"""Content-free model telemetry and a private LangChain transport boundary."""

import atexit
import hashlib
import math
import os
from functools import lru_cache

import httpx
from langchain_core.runnables import RunnableLambda
from langsmith import tracing_context

PROMPT_VERSION = "queryotter-native-v1"
WORKFLOW_VERSION = "draft-validate-repair-v1"


def prompt_revision(system):
    return hashlib.sha256(system.encode()).hexdigest()[:16]


def mask_payload(*, data, **kwargs):
    """The SDK masks metadata too; reconstruct only our fixed operational fields."""
    if data is None:
        return None
    if isinstance(data, dict):
        safe = {}
        if data.get("workflow_version") == WORKFLOW_VERSION:
            safe["workflow_version"] = WORKFLOW_VERSION
        if data.get("outcome") in {"failed", "invalid_json", "completed"}:
            safe["outcome"] = data["outcome"]
        seconds = data.get("seconds")
        if (
            isinstance(seconds, (int, float))
            and math.isfinite(seconds)
            and seconds >= 0
        ):
            safe["seconds"] = seconds
        return safe
    return "[redacted]"


@lru_cache(maxsize=1)
def telemetry_client():
    if os.getenv("QOT_LANGFUSE_ENABLED") != "1":
        return None
    if not all(os.getenv(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")):
        return None
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider

    # Dedicated provider: never export other libraries' HTTP/DB/model spans.
    client = Langfuse(
        tracer_provider=TracerProvider(),
        should_export_span=lambda span: span.name == "queryotter.model",
        mask=mask_payload,
        timeout=2,
    )
    atexit.register(client.shutdown)
    return client


def start_model_observation(revision):
    try:
        client = telemetry_client()
        if client is not None:
            return client.start_observation(
                name="queryotter.model", as_type="generation", version=revision
            )
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def record_model(metrics, outcome, observation=None):
    """Only numeric usage and fixed labels cross the telemetry boundary."""
    try:
        client = telemetry_client()
        if client is None:
            return
        attributes = {
            "name": "queryotter.model",
            "as_type": "generation",
            "version": metrics.get("prompt_revision", PROMPT_VERSION),
            "metadata": {
                "workflow_version": WORKFLOW_VERSION,
                "outcome": outcome
                if outcome in {"failed", "invalid_json", "completed"}
                else "failed",
                "seconds": metrics.get("seconds")
                if isinstance(metrics.get("seconds"), (int, float))
                else None,
            },
            "usage_details": {
                target: metrics[source]
                for source, target in (
                    ("input_tokens", "input"),
                    ("output_tokens", "output"),
                )
                if isinstance(metrics.get(source), int) and metrics[source] >= 0
            },
        }
        if observation is None:
            span = client.start_observation(**attributes)
        else:
            span = observation
            attributes.pop("name")
            attributes.pop("as_type")
            span.update(**attributes)
        span.end()
    except Exception:  # noqa: BLE001, S110
        # Observability must never fail a user operation or expose SDK errors.
        pass


def completion(payload, api_key):
    """LangChain composes requests; existing HTTP bounds/accounting stay authoritative."""

    def send(body):
        return httpx.post(
            os.getenv("MODEL_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
            + "/chat/completions",
            headers={"Authorization": "Bearer " + api_key},
            timeout=45,
            json=body,
        )

    # Explicitly disable inherited LangSmith tracing, including environment opt-ins.
    # Langfuse receives only record_model's allowlisted metrics, never callbacks.
    with tracing_context(enabled=False):
        return RunnableLambda(send).invoke(payload, config={"callbacks": []})
