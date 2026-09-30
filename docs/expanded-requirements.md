# Expanded QueryOtter delivery checklist

The expanded user request is the acceptance contract. PostgreSQL-only support is superseded. This checklist is maintained against implementation and test evidence; unchecked work is not represented as complete.

- [x] Public landing page and working safe examples
- [x] GitHub, Google and Microsoft OAuth with verified sessions, logout and deletion
- [x] First-run onboarding, personal workspaces and cross-user authorization tests
- [x] Connection presets, pasted strings, guided fields, TLS, tests, rotation and removal
- [x] Schema explorer and cache invalidation
- [x] Natural-language generation, assumptions, clarification, refinement and review before Run
- [x] Native query editor, bounded read-only results, pagination and cancellation
- [x] Saved queries, retention, history, account export and deletion
- [x] Evidence-backed optimization and controlled-copy benchmarks
- [x] PostgreSQL adapter discovery/generation/validation/execution evaluation
- [x] MySQL adapter discovery/generation/validation/execution evaluation
- [x] MariaDB adapter discovery/generation/validation/execution evaluation
- [x] SQLite uploads, restrictive copy execution and evaluation
- [x] SQL Server adapter discovery/generation/validation/execution evaluation
- [x] CockroachDB adapter discovery/generation/validation/execution evaluation
- [x] MongoDB adapter discovery/generation/validation/execution evaluation
- [x] Firestore native adapter and official emulator evaluation
- [x] Realtime Database native adapter and official emulator evaluation
- [x] Provider-specific guides and truthful visible support matrix
- [x] Optional Prisma schema context import
- [x] Scoped local/private network connector and SSRF protection
- [x] Model/tool/token/duration/database usage and per-user budgets
- [x] Product documentation, FAQ, support, privacy and terms
- [x] Accessible responsive loading, empty, error and success states
- [x] Deployed UI verification: all three OAuth personal-account flows and logout, isolated onboarding/workspaces, Neon/SQLite connections, schema discovery/rotation, real Groq generation/refinement, explicit execution, pagination, save/reload/history, queued cancellation, CSV/JSON/report/account exports, controlled SQLite/PostgreSQL benchmarks and approved disposable-account deletion. Direct Neon checks confirmed deletion of active data and preservation of OAuth identities. See public/deployed-ui-verification.json.
- [x] Comprehensive setup, seeded data, operations, actual evaluation and limitations

## Known external dependencies

Railway deployment on the existing metered Hobby workspace was explicitly approved and is live. GitHub, Google and Microsoft personal-account sign-in are registered and verified on production. Microsoft organization consent can require publisher verification or tenant-admin approval; the user owns that external identity/domain process. Only Neon and deployed SQLite copies have hosted engine verification. Other engine tests use official local services/emulators and do not imply hosted-provider verification. Remote libSQL transport remains unverified; supported native IAM/managed-identity renewal requires separate integration. See the support matrix and primary provider guides for precise limits.

## Architecture decisions

Keep React/Vite, FastAPI, the durable Neon job queue, separate supervised worker process and Groq. Add capability-based engine adapters, revocable account sessions and workspace-scoped persistence. Put private results in encrypted, expiring storage; send schema/type metadata and query context to the model, never credentials or result records. Generation, execution and optimization are separate jobs; generating a draft does not execute it. Preserve the original deterministic PostgreSQL optimization suite.
