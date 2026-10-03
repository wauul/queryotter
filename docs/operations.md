# Deployment and operations

Sentry configuration, privacy controls, source-map uploads, sampling, alert setup
and synthetic verification are documented in [Sentry operations](sentry.md).
Monitoring DSNs are optional; configured browser release builds require private
source-map uploads and an exact ingestion-origin CSP entry. Deploy both services
with the same Git-based release. Never install the build auth token on Railway.

The frontend is https://queryotter.vercel.app on Vercel. Its approved-route Node proxy uses server-only CONNECTOR_URL and SERVICE_TOKEN. The API/worker is https://api-worker-production-7d0a.up.railway.app on Railway, Amsterdam. Neon project queryotter (`quiet-rice-58196279`), branch `br-misty-truth-b1lldsfk`, AWS Frankfurt (`eu-central-1`) holds `queryotter_app` and separate `queryotter_experiments` databases.

Railway's existing Hobby deployment was explicitly approved as metered. One sleeping replica is capped at 0.5 CPU and 512 MiB; these resource limits are **not a dollar spending cap**. Cold starts and Neon scale-to-zero can delay the first operation. `/healthz` is public readiness; all application routes on the worker require the private service token. Never expose that token through a browser or VITE variable.

## Provision and deploy

1. Provision two PostgreSQL databases and separate restricted runtime roles. The application role owns only application tables in `qot_app`; the experiment role owns only the experiment database. Deny cross-database CONNECT. Use verified TLS and the direct endpoint for worker session behavior. `store.initialize()` creates/migrates application tables transactionally under its initialization lock.
2. Generate server SERVICE_TOKEN, SESSION_SECRET, ENCRYPTION_KEY and ADMIN_PASSWORD independently. Configure JOB_DATABASE_URL, EXPERIMENT_DATABASE_URL, Groq endpoint/model/key and the approved APP_ORIGIN from `.env.example`. Keep the encryption key in provider secret configuration separately from DB data/backups. No .env is committed.
3. Deploy the repository's non-root Python 3.12 Dockerfile to Railway. `backend.cloud` supervises FastAPI and a separate on-demand worker; the worker uses a PostgreSQL advisory lock to enforce one queue consumer, recovers interrupted work and closes connections while idle. Health check `/healthz`, target port 8000, one replica, bounded restart attempts. Do not set QOT_TEST_NETWORKS in cloud; the entrypoint rejects it.
4. Link the Vercel project. Set CONNECTOR_URL to the Railway HTTPS origin and the same SERVICE_TOKEN as sensitive server variables. Use `npm ci` and `npm run build:web`, output `dist`. The checked-in `vercel.json` configures Node proxy routes and a 60-second function limit.
5. Deploy with the authenticated official CLIs: `railway up --service api-worker --environment production` and `vercel --prod --yes`. Inspect provider deployment status and health, then verify anonymous and signed-in UI workflows. No desktop tunnel is required.

Provider variables can be set using CLI stdin, which avoids putting secrets into command-line history. Railway variable updates with `--skip-deploys` do not activate until redeployment. Confirm both services use matching tokens before cutting over. Never publish raw provider build logs without checking for credentials/DSNs.

## OAuth configuration

Register a confidential **web** OAuth application for each provider; clients and secrets are server-only Railway variables, not frontend variables. Exact production callbacks:

```text
https://queryotter.vercel.app/api/assistant/auth/github/callback
https://queryotter.vercel.app/api/assistant/auth/google/callback
https://queryotter.vercel.app/api/assistant/auth/microsoft/callback
```

GitHub requests read:user and user:email. Google/Microsoft request openid, profile, email. Microsoft supports work/school and personal accounts through the common v2 endpoint. Do not add database, Drive, mail, Graph write or billing permissions for sign-in. Google branding/publishing and Microsoft organizational consent policies may impose independent verification requirements; registration alone does not prove successful login.

The server uses authorization codes, PKCE, browser-bound one-use state and nonce. Google/Microsoft signed ID tokens validate signature, issuer, audience, nonce and expiry. Identities are keyed by provider subject and are not automatically merged by email. Sessions are opaque hashes, Secure/HttpOnly/SameSite=Lax, seven-day maximum with one-day idle expiry. Logout revokes the current session; deletion revokes all.

Production APP_ORIGIN is canonical. Preview deployments currently share that canonical origin and **are not suitable for OAuth login**: state cookies issued on a preview do not transfer to production. Test sign-in on the production host. For isolated preview OAuth, provision a separate exact callback/client and backend origin instead of a wildcard callback.

## Rotation, maintenance and recovery

- Rotate a database credential in its provider, then replace it through the connection editor and Test connection. Cached discovery is invalidated, revisions prevent stale job results, and plaintext secrets are never returned by the API. Removing a connection deletes related jobs/history/results/saved queries.
- Rotate Groq/OAuth secrets server-side and redeploy the worker. The current Groq key expires October 30, 2026. Do not replace it with an unapproved paid fallback. Remove expired/replaced provider secrets once a successful redeployment/login is verified.
- The registered Microsoft confidential-client secret expires March 29, 2027. Renew it in the app registration, update the server variable, redeploy and verify login before retiring the old secret.
- ENCRYPTION_KEY rotation needs a planned decrypt/re-encrypt migration with both keys, tested on a copy. Simply replacing the key makes encrypted connections/results unreadable. Keep it backed up securely apart from the database. SESSION_SECRET changes invalidate legacy operator sessions.
- Request-driven maintenance runs at most hourly and prunes expired results, selected history retention, expired OAuth state/sessions/connector tasks and abandoned demo accounts. Expired data is denied immediately even before physical cleanup. Idle deployments do not perform continuous deletion; the next request performs maintenance.
- Results have a 15-minute lifetime. History retention is 1–90 days. Account deletion removes active user/workspace records, model ledger, connectors and sessions. Exported files, browser downloads and provider backups have independent retention. Privacy must match these actual boundaries.
- Inspect sanitized job errors, observed durations, token ledger and platform CPU/memory. Do not log query records or secret configurations. One active job per user, 30 submissions/hour and one worker bound execution pressure. Public demo model quota is six operations/day globally; personal default is 20,000 tokens/day with conservative reservations.

Rollback Vercel and Railway together to a compatible code revision; do not reset durable Neon data to roll back UI. Test schema compatibility before restoring a provider database backup. Restore encryption configuration along with a recovered DB. Interrupted running jobs recover to a terminal state on worker startup. Never treat recovery as successful execution without checking persisted status/results.

## Operational blockers and testing boundaries

Only Neon and deployed SQLite copies have hosted engine verification. Other provider credentials/firewall routes must be supplied by their owners. Managed identity/IAM renewal and remote Turso transport are unverified or limited as documented. Free services can suspend/rate-limit workloads. SQL Server fixture license is Developer/non-production; do not turn it into a production database. Local fixture containers expose only loopback and their published passwords are test-only.

See [support](support-matrix.md), [provider setup](provider-guides.md), [evaluation](evaluation.md) and [private connector](local-connector.md). Issues should include sanitized reproduction steps and engine/version, never secrets or private records.
