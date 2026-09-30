"""Provider presets are connection guidance, not a claim of hosted verification."""

from urllib.parse import urlparse, unquote
from backend.adapters.base import AdapterError

PRESETS = [
    {
        "id": "neon",
        "name": "Neon",
        "engines": ["postgresql"],
        "docs": "https://neon.com/docs/connect/connect-securely",
        "instructions": "Copy a direct PostgreSQL connection string from Connect. Use sslmode=verify-full and a dedicated SELECT-only role. Direct connections preserve session settings; transaction pooling can restrict session behavior.",
        "default_schema": "public",
        "tls": "Verified TLS; system CA certificates",
        "authentication": "Database username/password; no provider OAuth needed",
    },
    {
        "id": "supabase",
        "name": "Supabase",
        "engines": ["postgresql"],
        "docs": "https://supabase.com/docs/guides/database/connecting-to-postgres",
        "instructions": "Use a direct URL when IPv6 is available, or the session pooler on port 5432 for IPv4. Avoid transaction pooler port 6543 for session-based inspection. Create a restricted PostgreSQL login; the API anon/service-role key is not a database password.",
        "default_schema": "public",
        "tls": "Verified TLS; use the project CA where required",
        "authentication": "Dedicated PostgreSQL username/password",
    },
    {
        "id": "prisma-postgres",
        "name": "Prisma Postgres",
        "engines": ["postgresql"],
        "docs": "https://www.prisma.io/docs/postgres/database/connecting-to-your-database",
        "instructions": "Use the direct PostgreSQL TCP URL from Prisma Console. A prisma:// Accelerate URL is not a native SQL connection. Optional schema.prisma import supplies relationship context, then actual database discovery validates it.",
        "default_schema": "public",
        "tls": "Verified TLS",
        "authentication": "Database credentials from Prisma Console",
    },
    {
        "id": "atlas",
        "name": "MongoDB Atlas",
        "engines": ["mongodb"],
        "docs": "https://www.mongodb.com/docs/atlas/driver-connection/",
        "instructions": "Create a database user with read on one database. Copy the SRV driver URL and include the database name. Add the worker’s permitted egress IPs to the Atlas access list; do not open every IP for convenience.",
        "tls": "Verified TLS for all SRV members",
        "authentication": "SCRAM database user; Atlas account login is separate",
    },
    {
        "id": "planetscale",
        "name": "PlanetScale",
        "engines": ["mysql", "postgresql"],
        "docs": "https://github.com/planetscale/connection-examples",
        "instructions": "Choose the actual PlanetScale engine. Use branch connection credentials with read-only privileges and TLS. Vitess/MySQL and PlanetScale Postgres are different engines and use different URLs.",
        "default_schema": "public",
        "tls": "Verified TLS",
        "authentication": "Branch database username/password",
    },
    {
        "id": "turso",
        "name": "Turso / libSQL",
        "engines": ["sqlite"],
        "docs": "https://docs.turso.tech/sdk/http/reference",
        "instructions": "Use the libsql:// or turso:// database URL and a separate read-only database token. SQL-over-HTTP sets query_only on every connection. A local uploaded SQLite copy is also available.",
        "tls": "HTTPS for remote libSQL; uploaded copies use no network",
        "authentication": "Remote libSQL tokens are distinct from SQLite uploads",
        "limitation": "Remote transport does not expose server cancellation or experimental index benchmarks. Hosted token verification requires user credentials.",
    },
    {
        "id": "railway",
        "name": "Railway",
        "engines": ["postgresql", "mysql", "mongodb"],
        "docs": "https://docs.railway.com/guides/postgresql",
        "instructions": "Choose the database engine and use its public TCP proxy endpoint with a restricted database role and verified TLS. *.railway.internal is private to Railway; use a scoped connector in that network when there is no verified public TLS endpoint.",
        "default_schema": "public",
        "tls": "Verified database TLS; a TCP proxy does not supply PostgreSQL TLS by itself",
        "authentication": "Database credentials; Railway project tokens do not authenticate database queries",
    },
    {
        "id": "render",
        "name": "Render",
        "engines": ["postgresql"],
        "docs": "https://render.com/docs/databases",
        "instructions": "Copy the external PostgreSQL URL, configure permitted access, and create SELECT-only credentials. Internal Render URLs require a connector deployed in that network.",
        "default_schema": "public",
        "tls": "Verified TLS on the external endpoint",
        "authentication": "PostgreSQL username/password",
    },
    {
        "id": "aws",
        "name": "AWS RDS / Aurora",
        "engines": ["postgresql", "mysql", "mariadb", "sqlserver"],
        "docs": "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html",
        "instructions": "Select the actual engine and database endpoint. Use a dedicated SQL login and a public allowed network route or a connector in the VPC. RDS CA certificates may need a custom CA bundle. IAM token authentication is not yet exposed in this form; do not substitute an AWS access key for a database password.",
        "default_schema": "public",
        "tls": "Verified TLS using the current RDS CA bundle",
        "authentication": "Dedicated database login; IAM token workflow limited",
    },
    {
        "id": "cloud-sql",
        "name": "Google Cloud SQL",
        "engines": ["postgresql", "mysql", "sqlserver"],
        "docs": "https://cloud.google.com/sql/docs/postgres/connect-overview",
        "instructions": "Choose the engine. Public IP connections require authorized networks and verified certificates. Use a scoped local connector with the official Cloud SQL Auth Proxy for private-IP or IAM workflows; never assume cloud services can reach private addresses.",
        "default_schema": "public",
        "tls": "Verified server TLS; mutual TLS configurations require the connector/proxy path",
        "authentication": "Database login or official Auth Proxy configured outside the app",
    },
    {
        "id": "azure",
        "name": "Azure database services",
        "engines": ["postgresql", "mysql", "sqlserver", "mongodb"],
        "docs": "https://learn.microsoft.com/en-us/azure/azure-sql/database/connect-query-content-reference-guide",
        "instructions": "Choose the actual Azure engine. Use its public hostname, firewall allowlist and restricted database login. SQL Server requires SELECT and optionally SHOWPLAN. Microsoft Entra token authentication and Cosmos-specific Mongo compatibility need separate verification; they are not implied by this preset.",
        "default_schema": "dbo",
        "tls": "Verified TLS; never TrustServerCertificate",
        "authentication": "Dedicated database login; managed identity workflow limited",
    },
    {
        "id": "firebase",
        "name": "Firebase",
        "engines": ["firestore", "firebase_realtime"],
        "docs": "https://firebase.google.com/docs/firestore/query-data/get-data",
        "instructions": "Select Firestore Standard Core or Realtime Database. Use a dedicated read-only Google service account JSON key and the exact project/database. Firestore IAM credentials bypass Security Rules. Document inference reads at most 20 documents per collection locally and never sends record values to the model.",
        "tls": "Official Google/Firebase HTTPS endpoints only",
        "authentication": "Read-only service account; browser app API keys are not server credentials",
    },
    {
        "id": "generic",
        "name": "Generic / self-hosted",
        "engines": [
            "postgresql",
            "mysql",
            "mariadb",
            "sqlite",
            "mongodb",
            "sqlserver",
            "cockroachdb",
            "firestore",
            "firebase_realtime",
        ],
        "docs": "https://github.com/wauul/queryotter",
        "instructions": "Select the real engine. Use a public verified-TLS address or install the scoped local connector for localhost/private networks. SQLite uses an uploaded copy.",
        "tls": "Verified TLS for cloud connections; connector-local transport is explicitly configured",
        "authentication": "Engine-specific read-only credentials",
    },
]


