import time, os, json, logging
from backend import store
from backend.investigate import run, Cancelled
from backend.safety import Unsupported
from backend import monitoring

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


@monitoring.worker_job
def execute(job):
    id = job["id"]
    last_check = 0.0
    cancelled = False

    def check(force=False):
        nonlocal last_check, cancelled
        if cancelled:
            raise Cancelled()
        now = time.monotonic()
        if not force and now - last_check < 0.25:
            return
        last_check = now
        with store.connect() as c:
            r = c.execute("SELECT cancel FROM jobs WHERE id=?", (id,)).fetchone()
        if not r or r["cancel"]:
            cancelled = True
            raise Cancelled()

    try:
        if job["query"].startswith("{"):
            if "assistant" in json.loads(job["query"]):
                from backend.assistant import execute as assistant_execute

                report = assistant_execute(
                    job, check, lambda s, m: store.event(id, s, m)
                )
            else:
                from backend.live import investigate_live

                report = investigate_live(
                    job, lambda s, m: store.event(id, s, m), check
                )
        else:
            with store.connect() as c:
                registered = c.execute("SELECT 1 FROM q_users WHERE id=? AND status='active'", (job["owner"],)).fetchone()
            report = run(job["query"], lambda s, m: store.event(id, s, m), check, model_user=job["owner"] if registered else None)
        check(force=True)
        store.finish(id, "completed", report)
    except Cancelled:
        store.finish(id, "cancelled")
        if store.get(id, job["owner"]):
            store.event(
                id,
                "cancelled",
                "Cancelled at a safe checkpoint; disposable experiments discarded.",
            )
    except Unsupported as e:
        store.finish(id, "rejected", error=str(e))
    except TimeoutError:
        store.finish(
            id,
            "failed",
            error="Job duration limit exceeded. Experimental changes discarded.",
        )
    except Exception as e:
        from backend.adapters.base import AdapterError

        try:
            check(force=True)
        except Cancelled:
            store.finish(id, "cancelled")
        else:
            if isinstance(e, AdapterError):
                store.finish(id, "rejected", error=str(e))
            else:
                monitoring.capture(e, "job", "worker")
                store.finish(
                    id,
                    "failed",
                    error=f"Database or model operation failed ({type(e).__name__}). Check credentials, verified TLS, network allowlists and read-only grants. Provider details and secrets are not logged.",
                )
    logging.info(
        json.dumps(
            {
                "event": "job_finished",
                "job_id": id,
                "state": (store.get(id, job["owner"]) or {"state": "deleted"})["state"],
            }
        )
    )


@monitoring.process("worker")
def main():
    store.init()
    with store.worker_lock():
        store.recover()
        logging.info('{"event":"worker_ready","concurrency":1}')
        while True:
            job = store.claim()
            if job:
                execute(job)
            else:
                time.sleep(0.5)


@monitoring.process("worker")
def on_demand(wake):
    """Railway child process: no DB polling or connections while idle."""
    store.init()
    recover = True
    logging.info('{"event":"worker_ready","concurrency":1,"mode":"on_demand"}')
    while True:
        wake.wait()
        wake.clear()
        try:
            with store.worker_lock() as lock:
                if recover:
                    from backend.db import cleanup_abandoned

                    cleanup_abandoned()
                    store.recover()
                    recover = False
                while job := store.claim():
                    execute(job)
                    if lock:
                        lock.execute("SELECT 1")
        except BlockingIOError:
            time.sleep(2)
            wake.set()


if __name__ == "__main__":
    main()
