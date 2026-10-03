"""Private, optional Sentry telemetry. Only explicit operation spans and FastAPI.

No automatic logging, HTTP client, database or model instrumentation is installed.
Every emitted event is reconstructed; arbitrary application data is discarded.
"""

# Fail-open monitoring deliberately swallows SDK errors without logging provider
# details or recursively reporting its own telemetry failures.
# ruff: noqa: BLE001, S110
import functools
import os
import re
import signal
from contextlib import contextmanager, nullcontext
from pathlib import Path

import sentry_sdk
from sentry_sdk.integrations.dedupe import DedupeIntegration

OPERATIONS = {
    "request",
    "job",
    "generation",
    "discovery",
    "execution",
    "benchmark",
    "supervision",
    "smoke",
    "validation",
    "optimization",
    "connection",
}
COMPONENTS = {"api", "worker", "supervisor"}
ERROR_TYPES = {
    "RuntimeError",
    "ValueError",
    "TypeError",
    "KeyError",
    "IndexError",
    "TimeoutError",
    "OSError",
    "AssertionError",
    "ZeroDivisionError",
    "ConnectionError",
}
SOURCE_FILES = {
    str(p.relative_to(Path(__file__).parent.parent)).replace("\\", "/")
    for p in Path(__file__).parent.rglob("*.py")
}


def release_name(value):
    if re.fullmatch(r"(?:queryotter@)?[a-f0-9]{40}", value or ""):
        return "queryotter@" + value.removeprefix("queryotter@")
    return None


def sample_rate(value):
    try:
        rate = float(value)
        return rate if 0 <= rate <= 1 else 0.1
    except (TypeError, ValueError):
        return 0.1


def route_name(value):
    from urllib.parse import urlsplit

    path = urlsplit(value or "/").path
    path = re.sub(r"[a-f0-9]{32}|\{(?:id|jid|cid|rid)\}", ":id", path)
    allowed = {
        "api",
        "assistant",
        "session",
        "health",
        "healthz",
        "login",
        "logout",
        "examples",
        "jobs",
        "cancel",
        "report",
        "connections",
        "reports",
        "catalog",
        "settings",
        "parse-connection",
        "demo",
        "start",
        "auth",
        "github",
        "google",
        "microsoft",
        "callback",
        "owner",
        "remove",
        "rotate",
        "prisma",
        "schema",
        "results",
        "export",
        "history",
        "clear",
        "saved",
        "account",
        "delete",
        "connectors",
        "poll",
        "complete",
        ":id",
    }
    return (
        path
        if path.startswith("/api/") and all(p in allowed for p in path.split("/") if p)
        else "/"
    )


def trace_headers(headers):
    trace = headers.get("sentry-trace", "")
    if (
        not isinstance(trace, str)
        or not re.fullmatch(r"[a-f0-9]{32}-[a-f0-9]{16}(?:-[01])?", trace)
        or trace[:32] == "0" * 32
        or trace[33:49] == "0" * 16
    ):
        return {}
    baggage = headers.get("baggage", "")
    allowed = []
    if isinstance(baggage, str) and len(baggage) <= 2048:
        patterns = {
            "sentry-trace_id": r"[a-f0-9]{32}",
            "sentry-sampled": r"true|false",
            "sentry-sample_rate": r"0(?:\.\d{1,8})?|1(?:\.0{1,8})?",
        }
        parts = dict(
            part.strip().split("=", 1) for part in baggage.split(",") if "=" in part
        )
        for key, pattern in patterns.items():
            value = parts.get(key, "")
            if re.fullmatch(pattern, value) and (
                key != "sentry-trace_id" or value == trace[:32]
            ):
                allowed.append(key + "=" + value)
    return {
        "sentry-trace": trace,
        **({"baggage": ",".join(allowed)} if allowed else {}),
    }


def _trace(context):
    out = {}
    for key, length in (("trace_id", 32), ("span_id", 16), ("parent_span_id", 16)):
        value = context.get(key, "")
        if isinstance(value, str) and re.fullmatch(rf"[a-f0-9]{{{length}}}", value):
            out[key] = value
    if context.get("status") in {
        "ok",
        "internal_error",
        "cancelled",
        "deadline_exceeded",
        "unknown_error",
    }:
        out["status"] = context["status"]
    return out