def presets():
    return [
        {
            **p,
            "documentation_checked": "2026-09-30",
            "hosted_verification": "Requires user credentials; see engine evidence separately",
        }
        for p in PRESETS
    ]


def parse_url(value):
    try:
        u = urlparse(value)
        port = u.port
    except ValueError:
        raise AdapterError(
            "The connection URL has an invalid host or port.", "connection_format"
        ) from None
    mapping = {
        "postgres": "postgresql",
        "postgresql": "postgresql",
        "mysql": "mysql",
        "mariadb": "mariadb",
        "mongodb": "mongodb",
        "mongodb+srv": "mongodb",
        "mssql": "sqlserver",
        "sqlserver": "sqlserver",
        "libsql": "sqlite",
        "turso": "sqlite",
    }
    if u.scheme not in mapping:
        raise AdapterError(
            "This URL scheme is not a supported native database connection. Choose Firebase or SQLite separately.",
            "connection_format",
        )
    if not u.hostname:
        raise AdapterError("The URL needs a database hostname.", "connection_format")
    return {
        "engine": mapping[u.scheme],
        "host": u.hostname,
        "port": port,
        "database": unquote(u.path.strip("/")),
        "username": unquote(u.username or ""),
        "password_present": bool(u.password),
        "masked_url": u.scheme
        + "://"
        + (unquote(u.username or "") + ":••••@" if u.username else "")
        + u.hostname
        + (":" + str(u.port) if u.port else "")
        + "/"
        + unquote(u.path.strip("/")),
    }
