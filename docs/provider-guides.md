# Provider connection guides

Choose the provider first and then the actual engine. A preset configures documented connection guidance; it does not provision a database or prove hosted compatibility. These guides were checked against linked primary documentation September 30, 2026. Tested engine versions and environments are in the [support matrix](support-matrix.md).

For every provider: create a dedicated read-only login scoped to one database/schema, copy the native connection string, paste it into Connections or use the guided host/port/database/username/password form, select verified TLS and any required CA certificate, then Test connection. Review the actual engine/version and discovered schema. Generate a native draft, validate it, and explicitly Run a bounded query. A green connection status is not evidence that all business questions or optimization features work.

Credentials stay encrypted server-side and never enter Groq context. Editing replaces secrets without returning their old plaintext; rotation invalidates metadata and pending stale configurations. Removal deletes associated application data. Public cloud endpoints must resolve to public addresses. Private/internal endpoints need the [outbound scoped connector](local-connector.md).

## Neon

In the project Connect panel choose the actual branch, database and a restricted role. Use the direct PostgreSQL endpoint for discovery/session settings and `sslmode=verify-full`. Pooled/transaction URLs can restrict session behavior, so they are not the default. System CA verification works for the tested Neon production endpoint. [Secure connections](https://neon.com/docs/connect/connect-securely), [connection pooling](https://neon.com/docs/connect/connection-pooling).

QueryOtter's own Neon application store is separate from a user's selected connection. The hosted synthetic demo uses a SELECT-only reader; users never receive application runtime credentials.

## Supabase

Use Connect → direct PostgreSQL URL when IPv6 is available, or the session pooler on port 5432 for IPv4. The transaction pooler on port 6543 is unsuitable for this adapter's session controls. Supply the dedicated PostgreSQL password and project CA when required; `anon` and `service_role` API keys are not database passwords. Choose the desired schema; RLS policies and the database role determine visibility. Avoid owners/service-role access. [Connection methods](https://supabase.com/docs/guides/database/connecting-to-postgres), [SSL enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement).

## Prisma Postgres

Choose a direct PostgreSQL TCP URL from Prisma Console. `prisma://` Accelerate/ORM URLs are not native database endpoints. Use verified TLS and restricted native credentials. Importing schema.prisma optionally provides model names/relations, but actual discovery remains authoritative; mapped names must exist. [Direct connections](https://www.prisma.io/docs/postgres/database/connecting-to-your-database), [schema mappings](https://www.prisma.io/docs/orm/prisma-schema/data-model/database-mapping).

## MongoDB Atlas

Create an Atlas **database user**, with `read` on the chosen database, separate from Atlas account login. Copy the driver SRV URL including the database name and encoded credentials. Retain TLS/certificate verification for every resolved cluster member. Restrict the access list to the worker's allowed egress route. Do not use `0.0.0.0/0` as a shortcut; an ordinary dynamic-egress deployment may need a scoped connector with a stable permitted route. Optional document inference is incomplete. [Driver connections](https://www.mongodb.com/docs/atlas/driver-connection/), [database users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/).

## PlanetScale

Select MySQL/Vitess or PostgreSQL explicitly, then choose branch credentials with read-only privileges and the native URL/TLS configuration. Those engines do not share a dialect. Vitess-specific planning/session behavior is unverified in the local MySQL fixture; test it before relying on a query. [Official connection examples](https://github.com/planetscale/connection-examples), [PlanetScale documentation](https://planetscale.com/docs).

## Turso / libSQL

Use the actual libsql:// or turso:// database URL and a separate **read-only** database token in the SQLite remote form. Native HTTP v2 requests enforce query_only and parameterized values over HTTPS. Uploaded SQLite copies use no token/network. Remote transport is implemented but has **no successful hosted transport verification yet**; it does not expose server cancellation or controlled index benchmarks. Do not mark this preset verified merely because SQLite-copy tests pass. [HTTP v2](https://docs.turso.tech/sdk/http/reference), [database tokens](https://docs.turso.tech/cli/db/tokens/create).

## Railway

Choose the actual PostgreSQL, MySQL or MongoDB service. A public TCP proxy provides a network route, not automatic database TLS. Use verified database TLS and a restricted role on that endpoint. If the image/service has no verified public TLS or only `*.railway.internal`, run the connector inside its network. Railway account/project tokens do not authenticate database reads. QueryOtter's Railway worker deployment does not verify every Railway database template. [PostgreSQL guide](https://docs.railway.com/guides/postgresql), [TCP proxy](https://docs.railway.com/guides/tcp-proxy).

## Render

Use the external PostgreSQL URL and restricted SQL credentials, with verified TLS and permitted network access. Internal URLs are reachable only from Render's network; install a scoped connector there. Check suspension/expiry and provider limits separately. [Databases](https://render.com/docs/databases), [PostgreSQL networking](https://render.com/docs/postgresql-creating-connecting).

## AWS RDS / Aurora

Select the real engine and reader endpoint/database. Create a SELECT-only database login. Use the current region-appropriate RDS CA bundle and verify the endpoint hostname. A private VPC endpoint requires the connector on an allowed machine; public access still needs security-group rules and a permitted egress route. IAM database token acquisition/renewal is not exposed by QueryOtter's direct form; an AWS access key is not a SQL password. Aurora/engine-specific behavior needs credentials and hosted testing. [TLS certificates](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html), [IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html).

## Google Cloud SQL

Choose PostgreSQL, MySQL or SQL Server. Public-IP connections need authorized networks and verified server certificates; direct client-certificate/mutual-TLS configuration is not exposed. For private IP, IAM or client-certificate requirements, run the official Cloud SQL Auth Proxy alongside a scoped QueryOtter connector. Configure the proxy's Google identity outside QueryOtter and keep connector profiles restricted to its local port. [Connection overview](https://cloud.google.com/sql/docs/postgres/connect-overview), [Auth Proxy](https://cloud.google.com/sql/docs/postgres/sql-proxy).

## Azure database services

Choose PostgreSQL Flexible Server, MySQL Flexible Server, Azure SQL/SQL Server or an actual MongoDB endpoint. Use the exact public hostname, firewall allowlist, verified TLS/current CA and dedicated database login. SQL Server requires SELECT and optionally SHOWPLAN; never enable TrustServerCertificate. Microsoft OAuth login to QueryOtter is separate from Entra database authentication. Managed identity renewal and Cosmos Mongo API compatibility are unverified. [Azure SQL connections](https://learn.microsoft.com/en-us/azure/azure-sql/database/connect-query-content-reference-guide), [PostgreSQL TLS](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/security-tls).

## Firebase

Choose **Firestore Standard Core** or Realtime Database explicitly. Supply the exact project/database and a dedicated read-only service account JSON in the secret form. Browser Firebase API keys are not server credentials. Firestore server IAM credentials bypass Security Rules: grant the minimum viewer role and do not use Owner/Editor or a default admin service account. Optional inference samples at most 20 documents per collection within the adapter; values do not enter model context.

Realtime Database needs its exact official HTTPS database URL and appropriately restricted credentials. Native queries use one order key; `.indexOn` and composite Firestore indexes are database-owner configuration, never applied automatically. The adapter cannot generically prove the service account's IAM read-only policy; verify it in Google IAM before connecting. Hosted IAM/network/index behavior is unverified; official emulators passed. [Firestore reads](https://firebase.google.com/docs/firestore/query-data/get-data), [IAM roles](https://firebase.google.com/docs/firestore/security/iam), [Realtime REST authentication](https://firebase.google.com/docs/database/rest/auth), [Realtime indexing](https://firebase.google.com/docs/database/security/indexing-data).

## Generic and self-hosted

Choose the true engine/dialect. Use a publicly routable verified-TLS endpoint or the scoped connector for localhost/private networks. Upload SQLite copies up to 2 MiB; queries run on a copy, not the source file. Discovery supports ordinary tables, not arbitrary views or extension/UDF access. All Mongo SRV members must fit network restrictions. Firestore Enterprise Mongo-compatible mode is a separate product from Standard Core.

## Restricted role examples

Have the database owner run these templates after substituting actual database/schema/table names. Generate passwords outside source control; do not paste them into model prompts. Audit inherited/default/public grants too. Existing write permissions must be revoked, not merely hidden by a UI checkbox.

PostgreSQL/CockroachDB concept (syntax/grants vary by deployed version):

```sql
CREATE ROLE qot_reader LOGIN PASSWORD 'REPLACE_PRIVATELY';
GRANT CONNECT ON DATABASE shop TO qot_reader;
GRANT USAGE ON SCHEMA public TO qot_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO qot_reader;
ALTER ROLE qot_reader SET default_transaction_read_only = on;
-- Owner: review inherited roles, PUBLIC CREATE and future-table grants.
```

PostgreSQL's PUBLIC schema CREATE/temporary permissions or inherited write roles can make this insufficient; revoke unwanted permissions as the owner. Cockroach's permissions/session options need its native documentation. QueryOtter audits effective access on discovered tables and rejects privileged writers.

MySQL/MariaDB:

```sql
CREATE USER 'qot_reader'@'PERMITTED_SOURCE' IDENTIFIED BY 'REPLACE_PRIVATELY';
GRANT SELECT, SHOW VIEW ON shop.* TO 'qot_reader'@'PERMITTED_SOURCE';
-- Do not grant FILE, EXECUTE, CREATE, UPDATE, DELETE or administrator roles.
```

SQL Server (SQL authentication where enabled):

```sql
CREATE LOGIN qot_reader WITH PASSWORD = 'REPLACE_PRIVATELY';
USE shop;
CREATE USER qot_reader FOR LOGIN qot_reader;
GRANT SELECT ON SCHEMA::dbo TO qot_reader;
GRANT SHOWPLAN TO qot_reader; -- optional; needed only for plan evidence
-- Audit role memberships and inherited object/schema/database grants.
```

MongoDB:

```javascript
use shop
db.createUser({user: "qot_reader", pwd: "REPLACE_PRIVATELY", roles: [{role: "read", db: "shop"}]})
```

Atlas users should be created through the documented Atlas database-user flow. SQLite uploads use enforced read-only copy controls; Firebase uses IAM/native Rules rather than these SQL roles. If provider administration forbids creating/auditing the appropriate role, report the limitation instead of using an unrestricted owner credential.
