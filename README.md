# QueryOtter

QueryOtter investigates slow PostgreSQL SELECTs using a real Groq model and a deterministic experiment executor. It reads plans, proposes rewrites or indexes, verifies results on independent fixtures, benchmarks surviving candidates, and recommends only measured improvements.

**Live app:** https://queryotter.vercel.app  
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
  UI[React + TypeScript on Vercel] --> Edge[Vercel Node.js API proxy]
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

The published September 30 evaluation contains **15 fixed cases**: 12 supported and three rejected before execution. Eight supported cases produced verified improvements, two were inconclusive, and two had no justified candidate. There were **zero regressions and zero provider errors** in the final suite. Checks passed for 9/10 cases where the agent proposed candidates; the NULL trap failed an empirical check and was excluded. All eight selected recommendations passed every fixture. The deterministic baseline sometimes outperformed the agent (notably the item join); those results are retained. The evaluation took 222.16 seconds including provider pacing, used 12 model calls, and publishes per-case token counts, SQL calls, runtime and index costs. Rejected candidates are not presented as verified recommendations.

For the customer-orders case, PostgreSQL 18.4 on 120,000 orders measured **4.483 ms → 0.027 ms** median, **166.04×**, with original/candidate MAD **0.115/0.001 ms**. All four fixtures passed. The selected index took **46.85 ms** to build and used **4,898,816 bytes**:

```sql
SELECT id, customer_id, total, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 50;

-- Reviewable recommendation; never applied to production automatically.
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at DESC, id DESC);
```

The SELECT itself was retained. Seven original samples were `[4.410, 4.253, 4.588, 4.483, 4.598, 4.636, 4.238]` ms; candidate samples were `[0.031, 0.029, 0.027, 0.029, 0.027, 0.026, 0.027]` ms. The fixed deterministic baseline measured 0.026 ms in its own run. These are warm-cache measurements on this synthetic workload, not general speedup guarantees.

Independent deterministic checks compare PostgreSQL type OIDs and typed values. Without ORDER BY, rows are compared as multisets including duplicate multiplicity; with ORDER BY, sequences must match. Edge tests specifically prove that a naive NOT IN → NOT EXISTS rewrite with NULLs and a DISTINCT rewrite over duplicates fail. Sample equality is **empirical evidence**, not mathematical equivalence.

Both original and candidate states get warmups. Two warm-up rounds precede seven measured rounds; the order alternates by round, with an additional equal warmup before each measurement. Candidate indexes are rebuilt in rollback transactions. ANALYZE runs consistently after seeding. No parallel query workers. PostgreSQL JSON EXPLAIN ANALYZE provides execution time and buffer counters. Displayed SQL latency is database execution time, excluding model/network overhead. No cold-cache claim is made. Median, minimum, maximum, samples and median absolute deviation (MAD) are exported. A win must beat a margin of `max(10% original median, 3 × max(original MAD, candidate MAD), 0.05 ms)`. Noisy or tiny differences are inconclusive.

Index build latency and storage are reported separately. Index maintenance/write overhead is disclosed but not measured. Choosing the fastest observed candidate among a small set can introduce selection bias; confirm with independent representative workloads. The original and fixed index baseline are measured independently in reproducibly seeded environments. Full case results, including no gain, errors and rejected inputs, are in `public/evaluation.json`. `database_seconds` measures client time in SQL execute calls including seeding/metadata, excluding streaming fetch, connection setup and model calls. Provider pricing estimates remain unavailable rather than assuming a paid cost.

## Deployment

The primary hosted app uses Vercel Hobby with `vercel.json`, static Vite `dist` assets, and the Node.js function `api/proxy.js`. The function forwards approved API requests to the separate worker connector; long-running investigations and durable SQLite/PostgreSQL storage remain on that host. `CONNECTOR_URL` and sensitive `SERVICE_TOKEN` belong in Vercel's Production and Preview environments. The Groq key, experiment URL, owner password, session secret and encryption key stay on the connector host. `.vercelignore` excludes local secrets, PostgreSQL files, Python environments and backend source from the web deployment.

For the current free demonstration, the official Cloudflare client runs:

```powershell
.data/bin/cloudflared.exe tunnel --url http://127.0.0.1:8000 --no-autoupdate
```