def sanitize_span(span, hint=None):
    out = _trace(span)
    for key in ("start_timestamp", "timestamp"):
        if isinstance(span.get(key), (int, float, str)):
            # Python SDK timestamps are generated ISO strings, not application fields.
            value = span[key]
            if isinstance(value, (int, float)) or re.fullmatch(
                r"\d{4}-\d\d-\d\dT[\d:.]+Z?", value
            ):
                out[key] = value
    out["op"] = (
        span.get("op")
        if span.get("op") in {"http.server", "queue.process", "queryotter.operation"}
        else "queryotter.operation"
    )
    name = span.get("description", "")
    out["description"] = name if name in OPERATIONS else route_name(name)
    data = span.get("data", {})
    out["data"] = {}
    if data.get("operation") in OPERATIONS:
        out["data"]["operation"] = data["operation"]
    if data.get("engine") in {
        "postgresql",
        "sqlite",
        "mysql",
        "mariadb",
        "sqlserver",
        "cockroachdb",
        "mongodb",
        "firestore",
        "realtime",
        "libsql",
    }:
        out["data"]["engine"] = data["engine"]
    return out


def sanitize_event(event, hint=None):
    # Drop expected exceptions, including those raised through framework handlers.
    error = (hint or {}).get("exc_info", (None, None, None))[1]
    if expected(error):
        return None
    out = {}
    if hint is not None:
        hint.pop("attachments", None)
    for key in (
        "event_id",
        "type",
        "platform",
        "level",
        "timestamp",
        "start_timestamp",
    ):
        value = event.get(key)
        if (
            key == "event_id"
            and isinstance(value, str)
            and re.fullmatch(r"[a-f0-9]{32}", value)
            or key in {"type", "platform", "level"}
            and value in {"transaction", "python", "error", "warning", "info", "fatal"}
            or key in {"timestamp", "start_timestamp"}
            and (
                isinstance(value, (int, float))
                or isinstance(value, str)
                and re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:.]+Z?", value)
            )
        ):
            out[key] = value
    release = release_name(event.get("release"))
    if release:
        out["release"] = release
    env = event.get("environment")
    out["environment"] = (
        env
        if env in {"production", "preview", "staging", "development", "test"}
        else "development"
    )
    tags = event.get("tags", {})
    out["tags"] = {}
    if tags.get("component") in COMPONENTS:
        out["tags"]["component"] = tags["component"]
    if tags.get("operation") in OPERATIONS:
        out["tags"]["operation"] = tags["operation"]
    out["contexts"] = {"trace": _trace(event.get("contexts", {}).get("trace", {}))}
    if event.get("exception"):
        values = []
        for value in event["exception"].get("values", []):
            frames = []
            for frame in value.get("stacktrace", {}).get("frames", []):
                filename = str(frame.get("filename", "")).replace("\\", "/")
                filename = next(
                    (
                        f
                        for f in SOURCE_FILES
                        if filename == f or filename.endswith("/" + f)
                    ),
                    None,
                )
                frames.append(
                    {
                        **({"filename": filename} if filename else {}),
                        **{
                            k: frame[k]
                            for k in ("lineno", "colno")
                            if isinstance(frame.get(k), int)
                        },
                        "in_app": bool(filename),
                    }
                )
            values.append(
                {
                    "type": value.get("type")
                    if value.get("type") in ERROR_TYPES
                    else "Error",
                    "value": "[redacted]",
                    "stacktrace": {"frames": frames},
                    "mechanism": {
                        "type": "generic",
                        "handled": value.get("mechanism", {}).get("handled")
                        is not False,
                    },
                }
            )
        out["exception"] = {"values": values}
    if event.get("type") == "transaction":
        name = event.get("transaction", "")
        out["transaction"] = name if name in OPERATIONS else route_name(name)
        out["transaction_info"] = {"source": "route"}
        out["spans"] = [sanitize_span(span) for span in event.get("spans", [])]
    return out


def expected(error):
    if error is None:
        return False
    import asyncio

    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError

    from backend.adapters.base import AdapterError
    from backend.investigate import Cancelled
    from backend.safety import Unsupported

    return (
        isinstance(
            error,
            (
                AdapterError,
                Cancelled,
                Unsupported,
                RequestValidationError,
                asyncio.CancelledError,
            ),
        )
        or isinstance(error, HTTPException)
        and error.status_code < 500
    )


