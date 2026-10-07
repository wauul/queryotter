# Model workflow and operations

QueryOtter uses LangChain's `RunnableLambda` for the shared OpenAI-compatible
HTTP transport, including the historical PostgreSQL investigator. Groq remains
the model provider. The transport preserves the existing JSON/schema request,
45-second timeout and explicit retry/accounting controls; it adds no hidden retries.

LangGraph handles connected query generation: `draft → validate → end`, or
`draft → validate → repair → validate → end`. Clarification ends the workflow
without a query. At most two model calls are permitted. Each node checks
cancellation. Native adapter validation is authoritative; the graph never calls
execution. Run remains an explicit user action. Optimization proposals share the
LangChain transport and existing validation but do not use the draft graph.

The existing workspace database remains the durable job and usage store. Graph
state is in memory only: no extra checkpoint database or cross-account memory.

## Langfuse

Tracing is off by default. Configure these on the Python worker/server:

```dotenv
QOT_LANGFUSE_ENABLED=1
LANGFUSE_PUBLIC_KEY=YOUR_PROJECT_PUBLIC_KEY
LANGFUSE_SECRET_KEY=YOUR_PROJECT_SECRET_KEY
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=production
```

Use an existing Langfuse project or your own compatible hosted instance. Never
expose keys through Vite. No account, subscription or hosting service is created
by installing this integration. Credentials and live ingestion require separate
configuration; offline tests do not prove hosted ingestion.

Connected generation/refinement/optimization calls emit only numeric token
counts, measured operation seconds, fixed outcome labels, workflow version and
a SHA-256 revision of the system prompt. Prompts, schema, queries, parameters,
records, identifiers, credentials and exception text are excluded. Observation
timestamps bracket the actual model operation; `metadata.seconds` also records
its measured duration. Failed calls retain unknown usage in the durable budget ledger.
The historical standalone investigator uses the transport but does not emit these
Langfuse observations.

A dedicated OpenTelemetry provider and span-name filter isolate manual model
observations; a mask removes input/output data. No LangChain/Langfuse content
callback is attached. LangSmith tracing is explicitly disabled around graph and
transport calls even when its environment variable is enabled. Telemetry errors
cannot fail user operations. The SDK batches exports and shutdown flushes pending
events; abrupt process termination can lose telemetry. The database usage ledger
remains authoritative. Disable with `QOT_LANGFUSE_ENABLED=0` and restart the worker.

## LLMOps release gate

LLMOps is an operational workflow, rather than another dependency. This project
now versions its workflow and fingerprints the actual system prompt in stored
model usage. Dependencies are resolved in `uv.lock` and CI installs them locked.

```powershell
uv sync --locked
uv run pytest tests/test_llmops.py tests/test_assistant.py -q --junitxml=artifacts/llmops-regression.xml
```

CI blocks on this gate and saves its JUnit results. Scripted model outputs test
real adapter validation, clarification, unsafe/unknown fields, bounded repair,
cancellation, transport settings, privacy and successful/failed-call accounting.
These are deterministic workflow regressions, **not model semantic accuracy**.
Existing assistant tests also cover authorization and explicit execution.

Before a model or prompt release, additionally run the opt-in real-provider suite
in `integration/evaluate_nl.py` against its synthetic services (see
[evaluation methodology](evaluation.md)). Compare independently expected results,
clarification success, calls, repair counts and unknown usage with the prior report.
Save each report under a new artifact name; never present an older report as a
new-model result. Real runs consume provider quota and need the fixture services.
Check the new report with `uv run python -m integration.check_evaluation artifacts/nl-evaluation.json`.
The command exits nonzero for incomplete cases, semantic/execution/clarification
failures, or a mismatched prompt/workflow revision. For a targeted engine run,
set `--expected-semantic-cases 1`; all three clarification cases are still required.
The gate evaluates the supplied artifact; verify its model and date against the
intended release. It does not contact Groq or prove production behavior.
Do not release known safety or semantic regressions. Roll back code and `uv.lock`
together to the previous revision if a deployment regresses. No live model or
Langfuse verification is implied by CI or installing these packages.

References: [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
[Langfuse Python SDK](https://langfuse.com/docs/observability/sdk/overview).

## Provisioned project and repeatable verification

The EU [QueryOtter Langfuse project](https://cloud.langfuse.com/project/cmuy7o97a012bad0gnho4i0s3/traces)
contains three versioned code-reference system prompts, four synthetic safety
dataset items and three boolean score configurations. These are repository
mirrors and synthetic fixtures; runtime instructions remain pinned in code.
Server credentials are in private local/provider configuration, never Git.

```powershell
uv run python scripts/setup-langfuse.py
uv run python scripts/verify-langfuse.py
```

Setup reuses unchanged prompt versions, dataset item IDs and score names.
Verification explicitly consumes Groq quota for four synthetic cases and checks
independently expected SQLite results, clarifications and Langfuse ingestion.
It uses a temporary local application store and the `validation` environment.
It saves sanitized evidence to `artifacts/langfuse-validation.json`.
See [verification record](llmops-verification.md) for the actual evidence scope.