Use the returned URL for `CONNECTOR_URL`. The connector requires the service token, so visiting its tunnel directly cannot start jobs. The proxy removes caller-supplied service headers, forwards only approved API routes, refuses cross-origin writes, and never redirects credentials. [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/) are development-only, have no uptime guarantee, and get a new hostname on restart. Use a named tunnel and persistent machine, or a dedicated worker host, for durable availability. Neither was provisioned as a paid resource.

Build and deploy from this repository:

```powershell
npm run test:proxy
npm run build:web
vercel link --yes --scope wauuls-projects --project queryotter
vercel env add CONNECTOR_URL production,preview
vercel env add SERVICE_TOKEN production,preview --sensitive
vercel deploy --prod --yes
```

Run the two `env add` commands only during initial setup, entering the connector URL and the matching service token from the private worker environment. Use `vercel env update CONNECTOR_URL production,preview` and redeploy if the tunnel changes. Never pass credentials as command-line arguments or commit them. Deployment uses the authenticated Vercel CLI; automatic GitHub deployment is not connected for this project. Future updates require `vercel deploy --prod --yes` after validation.

The previous Sites deployment remains available; its optional build is `npm run build` followed by `uv run python scripts/package-site.py`, using `.openai/hosting.json` and `hosting/worker.js`. Vercel uses `build:web` and does not package the Sites Worker.

## Troubleshooting and limits

- **Worker offline:** published reports still render. Start PostgreSQL, API, worker and tunnel; update the hosted connector URL after tunnel restart.
- **Groq 429:** free-tier quota exhausted. Wait for reset; the worker retries once, then reports failure without provider secrets. No paid fallback.
- **Invalid connection:** check credentials, TLS verification, port, read-only grants and supported schema size. Detailed driver errors are suppressed to avoid disclosing URLs or records.
- **Comparison rejected:** supply a smaller deterministic result or supported ordering. The app will retain the original query.
- **Restart recovery:** a running job requeues once; a second interruption fails safely. Clean up only orphan disposable schemas when no jobs are active.
- **Owner account:** one configured owner login; anonymous sessions have isolated histories. Multi-user signup/OIDC and hosted always-on workers are not implemented.
- **Metadata cache:** per-job schema snapshot only; no cross-job cache because disposable schemas are recreated. Statistics are refreshed after seeding.
- **Model budget:** at most three candidates, one model decision plus one transient retry. No iterative follow-up decision or plateau-search loop.

CI builds the frontend and runs deterministic API/SQL/database tests against embedded PostgreSQL plus the Vercel proxy security checks; it does not consume model credits. Node and Python dependency lockfiles are committed. See the published evaluation for actual model/SQL usage and outcomes, and `tests/` for reproducible safety, semantic and operations checks.

## Verification evidence

Authenticated live plan-only work was also verified against a dedicated local read-only fixture: encrypted connection storage, a real Groq proposal from metadata and non-executing EXPLAIN, no record reads, no measured latency claims and no experimental indexes. See `docs/live-verification.json`. The fixture remains available as an owner-only saved connection. `scripts/verify-live.py` reproduces it on a local disposable cluster.

**46 tests passed locally**; GitHub CI also passed on Linux, covering parsing, unsafe functions/writes, NULL/duplicate/type/order traps, experiment role restoration, actual statement timeout, cancellation, persisted jobs, cross-session isolation, idempotency, encrypted-connection setup errors, CSRF and report export. Production build passes TypeScript and Vite. There is a dependency deprecation warning from Starlette's TestClient/httpx combination; it does not affect test results.

The deployed flow was tested with real Groq/SQL work: **4.452 ms → 0.025 ms** in a fresh hosted customer-orders investigation. Job history persisted; duplicate submission returned the same job; a separate browser session could not read, cancel or export it. Cancellation reached a persisted terminal state. Unsafe SQL was refused before execution. Owner authentication and redacted invalid connection errors were verified. Full evidence is in `docs/deployed-verification.json` (synthetic SQL and metadata only; no credentials or records).

To repeat deployed verification (requires the worker and tunnel online; uses the private owner password to avoid exhausting the public demo quota; makes one model run and one cancellable submission):

```powershell
uv run python scripts/verify-deployed.py https://queryotter.vercel.app --owner
```
