# Evaluation and benchmark methodology

Published artifacts contain synthetic data only. They document observed runs, not guarantees across unseen databases.

## Engine and model evaluation

`integration/fixtures.py` provisions the named disposable local services from `integration/compose.yml` and seeds independently defined customers/orders. Fixtures contain joins, aggregation, paid/unpaid values, dates at calendar boundaries, NULLs, duplicates and missing/varying document fields. `integration/verify.py` discovers actual metadata, validates native queries and compares actual rows with expected results computed outside the generated query. It also tests unsafe/unknown native constructs, result bounds, deadlines, cancellation checkpoints, capabilities and applicable invalid passwords.

`integration/evaluate_nl.py` gives Groq scoped actual schema, a concrete question and date context. It independently executes the validated native draft and compares expected rows/IDs. Model generation and execution are separate operations. Clarification cases expect a question and no runnable query. Tests use the real configured Groq API; rate-limit failures remain failures. The published final evidence combines recorded successful runs after the Realtime numeric-key/schema fixes and includes that provenance.

| Measurement | Observed result | Scope |
|---|---|---|
| Connection + discovery + native validation/execution | 9/9 | Official local databases / Firebase emulators |
| Real Groq native-query cases | 9/9 | One independently specified synthetic case per engine |
| Focused clarification | 3/3 | Ambiguous “best”, missing relationship/context and unsupported request cases in artifact |
| Model usage | 14,604 input + 3,829 output tokens; 12 calls | Successful published evaluation; failed/other calls are separate ledger entries |
| Estimated model cost | $0.004488 | $0.15/M input + $0.60/M output; estimate, not invoice |
| Native in-flight execution timeout | 6/6 relational | Actual expensive aggregate on disposable local fixtures |
| Hosted PostgreSQL | Passed | Neon 18.6: TLS, read-only discovery/FK/native expected rows/EXPLAIN |
| Python / proxy regression suites | 76 / 4 passing after expanded verification | Authorization, budget, SQL/document limits, connector protocol, sessions, deletion and proxy controls |

See [adapter evidence](../public/adapter-verification.json), [model evidence](../public/nl-evaluation.json), [actual execution bounds](../public/execution-boundaries.json), and [Neon evidence](../public/neon-verification.json). The support matrix distinguishes version and environment. Emulator success is not Firebase hosted-IAM or production-index verification. Cockroach's insecure fixture does not verify hosted authentication.

## Controlled SQLite benchmarking

Only an uploaded copy is eligible. The worker creates a **second** disposable file, validates original/candidate against discovered metadata, and permits at most two non-unique plain-column experimental indexes. It never changes the user's uploaded source or a connected database. Queries must return a full result of at most 500 rows.

Correctness compares typed values, duplicates, NULLs and output column names/order. With required ORDER BY, rows compare in order; otherwise a typed multiset is compared. Equality on this one snapshot is explicitly narrower than all-input equivalence. An index does not establish correctness of a different query. Non-equivalent candidates receive no successful optimization claim.

Timing uses one warm-up and seven warm client-wall-time samples before and after candidate indexes, including fetching the result. Reports show median, median absolute deviation (MAD), all samples, original/candidate plans, scope and observed additional allocated bytes. A measured win requires more than 10% and a difference above twice combined MAD. Cache and execution-order effects can remain. Index write overhead is disclosed but not measured.

The [actual deployed SQLite copy report](../public/deployed-copy-benchmark.json) measured 0.010071 ms baseline vs 0.007581 ms candidate median (MAD 0.000592 / 0.000350 ms), 1.3285× on six complete ordered rows, with 4,096 extra allocated bytes. These tiny warm-cache timings are a narrow fixture observation, not a practical production latency prediction.

A [second deployed copy report](../public/deployed-copy-benchmark-no-gain.json), downloaded through the authorized server export, passed the same six-row result comparison but found no verified gain. This is retained separately: tiny timings can vary enough to change the observed outcome, and the application does not label every proposed index an improvement.

## Preserved PostgreSQL portfolio

The original suite creates isolated PostgreSQL schemas, seeded orders/customers, independent edge datasets and controlled indexes. It uses actual EXPLAIN ANALYZE/BUFFERS, seven timing samples, median/MAD, full empirical correctness checks and a conservative win threshold. The published 15-case regression report includes refused/unsupported cases, 12 supported cases and eight measured wins. The historical README and [suite artifact](../public/evaluation.json) describe the exact fixtures and outcomes.

The [fresh expanded-application PostgreSQL report](../public/deployed-postgresql-benchmark.json), exported through production on September 30, measured 6.294 ms baseline vs 0.086 ms candidate median (MAD 0.215 / 0.007 ms), 73.19×, across seven warm-cache repetitions. It passed all four correctness fixtures, including the 120,000-order dataset. The hosted Neon PostgreSQL 18.6 investigation used one Groq call, 1,254 input and 241 output tokens, 237 tracked database tool calls and 13.02 seconds end-to-end; estimated model cost was $0.0003327. Index experiments used transaction rollback in a disposable synthetic schema. These observations do not describe arbitrary connected production queries.

The earlier [deployed-verification.json](deployed-verification.json) report remains as historical evidence. [Cloud deployment evidence](cloud-deployment.json) records the current infrastructure and checks.

## Reproduction and practical limits

Run the commands in the root README with Docker fixtures, uv's locked environment and an explicit Groq key. Save a new artifact rather than overwriting provenance with stale measurements. CI runs deterministic native fixtures without requiring hosted/model credentials. Model tests consume quota and should be paced; operating-system/Python/SQLite versions and shared CPU load affect runtime.

Syntax validation does not prove executability. Executability does not prove intent. Independently specified expected results support only the tested semantics. More questions, schemas, time zones, document arrays and schema-drift cases are needed before interpreting these small fixtures as broad accuracy statistics. Plans/recommendations on engines without controlled benchmarks remain unmeasured. A failed credential/TLS test verifies a failure boundary, not successful provider onboarding.
