# Sentry operations

Monitoring is optional per process. An empty DSN disables it. This implementation
does not provision a paid feature or introduce a production crash endpoint.

## Setup and release builds

The `queryotter` organization uses the existing `#queryotter` team. Its projects
are `queryotter-web` (React), `queryotter-proxy` (Node) and `queryotter-python`
(FastAPI/API, worker and supervisor). The browser ingestion origin is
`https://o4512192420249600.ingest.de.sentry.io`, explicitly allowed by the CSP.
The organization build token `QueryOtter source maps and releases` has `org:ci`
scope; production and preview Vercel secrets contain it. Railway has no build token.

Reuse the organization's existing QueryOtter projects when appropriate. Use a
browser React project/key for `VITE_SENTRY_DSN`, and separate server project keys
for `SENTRY_PROXY_DSN` and `SENTRY_PYTHON_DSN` (the Python API, supervisor and
worker share a project, distinguished by `component`). Keep the server DSNs on
Vercel/Railway; do not expose them through VITE variables.

Set `SENTRY_ENVIRONMENT` explicitly to `production`, `preview`, `staging` or
`development`. The release is `queryotter@<full 40-character Git SHA>` everywhere.
Deploy the same committed revision to both providers. Vercel uses
`VERCEL_GIT_COMMIT_SHA`; Railway uses `RAILWAY_GIT_COMMIT_SHA`. For local CLI
deployments, explicitly set `SENTRY_RELEASE` on both services before deploying.
The Docker build also accepts `--build-arg QOT_GIT_SHA=<sha>` as a fallback.

Before enabling the browser DSN, add **only its exact HTTPS origin** to the
`connect-src` directive in `vercel.json`. Preserve all other CSP directives.
Do not use `*.sentry.io`, weaken `script-src`, or invent an ingestion host.
The build checks that the configured DSN origin appears in the CSP.

Provide `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` **only to the build
environment/CI**. Leave build secrets blank in runtime `.env` files. Never use
`VITE_SENTRY_AUTH_TOKEN`, commit tokens or put them in command arguments.
Configure the token as a sensitive Vercel build variable and a GitHub Actions
secret; project/org/browser DSN are Actions variables. Use an organization build
token scoped to source-map/release uploads. Do not install it on Railway.

`npm run build:web` uploads hidden browser maps through the official Vite plugin
and deletes them after upload. A configured monitored build fails when credentials,
Git release or exact CSP origin are missing; upload errors also fail the build.
`npm run build` additionally packages Sites assets and independently skips `.map`
files. Local builds without a browser DSN generate no maps or upload requests.
CI uses these same commands and keeps the build token out of test/runtime steps.
Server proxy stacks retain original JavaScript; Python stacks retain repository
filenames/line numbers. Their source-map upload is unnecessary.

The JS SDK uses the compatible 10.x API with explicit `sendDefaultPii: false`
and static transaction tracing; Python uses 2.x. Upgrading to JS 11 requires
migrating its data-collection and streamed-span APIs and rerunning privacy tests.
Do not simply replace the versions and assume the callbacks still execute.

## Sampling, privacy and delivery

Browser/server tracing defaults to 10%, separately configurable from 0–1 with
`VITE_SENTRY_TRACES_SAMPLE_RATE` / `SENTRY_TRACES_SAMPLE_RATE`. Errors are captured
at 100%. Replay, profiling, telemetry logs, metrics and automatic sessions are
disabled. There is no Replay opt-in in this implementation.

The SDKs send neither default PII nor Python locals/source context. Only FastAPI,
Starlette and deduplication integrations run in Python. Explicit Node spans avoid
ESM/preload requirements and automatic fetch/DB/logging/model instrumentation.
The browser installs automatic error handling, deduplication and browser tracing;
it installs no DOM/console breadcrumb or replay integration. Network request and
response bodies are never collected.

Callbacks rebuild events from an allowlist: component/operation, Git release,
environment, timestamps, random trace/span IDs, safe status and stack locations.
Messages, source snippets, locals, breadcrumb text, arbitrary context/attributes,
request bodies/headers/cookies, user identity, prompts, queries, schema names,
model output and record values are discarded. Routes replace opaque resource IDs
and remove query strings; unknown routes/names collapse to `/`. Stack function
names are omitted. Browser asset filenames retain debug-ID matching for source
maps. Error category plus stack location supplies grouping. Attachments are dropped.
Sentry receives transport network metadata as the ingestion provider even though
application events do not attach IP/account identity. Set appropriate project
retention and server-side scrubbing; Sentry retention is independent of history.

Tracing is restricted to same-origin browser `/api/` requests and the proxy's
configured HTTPS `CONNECTOR_URL`. Redirects are not followed. Proxy/API ingress
validates the trace header and retains only trace ID and sampling baggage.
Foreign baggage, users and transaction/release text are discarded. Outbound
Python propagation is disabled for Groq, OAuth and user-selected databases.
`jobs.trace_context` stores this minimal metadata, using an idempotent nullable
column migration for PostgreSQL/SQLite. It is never exposed in job responses and
adds no credential/prompt/result fields to the queue. Worker scopes are reset
for every job, including jobs with missing/malformed trace metadata.

