import json
import logging
import secrets

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from backend import monitoring, store, worker, workspaces
from backend.adapters.base import AdapterError
from backend.investigate import Cancelled

SECRET = "synthetic-secret-Groq-OAuth-p@ss-PROMPT-SELECT-private_schema-card424242"
TRACE = "a" * 32
PARENT = "b" * 16


class MemoryTransport(Transport):
    def __init__(self, options):
        super().__init__(options)
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)

    def events(self, type="event"):
        return [
            item.payload.json
            for envelope in self.envelopes
            for item in envelope.items
            if item.headers["type"] == type
        ]


@pytest.fixture
def telemetry(monkeypatch, tmp_path):
    original = sentry_sdk.get_client()
    original_init = sentry_sdk.init
    monkeypatch.setenv("SENTRY_PYTHON_DSN", "https://public@o0.ingest.sentry.io/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")
    monkeypatch.setenv("SENTRY_RELEASE", "c" * 40)
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "1")

    def init(**kwargs):
        kwargs["transport"] = MemoryTransport
        return original_init(**kwargs)

    monkeypatch.setattr(sentry_sdk, "init", init)
    assert monitoring.init("api")
    monkeypatch.delenv("JOB_DATABASE_URL", raising=False)
    monkeypatch.setattr(store, "DB", tmp_path / "jobs.db")
    store.init()
    workspaces.init()
    transport = sentry_sdk.get_client().transport
    yield transport
    sentry_sdk.get_client().close(timeout=0.1)
    sentry_sdk.get_global_scope().set_client(original)


def test_allowlist_removes_secrets_from_all_event_surfaces():
    event = {
        "message": SECRET,
        "request": {"url": SECRET, "cookies": SECRET, "data": SECRET},
        "user": {"id": SECRET},
        "extra": {"query": SECRET},
        "server_name": SECRET,
        "breadcrumbs": [{"message": SECRET}],
        "contexts": {
            "trace": {
                "trace_id": TRACE,
                "span_id": PARENT,
                "dynamic_sampling_context": {"secret": SECRET},
            },
            "model": {"prompt": SECRET},
        },
        "exception": {
            "values": [
                {
                    "type": SECRET,
                    "value": SECRET,
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": SECRET,
                                "function": SECRET,
                                "context_line": SECRET,
                                "vars": {"password": SECRET},
                                "lineno": 3,
                            },
                            {"filename": "backend/worker.py", "lineno": 10},
                        ]
                    },
                }
            ]
        },
        "tags": {"component": "worker", "operation": "job", "query": SECRET},
        "release": SECRET,
    }
    sanitized = monitoring.sanitize_event(event)
    assert SECRET not in json.dumps(sanitized)
    assert (
        sanitized["exception"]["values"][0]["stacktrace"]["frames"][1]["filename"]
        == "backend/worker.py"
    )
    assert (
        monitoring.sanitize_span(
            {"description": SECRET, "data": {"db.statement": SECRET}}
        )["description"]
        == "/"
    )


def test_sdk_envelopes_have_no_request_data_locals_logging_or_model_content(telemetry):
    sentry_sdk.set_extra("query", SECRET)
    sentry_sdk.set_user({"id": SECRET, "email": SECRET})
    sentry_sdk.add_breadcrumb(message=SECRET, data={"sql": SECRET})
    logging.getLogger(__name__).error(SECRET)
    try:
        connection_string = SECRET
        raise RuntimeError(connection_string)
    except RuntimeError as error:
        monitoring.capture(error, "generation", "worker")
        monitoring.capture(error, "generation", "worker")
    monitoring.flush()
    assert len(telemetry.events()) == 1
    event = telemetry.events()[0]
    assert event["release"] == "queryotter@" + "c" * 40
    assert event["tags"] == {"component": "worker", "operation": "generation"}
    assert SECRET.encode() not in b"".join(e.serialize() for e in telemetry.envelopes)
    assert sentry_sdk.get_client().options["include_local_variables"] is False
    assert set(sentry_sdk.get_client().integrations) == {
        "dedupe",
        "fastapi",
        "starlette",
    }


