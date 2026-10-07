# LLMOps verification — October 7, 2026

The EU QueryOtter Langfuse project (`cmuy7o97a012bad0gnho4i0s3`) was created
in the existing Hobby organization. No billing upgrade was made. Project API
credentials authenticated successfully and were saved privately to local and
Railway server configuration.

Provisioned and read back: three version-1 code-reference system prompts,
`queryotter-synthetic-safety-v1` with four synthetic items, and three boolean
score configurations. Runtime prompts remain pinned in the repository.

The actual LangChain/LangGraph/Groq generation workflow passed four disposable
SQLite cases: first five ordered order IDs matched independently specified
rows; ambiguous wording, a deletion request and an unknown salary field each
returned clarification without a query. No production records were used.
Langfuse API ingestion checks and the dashboard confirmed model observations
with token usage and workflow/outcome/duration metadata; input and output were
absent. A deterministic boundary score was also ingested.

The full Python suite passed 99 tests. The dedicated assistant/LLMOps CI gate
passed 29 tests; focused lint and locked dependency resolution passed. The
existing Authlib deprecation warning remains. CI disables external telemetry
for tests and saves the gate's JUnit artifact.

The initial live check exposed SDK masking of metadata; the mask was corrected
to reconstruct only fixed operational fields. Subsequent live checks verified
the corrected metadata and content exclusion. Model spans now start before the
provider request so observation latency brackets the actual operation.

Local sanitized run evidence is at `artifacts/langfuse-validation.json`; it is
ignored by Git. Reproduce it with `uv run python scripts/verify-langfuse.py`.
These four fixtures are narrow regressions, not general model accuracy or
verification of all engines. Production deployment and hosted checks must be
confirmed separately through provider status and a fresh synthetic hosted job.
