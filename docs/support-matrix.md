# Support and verification matrix

Evidence recorded September 30, 2026. A provider preset is connection guidance, not a hosted integration certificate. The live matrix consumes [adapter-verification.json](../public/adapter-verification.json); [real model cases](../public/nl-evaluation.json) and [timeouts](../public/execution-boundaries.json) provide separate evidence.

All nine engine adapters passed actual connection, discovery, native validation and bounded execution. All nine also passed one real Groq case with independently defined expected results. This limited suite does not establish general semantic accuracy.

| Engine | Verified version / environment | Plans | Profiling | Candidates | Controlled benchmark | Hosted evidence |
|---|---|---|---|---|---|---|
| PostgreSQL | 18.4 local; 18.6 Neon | EXPLAIN | Observed execution; portfolio ANALYZE | Supported, unmeasured until tested | Synthetic PostgreSQL portfolio | Neon, verified TLS/read-only role/native expected rows |
| MySQL | 8.4.11 official local image | EXPLAIN JSON | Observed execution | Supported | Unsupported | Requires credentials |
| MariaDB | 11.4.13 official local image | EXPLAIN JSON | Observed execution | Supported | Unsupported | Requires credentials |
| SQLite | 3.50.4 local; 3.46.1 Railway runtime | EXPLAIN QUERY PLAN | Observed execution | Supported | Second disposable uploaded copy | Deployed copy workflow verified |
| SQL Server | 2022 Developer, 16.0.4295.3 local | SHOWPLAN, permission-dependent | Observed execution | Supported | Unsupported | Requires credentials |
| CockroachDB | 25.4.0 local insecure fixture | Distributed EXPLAIN | Observed execution | Supported | Unsupported | Hosted TLS/authentication require credentials |
| MongoDB | 8.0.32 official local image | Non-executing explain | Observed execution | Supported | Unsupported | Requires credentials |
| Firestore | Official Standard Core emulator/API v1 | Unsupported | No equivalent planner profiler exposed | Limited native/index recommendations | Unsupported | Requires project/read-only IAM credentials |
| Realtime Database | Official emulator/REST v1 | Unsupported | No equivalent planner profiler exposed | Limited native/index recommendations | Unsupported | Requires database/read-only credentials |

Every adapter exposes cancellation/deadlines. Cancellation checkpoints are tested for all nine; actual in-flight native timeout fixtures passed for the six relational engines. This is not a claim of instantaneous interruption in every driver. Invalid passwords were actually rejected for PostgreSQL, MySQL, MariaDB, SQL Server and MongoDB. Malformed CA bundles were rejected; Neon additionally verifies a real hosted TLS path. Hosted provider-specific CA, mutual TLS, firewall and identity workflows remain separate configurations to verify.

## Providers and transports

| Provider preset | Engine reuse | Verification status |
|---|---|---|
| Neon | PostgreSQL | Hosted connection, discovery, native query/expected results and EXPLAIN verified |
| Supabase / Prisma Postgres / Render | PostgreSQL | Provider-specific guidance; requires credentials |
| MongoDB Atlas | MongoDB | Requires Atlas credentials and allowed egress route |
| PlanetScale | MySQL or PostgreSQL, selected explicitly | Requires branch credentials; Vitess behavior not verified |
| Turso/libSQL | SQLite dialect over native HTTP v2 | Implemented transport, **not successfully tested** against hosted service; cancellation/index benchmarks unavailable |
| Railway | PostgreSQL/MySQL/MongoDB | API/worker hosting verified; database preset needs separate database credentials |
| AWS RDS/Aurora | Selected relational engine | Requires credentials/CA/network route; IAM tokens not exposed |
| Google Cloud SQL | PostgreSQL/MySQL/SQL Server | Requires credentials; private/mutual-TLS/IAM through scoped connector and official proxy |
| Azure database services | PostgreSQL/MySQL/SQL Server/MongoDB | Requires credentials; managed identity and Cosmos compatibility unverified |
| Firebase | Firestore Standard Core / Realtime | Official emulator verification; hosted service requires credentials |
| Generic self-hosted | Selected engine | Local engine fixtures; private network connector required |

Prisma import is model context, not an engine or connection. Firestore Enterprise Mongo-compatible mode is outside Standard Core support. Managed IAM/Entra access-token renewal and automatic provider OAuth provisioning are not implemented. No logo or successful connection is used as evidence of end-to-end provider verification.