def test_queue_metadata_and_worker_capture_preserve_states_and_trace(
    telemetry, monkeypatch
):
    incoming = {
        "sentry-trace": f"{TRACE}-{PARENT}-1",
        "baggage": f"sentry-trace_id={TRACE},sentry-user_id={SECRET},vendor={SECRET}",
    }
    with sentry_sdk.start_transaction(
        sentry_sdk.continue_trace(
            monitoring.trace_headers(incoming), op="http.server", name="/api/jobs"
        )
    ):
        created = store.create("alice", secrets.token_hex(12), None, "SELECT 1")
    assert "trace_context" not in created
    job = store.claim()
    assert SECRET not in job["trace_context"]
    assert json.loads(job["trace_context"])["sentry-trace"].startswith(TRACE)

    def fail(*args, **kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(worker, "run", fail)
    worker.execute(job)
    assert store.get(job["id"], "alice")["state"] == "failed"
    assert len(telemetry.events()) == 1
    assert telemetry.events()[0]["contexts"]["trace"]["trace_id"] == TRACE
    assert any(
        event["transaction"] == "job"
        and event["contexts"]["trace"]["trace_id"] == TRACE
        for event in telemetry.events("transaction")
    )
    assert SECRET.encode() not in b"".join(e.serialize() for e in telemetry.envelopes)


@pytest.mark.parametrize(
    "error,state",
    [
        (AdapterError(SECRET), "rejected"),
        (Cancelled(), "cancelled"),
        (TimeoutError(), "failed"),
    ],
)
def test_expected_worker_outcomes_do_not_alert(telemetry, monkeypatch, error, state):
    created = store.create("alice", secrets.token_hex(12), None, "SELECT 1")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(worker, "run", fail)
    worker.execute(store.claim())
    assert store.get(created["id"], "alice")["state"] == state
    assert not telemetry.events()


def test_trace_validation_and_missing_configuration(monkeypatch):
    assert monitoring.trace_headers({"sentry-trace": SECRET}) == {}
    assert monitoring.trace_headers(
        {"sentry-trace": f"{TRACE}-{PARENT}-1", "baggage": "x=" + SECRET}
    ) == {"sentry-trace": f"{TRACE}-{PARENT}-1"}
    monkeypatch.delenv("SENTRY_PYTHON_DSN", raising=False)
    assert monitoring.init("worker") is False


def test_fastapi_errors_capture_once_and_expected_auth_does_not(telemetry):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.post("/api/jobs")
    def broken():
        raise RuntimeError(SECRET)

    @app.get("/api/session")
    def unauthorized():
        raise HTTPException(401, SECRET)

    client = TestClient(monitoring.TraceIngress(app), raise_server_exceptions=False)
    response = client.post(
        "/api/jobs?code=" + SECRET,
        headers={
            "sentry-trace": f"{TRACE}-{PARENT}-1",
            "baggage": "sentry-user_id=" + SECRET,
            "authorization": SECRET,
        },
        json={"prompt": SECRET, "query": SECRET},
    )
    assert response.status_code == 500
    assert client.get("/api/session").status_code == 401
    assert len(telemetry.events()) == 1
    assert telemetry.events()[0]["contexts"]["trace"]["trace_id"] == TRACE
    assert SECRET.encode() not in b"".join(e.serialize() for e in telemetry.envelopes)


def test_untraced_next_job_does_not_reuse_previous_user_trace(telemetry, monkeypatch):
    monkeypatch.setattr(
        worker,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(SECRET)),
    )
    first = store.create("alice", secrets.token_hex(12), None, "SELECT 1")
    job = store.claim()
    job["trace_context"] = json.dumps({"sentry-trace": f"{TRACE}-{PARENT}-1"})
    worker.execute(job)
    second = store.create("bob", secrets.token_hex(12), None, "SELECT 1")
    job = store.claim()
    job["trace_context"] = "malformed"
    worker.execute(job)
    events = telemetry.events()
    assert len(events) == 2
    assert events[0]["contexts"]["trace"]["trace_id"] == TRACE
    assert events[1]["contexts"]["trace"]["trace_id"] != TRACE
    assert all("user" not in event for event in events)
    assert store.get(first["id"], "alice")["state"] == "failed"
    assert store.get(second["id"], "bob")["state"] == "failed"


def test_swallowed_provider_failure_is_captured_before_safe_adapter_error(
    telemetry, monkeypatch
):
    from backend.adapters import registry

    class Broken:
        def __init__(self, config, check):
            raise RuntimeError(SECRET)

    monkeypatch.setitem(registry.ADAPTERS, "sqlite", Broken)
    with pytest.raises(AdapterError), registry.open_adapter("sqlite", {}):
        pass
    assert len(telemetry.events()) == 1
    assert telemetry.events()[0]["tags"]["operation"] == "connection"
    assert SECRET.encode() not in b"".join(e.serialize() for e in telemetry.envelopes)
