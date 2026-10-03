import os, time, uuid, json, contextvars
from contextlib import contextmanager
import psycopg
from psycopg import sql
from dotenv import load_dotenv
from backend.connections import tls_options
from backend import monitoring

load_dotenv()
METRICS = contextvars.ContextVar("database_metrics", default=None)


class MeasuredConnection(psycopg.Connection):
    def execute(self, *args, **kwargs):
        start = time.monotonic()
        try:
            return super().execute(*args, **kwargs)
        finally:
            m = METRICS.get()
            if m is not None:
                m["calls"] += 1
                m["seconds"] += time.monotonic() - start


def connect():
    c = MeasuredConnection.connect(
        os.environ["EXPERIMENT_DATABASE_URL"],
        autocommit=True,
        connect_timeout=10,
        **tls_options(os.environ["EXPERIMENT_DATABASE_URL"]),
    )
    c.execute("SET statement_timeout='3s'")
    c.execute("SET lock_timeout='500ms'")
    return c


def cleanup_abandoned():
    """Call only while holding the global worker lock in the disposable DB."""
    with connect() as c:
        schemas = c.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname ~ '^qot_[a-f0-9]{16}$' AND nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)"
        ).fetchall()
        c.execute("SET statement_timeout='15s'")
        for (name,) in schemas:
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def seed(conn, schema, size=120000, seed=17, edge=False):
    if not schema.startswith("qot_"):
        raise ValueError("Disposable schema prefix required")
    conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    conn.execute(
        sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(schema))
    )
    conn.execute(
        "CREATE TABLE customers (id integer PRIMARY KEY, name text NOT NULL, city text)"
    )
    conn.execute(
        "CREATE TABLE orders (id integer PRIMARY KEY, customer_id integer REFERENCES customers(id), status text, total numeric(12,2), created_at timestamp NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE items (id integer PRIMARY KEY, order_id integer REFERENCES orders(id), quantity integer, product text)"
    )
    n = 0 if size == 0 else max(10, min(10000, size // 10))
    conn.execute(
        "INSERT INTO customers SELECT g, 'Customer ' || g, CASE WHEN g %% 10 = 0 THEN NULL WHEN g %% 23 = 0 THEN 'Paris' ELSE 'Lyon' END FROM generate_series(1,%s) g",
        (n,),
    )
    if size:
        conn.execute(
            """INSERT INTO orders SELECT g,
        CASE WHEN g %% 71=0 THEN NULL WHEN g %% 7=0 THEN 42 %% %s + 1 ELSE (g * %s %% %s)+1 END,
        CASE WHEN g %% 97=0 THEN 'refunded' WHEN g %% 11=0 THEN NULL ELSE 'completed' END,
        CASE WHEN g %% 29=0 THEN NULL ELSE ((g * 17) %% 5000)::numeric / 10 END,
        timestamp '2024-01-01' + ((g * %s) %% 70000) * interval '1 minute'
        FROM generate_series(1,%s) g""",
            (n, seed, n, seed, size),
        )
        conn.execute(
            "INSERT INTO items SELECT g, (g %% %s)+1, (g %% 4)+1, 'Synthetic product' FROM generate_series(1,%s) g",
            (size, size * 2),
        )
    if edge and size:
        conn.execute("INSERT INTO customers VALUES (100000,'Orphan customer','Paris')")
        conn.execute(
            "INSERT INTO orders VALUES (-1,NULL,NULL,NULL,timestamp '1900-01-01'),(-2,1,'completed',0,timestamp '2100-01-01'),(-3,1,'completed',0,timestamp '2100-01-01')"
        )
    conn.execute("ANALYZE customers")
    conn.execute("ANALYZE orders")
    conn.execute("ANALYZE items")
    # Execution uses a dedicated role with SELECT grants, even inside the disposable DB.
    conn.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='qot_reader') THEN CREATE ROLE qot_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE; END IF; END $$"
    )
    conn.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO qot_reader").format(sql.Identifier(schema))
    )
    conn.execute(
        sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO qot_reader").format(
            sql.Identifier(schema)
        )
    )


@contextmanager
def sandbox(size=120000, seed_value=17, edge=False):
    schema = "qot_" + uuid.uuid4().hex[:16]
    with connect() as conn:
        try:
            seed(conn, schema, size, seed_value, edge)
            conn.execute("SET statement_timeout = '3s'")
            conn.execute("SET lock_timeout = '500ms'")
            conn.execute("SET max_parallel_workers_per_gather = 0")
            yield conn, schema
        finally:
            conn.execute("SET statement_timeout=0")
            conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )


@monitoring.instrument('execution')
def explain(conn, query, analyze=False):
    prefix = (
        "EXPLAIN (FORMAT JSON, COSTS TRUE"
        + (", ANALYZE TRUE, BUFFERS TRUE, TIMING TRUE" if analyze else "")
        + ") "
    )
    outer = conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
    with conn.transaction():
        if outer:
            conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL ROLE qot_reader")
        try:
            return conn.execute(prefix + query).fetchone()[0][0]
        finally:
            conn.execute("SET LOCAL ROLE NONE")


def result(conn, query, cap=20000):
    outer = conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
    with conn.transaction():
        if outer:
            conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL ROLE qot_reader")
        with conn.cursor(name="qot_compare_" + uuid.uuid4().hex[:8]) as cur:
            cur.execute(query)
            types = [d.type_code for d in cur.description]
            rows = cur.fetchmany(cap + 1)
            if len(rows) > cap:
                raise ValueError("Result exceeds comparison budget (20,000 rows).")
            if sum(len(str(r)) for r in rows) > 4_000_000:
                raise ValueError("Result exceeds 4 MB comparison budget.")
            # Type OIDs and Python types prevent string/number and NULL conflation.
            encoded = [
                json.dumps(
                    [(type(v).__name__, str(v) if v is not None else None) for v in r],
                    separators=(",", ":"),
                )
                for r in rows
            ]
            conn.execute("SET LOCAL ROLE NONE")
            return types, encoded


def compact(plan):
    out = []

    def walk(node, depth=0):
        out.append(
            {
                k: node[k]
                for k in (
                    "Node Type",
                    "Relation Name",
                    "Index Name",
                    "Plan Rows",
                    "Actual Rows",
                    "Actual Total Time",
                    "Total Cost",
                    "Rows Removed by Filter",
                    "Shared Hit Blocks",
                    "Shared Read Blocks",
                    "Sort Method",
                )
                if k in node
            }
            | {"depth": depth}
        )
        for child in node.get("Plans", []):
            walk(child, depth + 1)

    walk(plan["Plan"])
    return out[:30]


@monitoring.instrument("discovery")
def metadata(conn):
    tables = conn.execute(
        "SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema=current_schema() ORDER BY table_name,ordinal_position LIMIT 101"
    ).fetchall()
    indexes = conn.execute(
        "SELECT tablename,indexdef FROM pg_indexes WHERE schemaname=current_schema() LIMIT 101"
    ).fetchall()
    constraints = conn.execute(
        "SELECT conrelid::regclass::text, pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace=current_schema()::regnamespace LIMIT 101"
    ).fetchall()
    stats = conn.execute(
        "SELECT tablename,attname,null_frac,n_distinct,correlation FROM pg_stats WHERE schemaname=current_schema() LIMIT 101"
    ).fetchall()
    return {
        "columns": tables,
        "indexes": indexes,
        "constraints": constraints,
        "statistics": stats,
        "version": conn.execute("SHOW server_version").fetchone()[0],
    }
