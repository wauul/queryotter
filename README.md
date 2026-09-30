# QueryOtter

QueryOtter investigates slow PostgreSQL SELECTs using a real Groq model and a deterministic experiment executor. It reads plans, proposes rewrites or indexes, verifies results on independent fixtures, benchmarks surviving candidates, and recommends only measured improvements.

**Live app:** https://queryotter.sappy-cod-9447.chatgpt.site  
**Repository:** https://github.com/wauul/queryotter

![QueryOtter measured investigation](docs/queryotter-desktop.png)

The hosted frontend includes published measurements and a capped live demo. New investigations use a separately running connector on the developer's computer. This free deployment is a portfolio demonstration, not an always-on hosted database service. Published reports remain usable when the connector is offline. Live database access is owner-authenticated and **plan-only**: metadata and EXPLAIN without ANALYZE; no records, experimental indexes or performance claims on connected databases.

## Local setup

Requires Node 22+, Python 3.12+ and [uv](https://docs.astral.sh/uv/). PostgreSQL binaries are supplied by the locked `embedded-postgres` npm package. Docker is optional and was unavailable on the development machine.

```powershell
npm ci
uv sync --locked
npm run postgres
```

Keep that terminal running. This generates ignored `.env` secrets and starts real PostgreSQL on **127.0.0.1:55432**. In `.env`, set `MODEL_API_KEY` to a Groq key, `MODEL_BASE_URL=https://api.groq.com/openai/v1`, and `MODEL_NAME=openai/gpt-oss-120b`. A dedicated development key expires October 30, 2026; renew it in the server environment when needed. No key is shipped in the repository or frontend. `.env.example` documents configuration without credentials.

In three more terminals:

```powershell
uv run uvicorn backend.api:app --host 127.0.0.1 --port 8000 --no-access-log
uv run python -m backend.worker
npm run dev
```

Open http://127.0.0.1:5173. The Vite server injects the service token into its API proxy; it never sends that secret to the browser. Owner login uses `ADMIN_PASSWORD` from the private worker environment. Public registration is not implemented.

```powershell
uv run pytest -q
npm run build
uv run python -m scripts.evaluate
```

Evaluation makes real model calls; use the free Groq tier and its existing rate limits. It waits between supported cases and retries once on transient provider errors. No credits or paid hosting were purchased. Unit/integration tests do not call the model. Run evaluations with the worker idle for comparable resource conditions.

## Scope and decisions

Supported: filters, sorting, joins on supplied tables, aggregation, deterministic pagination, SELECT-only CTEs, missing indexes and ordinary column/covering index candidates. The public demo permits only 15 fixed examples. Authenticated custom queries target the synthetic `customers`, `orders`, and `items` tables. Live plan-only queries can target bounded public-schema tables using standard types.

Rejected: multiple statements, writes including data-modifying CTEs, SELECT INTO, locks, recursive CTEs, set operations, windows, volatile/unknown functions, arbitrary schema qualification and pagination without a supported unique tie-breaker. The SQL validator deliberately has a narrow allowlist. Unique ordering inference supports demo PK/FK patterns and grouped columns; it is not a general functional-dependency prover.

The loop is **inspect → explain → hypothesize → experiment → validate → benchmark → recommend**. The Groq model receives compact JSON plan nodes and relevant schema/statistics, never records or connection credentials. It chooses up to three ranked candidates in one decision call, with at most one transient retry. The executor owns all SQL validation, execution permissions, semantic comparison, benchmark calculations and recommendation selection. The agent is a bounded one-round investigator; it does not conduct unlimited exploratory model loops.

## Architecture

```mermaid
flowchart LR
  UI[React + TypeScript] --> Edge[Hosted Worker proxy]
  Edge -->|Service-authenticated HTTPS connector| API[FastAPI]
  API --> Jobs[(SQLite WAL jobs and events)]
  Worker[Separate Python worker, concurrency 1] --> Jobs
  Worker --> Groq[Groq structured JSON proposals]
  Worker --> PG[(Disposable PostgreSQL schemas)]
  UI --> Reports[Published reports and evaluation]
```

HTTP handlers enqueue work and return. SQLite stores owner-scoped jobs, events, idempotency keys, quotas and encrypted connection URLs. The worker uses an OS lock for single ownership, safe cancellation checkpoints, and at most two attempts after recovery from interruption. Requests with the same owner and idempotency key return the existing job. Report export and cancellation enforce the same owner check as retrieval. Reusing a request key with changed SQL or connection is rejected: use a fresh key.

## Dataset and isolation

Each investigation creates a random `qot_…` disposable schema with **10,000 customers, 120,000 orders and 240,000 items** (370,000 rows total), using deterministic arithmetic and seed 17. Every candidate also runs against empty tables and 300-/900-order edge fixtures with seeds 17 and 31, including NULLs, duplicate projected rows, an orphan customer, skew and boundary timestamps. See `backend/db.py` for exact seed SQL. Schemas are removed in a `finally` block; indexes are built only inside rollback transactions. An interrupted OS process can leave a schema; inspect and remove only abandoned `qot_` schemas in the designated disposable cluster before restarting evaluations.

The experiment URL must point to a **dedicated disposable cluster**. Its provisioning role creates the test schemas. SELECT/EXPLAIN run under `qot_reader`, a NOLOGIN, non-superuser role with SELECT grants. Standalone SELECTs also use read-only transactions; inside an index experiment transaction, restrictive role permissions protect execution while permitting the provisioning role to create disposable indexes. SQL comments are stripped and untrusted input cannot alter the system prompt.

Timeouts: statements 3 seconds, locks 500 ms, jobs 180 seconds with cooperative checkpoints. Model HTTP calls are limited to 45 seconds, with one bounded retry. Cancellation can wait for the current statement or provider request to finish. Comparisons stream at most 20,001 rows and reject results above 20,000 rows or 4 MB. One active run per session, 10 submitted jobs/hour/session, six anonymous model runs/day globally; cached reports cost nothing. Login attempts are limited. Quotas persist across restarts.

Live connections require a non-superuser role without creation/replication/bypass privileges, public-schema CREATE or direct write grants. Remote URLs require `sslmode=verify-full`. Credentials are encrypted using Fernet with a server-held key. Metadata is restricted to the public schema and 100 columns; live statements use read-only transactions, 1.5-second statement timeouts and 200-ms lock timeouts. Inherited permissions and arbitrary custom PostgreSQL type behavior are not comprehensively audited; only trusted owner connections to sanitized replicas should be used. Live data is never copied automatically. No production index or query replacement is applied.

## Correctness and benchmark methodology

Independent deterministic checks compare PostgreSQL type OIDs and typed values. Without ORDER BY, rows are compared as multisets including duplicate multiplicity; with ORDER BY, sequences must match. Edge tests specifically prove that a naive NOT IN → NOT EXISTS rewrite with NULLs and a DISTINCT rewrite over duplicates fail. Sample equality is **empirical evidence**, not mathematical equivalence.

Both original and candidate states get warmups. Two warm-up rounds precede seven measured rounds; the order alternates by round, with an additional equal warmup before each measurement. Candidate indexes are rebuilt in rollback transactions. ANALYZE runs consistently after seeding. No parallel query workers. PostgreSQL JSON EXPLAIN ANALYZE provides execution time and buffer counters. Displayed SQL latency is database execution time, excluding model/network overhead. No cold-cache claim is made. Median, minimum, maximum, samples and median absolute deviation (MAD) are exported. A win must beat a margin of `max(10% original median, 3 × max(original MAD, candidate MAD), 0.05 ms)`. Noisy or tiny differences are inconclusive.

Index build latency and storage are reported separately. Index maintenance/write overhead is disclosed but not measured. Choosing the fastest observed candidate among a small set can introduce selection bias; confirm with independent representative workloads. The original and fixed index baseline are measured independently in reproducibly seeded environments. Full case results, including no gain, errors and rejected inputs, are in `public/evaluation.json`. `database_seconds` measures client time in SQL execute calls including seeding/metadata, excluding streaming fetch, connection setup and model calls. Provider pricing estimates remain unavailable rather than assuming a paid cost.

## Deployment

The hosted app uses Sites with committed `.openai/hosting.json`, static `dist` assets, and `hosting/worker.js`. `CONNECTOR_URL` and secret `SERVICE_TOKEN` belong in the hosting environment. The Groq key, experiment URL, session secret and encryption key stay on the connector host.

For the current free demonstration, the official Cloudflare client runs:

```powershell
.data/bin/cloudflared.exe tunnel --url http://127.0.0.1:8000 --no-autoupdate
```

Use the returned URL for `CONNECTOR_URL`. The connector requires the service token, so visiting its tunnel directly cannot start jobs. The proxy removes caller-supplied service headers, forwards only approved API routes, refuses cross-origin writes, and never redirects credentials. [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/) are development-only, have no uptime guarantee, and get a new hostname on restart. Use a named tunnel and persistent machine, or a dedicated worker host, for durable availability. Neither was provisioned as a paid resource.

Build and package exact committed source:

```powershell
npm run build
uv run python scripts/package-site.py
git add .
git commit -m "Build QueryOtter"
git push
```

Push the same commit to the configured Sites source remote using a short-lived credential, save a version with its exact SHA and `artifacts/queryotter.tar.gz`, then deploy that version through the Sites connector. Never store Git tokens in source or remote URLs. The archive contains only built assets, hosting config and the Worker.

## Troubleshooting and limits

- **Worker offline:** published reports still render. Start PostgreSQL, API, worker and tunnel; update the hosted connector URL after tunnel restart.
- **Groq 429:** free-tier quota exhausted. Wait for reset; the worker retries once, then reports failure without provider secrets. No paid fallback.
- **Invalid connection:** check credentials, TLS verification, port, read-only grants and supported schema size. Detailed driver errors are suppressed to avoid disclosing URLs or records.
- **Comparison rejected:** supply a smaller deterministic result or supported ordering. The app will retain the original query.
- **Restart recovery:** a running job requeues once; a second interruption fails safely. Clean up only orphan disposable schemas when no jobs are active.
- **Owner account:** one configured owner login; anonymous sessions have isolated histories. Multi-user signup/OIDC and hosted always-on workers are not implemented.
- **Metadata cache:** per-job schema snapshot only; no cross-job cache because disposable schemas are recreated. Statistics are refreshed after seeding.
- **Model budget:** at most three candidates, one model decision plus one transient retry. No iterative follow-up decision or plateau-search loop.

CI builds the frontend and runs deterministic API/SQL/database tests against embedded PostgreSQL; it does not consume model credits. Node and Python dependency lockfiles are committed. See the published evaluation for actual model/SQL usage and outcomes, and `tests/` for reproducible safety, semantic and operations checks.
