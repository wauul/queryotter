"""Railway API with a supervised separate worker process and durable Neon jobs."""

import multiprocessing
import os
import threading
import uvicorn
from dotenv import load_dotenv
from backend import store
from backend.worker import on_demand
from backend import monitoring


@monitoring.process("supervisor")
def main():
    load_dotenv()
    if os.environ.get("QOT_TEST_NETWORKS"):
        raise SystemExit(
            "The test network exception must never be enabled in cloud mode."
        )
    if not os.environ.get("JOB_DATABASE_URL"):
        raise SystemExit(
            "Cloud mode requires JOB_DATABASE_URL; local files are not durable."
        )
    store.init()
    context = multiprocessing.get_context("spawn")
    wake = context.Event()
    worker = context.Process(target=on_demand, args=(wake,), name="queryotter-worker")
    worker.start()
    store.set_waker(wake.set)
    wake.set()
    stopping = threading.Event()

    def supervise():
        worker.join()
        if not stopping.is_set():
            monitoring.capture(RuntimeError("worker_exit"), "supervision", "supervisor")
            monitoring.flush()
            os._exit(1)

    threading.Thread(target=supervise, daemon=True).start()
    try:
        uvicorn.run(
            "backend.api:app",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "8000")),
            access_log=False,
            timeout_graceful_shutdown=10,
        )
    finally:
        stopping.set()
        worker.terminate()
        worker.join(timeout=10)
        if worker.is_alive():
            worker.kill()
        store.set_waker(None)


if __name__ == "__main__":
    main()
