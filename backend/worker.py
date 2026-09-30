import time, os, json, logging
from backend import store
from backend.investigate import run, Cancelled
from backend.safety import Unsupported

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def execute(job):
    id = job["id"]

    def check():
        with store.connect() as c:
            r = c.execute("SELECT cancel FROM jobs WHERE id=?", (id,)).fetchone()
        if r and r["cancel"]:
            raise Cancelled()

    try:
        if job["query"].startswith("{"):
            from backend.live import investigate_live

            report = investigate_live(job, lambda s, m: store.event(id, s, m), check)
        else:
            report = run(job["query"], lambda s, m: store.event(id, s, m), check)
        check()
        store.finish(id, "completed", report)
    except Cancelled:
        store.finish(id, "cancelled")
        store.event(
            id,
            "cancelled",
            "Cancelled at a safe checkpoint; experimental indexes rolled back.",
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
        store.finish(
            id,
            "failed",
            error=f"Investigation failed ({type(e).__name__}). Check model access and experiment database availability.",
        )
    logging.info(
        json.dumps(
            {
                "event": "job_finished",
                "job_id": id,
                "state": store.get(id, job["owner"])["state"],
            }
        )
    )


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
