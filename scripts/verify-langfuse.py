"""Opt-in real Groq + Langfuse validation using only disposable synthetic data."""

import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import generation, llmops, store, workspaces
from backend.adapters.relational import SQLite
from backend.demo import sqlite_demo


def main():
    load_dotenv(".env")
    os.environ.pop("JOB_DATABASE_URL", None)
    os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = "validation"
    client = llmops.telemetry_client()
    if client is None or not client.auth_check():
        raise SystemExit("Configured Langfuse authentication is required.")
    started = datetime.now(UTC)
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        store.DB = Path(directory) / "validation.sqlite3"
        store.init()
        workspaces.init()
        user = workspaces.user_for_identity(
            "fixture", "llmops-validation", "Synthetic validation"
        )["id"]
        with SQLite(sqlite_demo()) as adapter:
            metadata = adapter.discover()
            for category, prompt in [
                (
                    "ordered-ids",
                    "Show the first five order ids ordered by id ascending. Return only id.",
                ),
                ("ambiguous", "Show the best customers."),
                ("unsafe", "Delete all orders."),
                ("missing-field", "Show customer salaries."),
            ]:
                draft = generation.generate(user, adapter, metadata, prompt)
                if category == "ordered-ids":
                    assert draft.get("query"), "Expected read-only draft."
                    assert draft["validation"]["executable"] is None
                    # This validation harness explicitly runs only this synthetic SELECT.
                    assert adapter.execute(draft["query"], metadata)["rows"] == [
                        [1],
                        [2],
                        [3],
                        [4],
                        [5],
                    ]
                else:
                    assert draft.get("clarification") and not draft.get("query"), (
                        "Expected focused clarification."
                    )
                cases.append(
                    {"category": category, "passed": True, "usage": draft["usage"]}
                )
                print(category, "passed", flush=True)
        client.flush()
        observations = []
        for _ in range(15):
            observations = client.api.observations.get_many(
                name="queryotter.model",
                from_start_time=started,
                fields="core,io,metadata,usage",
                limit=100,
            ).data
            if len(observations) >= sum(c["usage"]["model_calls"] for c in cases):
                break
            time.sleep(2)
        assert len(observations) >= len(cases), "Traces did not arrive in Langfuse."
        traces = []
        for observation in observations:
            assert observation.input in (None, "[redacted]")
            assert observation.output in (None, "[redacted]")
            assert (
                observation.metadata.get("workflow_version") == llmops.WORKFLOW_VERSION
            )
            assert observation.metadata.get("outcome") in {
                "completed",
                "invalid_json",
                "failed",
            }
            assert not any(
                k in observation.metadata
                for k in ("query", "prompt", "records", "user")
            )
            traces.append(
                {"trace_id": observation.trace_id, "observation_id": observation.id}
            )
        client.create_score(
            name="explicit_execution_boundary",
            value=1,
            data_type="BOOLEAN",
            trace_id=traces[0]["trace_id"],
            environment="validation",
        )
        client.flush()
        report = {
            "checked": datetime.now(UTC).isoformat(),
            "prompt_revision": llmops.prompt_revision(generation.SYSTEM),
            "workflow_version": llmops.WORKFLOW_VERSION,
            "cases": cases,
            "traces": traces,
            "sensitive_content_excluded": True,
            "scope": "Real Groq and Langfuse, local disposable SQLite synthetic fixtures only",
        }
        output = Path("artifacts/langfuse-validation.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print("Langfuse ingestion and content exclusion passed; evidence:", output)
    client.shutdown()


if __name__ == "__main__":
    main()
