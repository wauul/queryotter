import os, json, time
import psycopg
from cryptography.fernet import Fernet
from backend import store, monitoring
from backend.db import metadata, compact
from backend.model import propose
from backend.safety import validate_query
from backend.connections import tls_options


@monitoring.instrument("discovery")
def inspect_connection(url):
    conn = psycopg.connect(url, connect_timeout=10, autocommit=True, **tls_options(url))
    try:
        role = conn.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        if any(role):
            raise ValueError("Privileged roles are forbidden")
        if conn.execute(
            "SELECT has_schema_privilege(current_user,'public','CREATE')"
        ).fetchone()[0]:
            raise ValueError("Schema creation permission forbidden")
        conn.execute("SET statement_timeout='1500ms'")
        conn.execute("SET lock_timeout='200ms'")
        if conn.execute(
            "SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p','v','m','f') AND (has_table_privilege(current_user,oid,'INSERT') OR has_table_privilege(current_user,oid,'UPDATE') OR has_table_privilege(current_user,oid,'DELETE') OR has_table_privilege(current_user,oid,'TRUNCATE'))"
        ).fetchone()[0]:
            raise ValueError("Effective write grants forbidden")
        if conn.execute(
            "SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND (relkind IN ('v','m','f') OR relrowsecurity)"
        ).fetchone()[0]:
            raise ValueError("Views, foreign tables and row-level policies unsupported")
        conn.execute("SET default_transaction_read_only=on")
        conn.execute("SET search_path=pg_catalog,public")
        return conn
    except Exception:
        conn.close()
        raise


def investigate_live(job, event, check):
    data = json.loads(job["query"])
    with store.connect() as s:
        row = s.execute(
            "SELECT secret FROM connections WHERE id=? AND owner=?",
            (data["live"], job["owner"]),
        ).fetchone()
    if not row:
        raise ValueError("Connection not found")
    url = (
        Fernet(os.environ["ENCRYPTION_KEY"].encode())
        .decrypt(row["secret"].encode())
        .decode()
    )
    start = time.monotonic()
    check()
    event(
        "inspect",
        "Live mode: metadata and non-executing EXPLAIN only. No records or indexes accessed.",
    )
    with inspect_connection(url) as conn:
        conn.execute("SET search_path=public,pg_catalog")
        info = metadata(conn)
        conn.execute("SET search_path=pg_catalog,public")
        if len(info["columns"]) > 100:
            raise ValueError(
                "Schema exceeds live metadata budget; use a dedicated sanitized schema."
            )
        standard = {
            "integer",
            "bigint",
            "smallint",
            "text",
            "character varying",
            "numeric",
            "timestamp without time zone",
            "timestamp with time zone",
            "boolean",
            "date",
            "double precision",
            "real",
        }
        if any(c[2] not in standard for c in info["columns"]):
            raise ValueError("Custom types and domains are unsupported in live mode.")
        tables = {c[0] for c in info["columns"]}
        query = validate_query(data["sql"], tables)
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            plan = compact(
                conn.execute("EXPLAIN (FORMAT JSON) " + query).fetchone()[0][0]
            )
        event("explain", "Planner estimates collected without executing the SELECT.")
        check()
        p, usage = propose(query, info, plan)
        check()
        event(
            "recommend",
            "Unverified recommendations only. Export to a sanitized disposable database to measure.",
        )
        return {
            "query": query,
            "diagnosis": p.diagnosis,
            "candidates": [
                {
                    **c.model_dump(),
                    "status": "unverified",
                    "correctness": {"passed": False, "datasets": []},
                }
                for c in p.candidates
            ],
            "best": None,
            "original": None,
            "plan_before": plan,
            "schema": info,
            "conditions": {
                "mode": "live plan-only",
                "equivalence": "Not tested. Query was not executed.",
                "cache": "Not measured",
            },
            "usage": usage
            | {
                "tool_calls": 3,
                "runtime_seconds": round(time.monotonic() - start, 2),
                "database_seconds": None,
            },
            "migration": [],
            "limitations": [
                "Live mode only reads bounded metadata and non-executing EXPLAIN.",
                "No semantic or performance verification; no indexes applied.",
            ],
        }