Handled network/5xx/invalid-response browser failures alert; ordinary 4xx UI
responses do not. React's boundary reports caught render failures; root hooks
report uncaught/recoverable errors without a second caught hook. Proxy upstream
exceptions/timeouts are reported once and preserve their existing 503 response.
Python cancellations, validation, unsupported operations, AdapterError outcomes
and ordinary authentication failures do not alert. Unexpected swallowed worker,
generation and benchmark errors are reported while preserving job state behavior.
Supervisor crashes/unexpected worker exits are reported. Job and request scopes
are isolated. Delivery flushes for at most 1.5 seconds at proxy completion and
graceful process/API shutdown; monitoring failures are best effort. SIGTERM in
workers unwinds driver cleanup before flushing; abrupt kills cannot guarantee
delivery. Existing deadline and recovery semantics continue to apply.

## Alerts (requires authenticated organization access)

Inspect existing projects, alerts, available plan features and notification
actions first. Reuse an existing approved team/channel rather than inventing a
recipient. Do not enable paid performance features or upgrade a plan.

Recommended starting configuration:

- Error issue rule: production only, new issue or regression, 30-minute action
  cooldown, using the organization's
  existing approved notification action. Route by `component` to ownership.
  Add a separate sustained-frequency rule (five events in five minutes) where
  supported; do not combine new-issue and frequency conditions with AND.
- If supported on the existing plan: transaction-duration metric alert per
  component, p95 above 5 seconds for proxy/API or 120 seconds for jobs over a
  15-minute window, minimum 20 transactions before treating it as actionable.
  Use warning then critical thresholds and the same approved destination.
- Evaluate baseline traffic before tuning thresholds. Low-volume/10% sampled
  projects may need a longer window. Inspect quota consumption before increasing
  trace sampling. Synthetic smoke issues should be resolved after verification.

Use the supported [issue rule API](https://docs.sentry.io/api/alerts/create-an-alert-rule-for-a-project/)
and [metric alert API](https://docs.sentry.io/api/alerts/create-a-metric-alert-rule/)
or the Sentry UI. Performance API availability/threshold aggregation is plan
dependent: inspect support before creating rules. A proposal in this document is
not evidence that an alert or notification was configured.

## Verification

Local checks intercept actual SDK envelopes and do not consume Sentry quota:

```powershell
npm run test:proxy
npm run test:theme
npm run test:i18n
npm run test:sentry
# CI installs Chromium; Windows can use installed Edge for this headless test.
npx playwright install chromium
npm run test:sentry:browser
npm run test:sentry:maps
npm run test:backend
npm run build:web
npm run build
node scripts/sentry-smoke.mjs
uv run python -m integration.sentry_smoke --component api
uv run python -m integration.sentry_smoke --component worker
uv run python -m integration.sentry_smoke --component supervisor
```

`test:backend` starts a separate temporary loopback PostgreSQL on port 55439 and
removes only its own fixture after running all Python tests. It does not change
`.env` or the existing developer database. Browser fixtures live under `tests/`
and are excluded from production Vite output; they deliberately exercise uncaught
errors, unhandled rejections, caught render errors, expected 401s and handled 503s
in both languages. Tests inspect serialized envelopes for realistic synthetic
secrets, duplicate counts, isolation, trace continuity and Git/environment tags.
Set `QOT_TEST_PYTHON` to an interpreter path to run in an isolated environment
matching CI's Python 3.12. On this Windows host the Python 3.14 PostgreSQL
concurrency check times out; the complete suite passes on Python 3.12.

For actual ingestion, run the CLI smokes with `--send` and the appropriate runtime
DSN/environment/release injected securely. These scripts use only synthetic data
and a disposable local store; they don't submit real production jobs. Check the
printed event IDs in Sentry. The scripts explicitly report ingestion unverified:
a local SDK flush alone does not prove receipt or successful symbolication.
`node scripts/sentry-browser-smoke.mjs --send` serves the built `dist` locally,
breaks only local API requests, and sends real browser events using its configured
DSN. No smoke code enters the production bundle. Use a `test` environment build
and verify the printed event IDs/debug IDs in Sentry.

For a deployed verification after credentials and deployment are authorized:

1. Configure DSNs, build token, exact CSP origin and shared Git release. Deploy
   both providers using the existing official CLIs. Verify build upload succeeds.
2. Check uploaded debug-ID artifacts in the browser project. On an operator's
   browser, use a temporary console `setTimeout(() => { throw new Error('QueryOtter synthetic browser smoke'); }, 0)`;
   inspect that event's release/environment/component and original TypeScript
   stack frames from an application failure exercised through the UI. A console
   stack alone does not verify TypeScript source-map resolution.
3. Run only synthetic UI job data, follow its trace from browser → proxy → API →
   queued worker and confirm the same trace ID with correct parent spans. Inspect
   each component's event, privacy filtering and alert routing in Sentry itself.
4. Confirm deployed assets contain no `.map` or build token; verify `.map` URLs
   cannot serve source content. Resolve synthetic issues and remove any temporary
   console/test hooks. Do not add public production crash routes.

Official references: [React setup](https://docs.sentry.io/platforms/javascript/guides/react/),
[Vite maps](https://docs.sentry.io/platforms/javascript/guides/react/sourcemaps/uploading/vite/),
[Python options](https://docs.sentry.io/platforms/python/configuration/options/),
[custom queue propagation](https://docs.sentry.io/platforms/python/tracing/distributed-tracing/custom-trace-propagation/).
