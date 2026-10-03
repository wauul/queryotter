"""Synthetic monitoring smoke; disposable store, no production crash route.

By default intercept SDK envelopes locally. --send explicitly uses configured DSN.
Verify the printed event ID in Sentry; a flush alone is not proof of ingestion.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import sentry_sdk
from sentry_sdk.transport import Transport

from backend import monitoring, store, workspaces


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--component", choices=["api", "worker", "supervisor"], required=True
    )
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    envelopes = []
    event_ids = []
    if args.send and not os.environ.get("SENTRY_PYTHON_DSN"):
        parser.error("SENTRY_PYTHON_DSN is required for --send")
    original_init = sentry_sdk.init

    class LocalTransport(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)

    def local_init(**kwargs):
        kwargs["transport"] = LocalTransport
        return original_init(**kwargs)

    if not args.send:
        os.environ["SENTRY_PYTHON_DSN"] = "https://public@o0.ingest.sentry.io/1"
        os.environ["SENTRY_ENVIRONMENT"] = "test"
        os.environ["SENTRY_TRACES_SAMPLE_RATE"] = "1"
    with patch.object(sentry_sdk, "init", original_init if args.send else local_init):
        if not monitoring.init(args.component):
            parser.error("Monitoring initialization failed")
    original_filter = sentry_sdk.get_client().options["before_send"]

    def record_event(event, hint):
        sanitized = original_filter(event, hint)
        if sanitized:
            event_ids.append(sanitized["event_id"])
        return sanitized

    sentry_sdk.get_client().options["before_send"] = record_event
    if args.component == "api":
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/api/session")
        def broken():
            raise RuntimeError("QueryOtter synthetic API smoke")

        TestClient(monitoring.TraceIngress(app), raise_server_exceptions=False).get(
            "/api/session"
        )
    elif args.component == "worker":
        from backend import worker

        with (
            tempfile.TemporaryDirectory(prefix="queryotter-smoke-") as directory,
            patch.dict(os.environ, {"JOB_DATABASE_URL": ""}),
            patch.object(store, "DB", Path(directory) / "jobs.db"),
        ):
            store.init()
            workspaces.init()
            store.create("synthetic", "synthetic-worker-smoke", None, "SELECT 1")
            with patch.object(
                worker,
                "run",
                side_effect=RuntimeError("QueryOtter synthetic worker smoke"),
            ):
                worker.execute(store.claim())
    else:
        monitoring.capture(
            RuntimeError("QueryOtter synthetic supervision smoke"),
            "smoke",
            "supervisor",
        )
    event_id = event_ids[-1] if event_ids else None
    monitoring.flush()
    print(
        json.dumps(
            {
                "component": args.component,
                "event_id": event_id,
                "local_envelopes": len(envelopes) if not args.send else None,
                "ingestion_verified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
