"""Offline LLMOps gates: scripted provider outputs, real query safety validation."""

import json
from types import SimpleNamespace

import httpx
import pytest
from langsmith import get_tracing_context

from backend import generation, llmops, store, usage, workspaces
from backend.adapters.base import AdapterError
from backend.adapters.relational import SQLite
from backend.demo import sqlite_demo
from integration.check_evaluation import failures


@pytest.fixture
def adapter():
    with SQLite(sqlite_demo()) as instance:
        yield instance


SCHEMA = {
    "tables": [{"name": "orders", "columns": [{"name": "id", "type": "INTEGER"}]}]
}


def draft(query=None, clarification=None):
    return {
        "query": query,
        "clarification": clarification,
        "explanation": "Synthetic fixture",
        "assumptions": [],
    }


@pytest.mark.parametrize(
    "responses,expected_calls,has_query",
    [
        ([draft("SELECT id FROM orders LIMIT 5")], 1, True),
        ([draft("SELECT id FROM orders", "Define best")], 1, False),
        ([draft("DELETE FROM orders"), draft("SELECT id FROM orders")], 2, True),
        (
            [draft("SELECT salary FROM orders"), draft("SELECT salary FROM orders")],
            2,
            False,
        ),
        (
            [{"response_error": "invalid JSON"}, draft(clarification="Which field?")],
            2,
            False,
        ),
    ],
)
def test_graph_boundaries(monkeypatch, responses, expected_calls, has_query, adapter):
    calls = []

    def model(*args, **kwargs):
        assert get_tracing_context()["enabled"] is False
        calls.append(args[2])
        return responses[len(calls) - 1], {
            "model_calls": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "seconds": 1,
            "estimated_cost_usd": 0,
        }

    monkeypatch.setattr(generation, "call", model)
    monkeypatch.setattr(
        adapter, "execute", lambda *args: pytest.fail("Generation executed a query")
    )
    report = generation.generate("fixture", adapter, SCHEMA, "Synthetic request")
    assert len(calls) == expected_calls
    assert bool(report.get("query")) == has_query
    assert report["usage"]["model_calls"] == expected_calls
    assert report["validation"]["executable"] is None
    assert report["validation"]["business_meaning_verified"] is False
    if expected_calls == 2:
        assert "invalid_draft" in calls[1] and report["repair_attempts"] == 1


def test_graph_cancellation_before_repair(monkeypatch, adapter):
    calls = []

    def model(*args):
        calls.append(1)
        return draft("DELETE FROM orders"), {"model_calls": 1}

    def check():
        if calls:
            raise TimeoutError("cancelled")

    monkeypatch.setattr(generation, "call", model)
    with pytest.raises(TimeoutError):
        generation.generate("fixture", adapter, SCHEMA, "Synthetic", check=check)
    assert len(calls) == 1


def test_langchain_preserves_wire_contract(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    def post(url, **kwargs):
        assert get_tracing_context()["enabled"] is False
        assert url.endswith("/chat/completions")
        assert kwargs["timeout"] == 45
        assert kwargs["headers"]["Authorization"] == "Bearer synthetic"
        assert kwargs["json"]["response_format"]["type"] == "json_object"
        return httpx.Response(200, json={"fixture": True})

    monkeypatch.setattr(llmops.httpx, "post", post)
    assert llmops.completion(
        {"response_format": {"type": "json_object"}}, "synthetic"
    ).json() == {"fixture": True}


def test_telemetry_excludes_content_and_survives_failure(monkeypatch):
    sent = []

    class Client:
        def start_observation(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(end=lambda: None)

    monkeypatch.setattr(llmops, "telemetry_client", lambda: Client())
    llmops.record_model(
        {
            "input_tokens": 12,
            "output_tokens": 3,
            "query": "PRIVATE QUERY",
            "prompt": "PRIVATE PROMPT",
            "user": "PRIVATE ID",
        },
        "completed",
    )
    assert sent[0]["usage_details"] == {"input": 12, "output": 3}
    assert "PRIVATE" not in json.dumps(sent)

    def fail():
        raise RuntimeError("private SDK details")

    monkeypatch.setattr(llmops, "telemetry_client", fail)
    llmops.record_model({}, "failed")


def test_telemetry_requires_explicit_opt_in(monkeypatch):
    llmops.telemetry_client.cache_clear()
    monkeypatch.delenv("QOT_LANGFUSE_ENABLED", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "synthetic")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "synthetic")
    assert llmops.telemetry_client() is None
    llmops.telemetry_client.cache_clear()


def test_sdk_mask_preserves_only_operational_metadata():
    assert llmops.mask_payload(
        data={
            "workflow_version": llmops.WORKFLOW_VERSION,
            "outcome": "completed",
            "seconds": 1.25,
            "query": "PRIVATE",
            "user": "PRIVATE",
        }
    ) == {
        "workflow_version": llmops.WORKFLOW_VERSION,
        "outcome": "completed",
        "seconds": 1.25,
    }
    assert llmops.mask_payload(data="PRIVATE") == "[redacted]"
    assert llmops.mask_payload(data=None) is None
    assert llmops.mask_payload(data={"seconds": float("nan")}) == {}


def test_release_gate_rejects_incomplete_stale_and_failed_evidence():
    report = {
        "prompt_revision": llmops.prompt_revision(generation.SYSTEM),
        "workflow_version": llmops.WORKFLOW_VERSION,
        "cases": [
            {"semantic_accuracy": True, "execution_success": True},
            {"correct_clarification": True, "query": None},
        ],
    }
    assert failures(report, 1, 1) == []
    assert failures(report, 9, 3)
    assert failures({**report, "prompt_revision": "stale"}, 1, 1)
    report["cases"][0]["semantic_accuracy"] = False
    assert failures(report, 1, 1)


@pytest.mark.parametrize(
    "status,body",
    [
        (
            200,
            {
                "choices": [
                    {"message": {"content": json.dumps(draft("SELECT id FROM orders"))}}
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        ),
        (429, {"error": "PRIVATE PROVIDER RESPONSE"}),
    ],
)
def test_accounting_through_actual_chain(tmp_path, monkeypatch, status, body):
    monkeypatch.delenv("JOB_DATABASE_URL", raising=False)
    monkeypatch.setattr(store, "DB", tmp_path / "app.sqlite3")
    store.init()
    workspaces.init()
    user = workspaces.user_for_identity("fixture", "llmops", "Synthetic")["id"]
    monkeypatch.setenv("MODEL_API_KEY", "synthetic")
    monkeypatch.setattr(
        llmops.httpx, "post", lambda *args, **kwargs: httpx.Response(status, json=body)
    )
    if status == 200:
        value, measured = generation.call(
            user, generation.SYSTEM, {"request": "Synthetic"}
        )
        assert value["query"]
        assert measured["prompt_revision"] == llmops.prompt_revision(generation.SYSTEM)
        assert usage.current(user)["tokens_used_or_reserved"] == 30
    else:
        with pytest.raises(AdapterError) as error:
            generation.call(user, generation.SYSTEM, {"request": "Synthetic"})
        assert "PRIVATE" not in str(error.value)
        assert usage.current(user)["tokens_used_or_reserved"] > 30
    assert usage.current(user)["last_24h"]["model_calls"] == 1