def init(component):
    dsn = os.environ.get("SENTRY_PYTHON_DSN", "")
    if not dsn:
        return False
    try:
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        integrations = [DedupeIntegration()]
        if component == "api":
            integrations += [
                FastApiIntegration(transaction_style="url", middleware_spans=False),
                StarletteIntegration(transaction_style="url", middleware_spans=False),
            ]
        env = os.environ.get("SENTRY_ENVIRONMENT", "development")
        sentry_sdk.init(
            dsn=dsn,
            release=release_name(
                os.environ.get("SENTRY_RELEASE")
                or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
                or os.environ.get("QOT_GIT_SHA")
            ),
            environment=env
            if env in {"production", "preview", "staging", "development", "test"}
            else "development",
            default_integrations=False,
            auto_enabling_integrations=False,
            integrations=integrations,
            send_default_pii=False,
            include_local_variables=False,
            include_source_context=False,
            max_request_body_size="never",
            max_breadcrumbs=0,
            enable_logs=False,
            send_client_reports=False,
            auto_session_tracking=False,
            trace_propagation_targets=[],
            traces_sample_rate=sample_rate(os.environ.get("SENTRY_TRACES_SAMPLE_RATE")),
            before_send=sanitize_event,
            before_send_transaction=sanitize_event,
            before_breadcrumb=lambda breadcrumb, hint: None,
            shutdown_timeout=1.5,
        )
        sentry_sdk.set_tag("component", component)
        sentry_sdk.set_user(None)
        return True
    except Exception:
        return False


def capture(error, operation="request", component=None):
    if expected(error):
        return
    try:
        with sentry_sdk.new_scope() as scope:
            scope.set_tag(
                "operation", operation if operation in OPERATIONS else "request"
            )
            if component in COMPONENTS:
                scope.set_tag("component", component)
            sentry_sdk.capture_exception(error)
    except Exception:
        pass


def flush():
    try:
        sentry_sdk.flush(timeout=1.5)
    except Exception:
        pass


def queued_trace():
    if not sentry_sdk.is_initialized():
        return {}
    try:
        return trace_headers(
            {
                "sentry-trace": sentry_sdk.get_traceparent(),
                "baggage": sentry_sdk.get_baggage(),
            }
        )
    except Exception:
        return {}


@contextmanager
def operation(name):
    manager = nullcontext()
    try:
        if sentry_sdk.is_initialized():
            manager = sentry_sdk.start_span(
                op="queryotter.operation",
                name=name if name in OPERATIONS else "request",
            )
    except Exception:
        pass
    with manager:
        yield


def instrument(name):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            with operation(name):
                return fn(*args, **kwargs)

        return wrapped

    return decorate


def worker_job(fn):
    @functools.wraps(fn)
    def wrapped(job):
        headers = {}
        try:
            import json

            headers = trace_headers(json.loads(job.get("trace_context") or "{}"))
        except (ValueError, TypeError, AttributeError):
            pass
        with sentry_sdk.new_scope() as current, sentry_sdk.isolation_scope() as scope:
            current.clear()
            scope.clear()
            scope.set_tag("component", "worker")
            scope.set_tag("operation", "job")
            manager = nullcontext()
            try:
                if sentry_sdk.is_initialized():
                    transaction = sentry_sdk.continue_trace(
                        headers, op="queue.process", name="job"
                    )
                    manager = sentry_sdk.start_transaction(transaction)
            except Exception:
                pass
            with manager:
                return fn(job)

    return wrapped


def process(component):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            from dotenv import load_dotenv

            load_dotenv()
            init(component)
            previous = None
            if component == "worker":
                previous = signal.getsignal(signal.SIGTERM)
                signal.signal(
                    signal.SIGTERM,
                    lambda signum, frame: (_ for _ in ()).throw(SystemExit(0)),
                )
            try:
                return fn(*args, **kwargs)
            except Exception as error:
                capture(error, "supervision", component)
                raise
            finally:
                flush()
                if previous is not None:
                    signal.signal(signal.SIGTERM, previous)

        return wrapped

    return decorate


class TraceIngress:
    """Validate trace metadata before Sentry's FastAPI/ASGI integration sees it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            headers = scope.get("headers", [])
            incoming = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in headers
                if k.lower() in {b"sentry-trace", b"baggage"}
            }
            safe = trace_headers(incoming)
            scope["headers"] = [
                (k, v)
                for k, v in headers
                if k.lower() not in {b"sentry-trace", b"baggage"}
            ] + [(k.encode(), v.encode()) for k, v in safe.items()]
        await self.app(scope, receive, send)
