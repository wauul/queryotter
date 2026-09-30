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
    # One worker per store. Recover only after OS process lock acquired.
    lock = open(".data/worker.lock", "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("A worker already owns this store.")
    with store.connect() as c:
        c.execute(
            "UPDATE jobs SET state='queued',updated=? WHERE state='running' AND attempts<2 AND cancel=0",
            (time.time(),),
        )
        c.execute(
            "UPDATE jobs SET state='failed',error='Worker interrupted; retry budget exhausted.' WHERE state='running' AND cancel=0"
        )
        c.execute(
            "UPDATE jobs SET state='cancelled' WHERE cancel=1 AND state IN ('queued','running')"
        )
    logging.info('{"event":"worker_ready","concurrency":1}')
    while True:
        job = store.claim()
        if job:
            execute(job)
        else:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
