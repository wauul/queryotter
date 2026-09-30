"""Create a tiny disposable read-only fixture and verify authenticated hosted plan-only work."""

import os, secrets, time, json, sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse, quote
import httpx, psycopg
from psycopg import sql
from dotenv import load_dotenv

load_dotenv()
BASE = sys.argv[1] if len(sys.argv) > 1 else "https://queryotter.vercel.app"


def main():
    parsed = urlparse(os.environ["EXPERIMENT_DATABASE_URL"])
    assert parsed.hostname in {"127.0.0.1", "localhost"}, (
        "Only local disposable test clusters are supported."
    )
    password = secrets.token_hex(24)
    db = "qot_live_fixture"
    role = "qot_live_verifier"
    with psycopg.connect(
        os.environ["EXPERIMENT_DATABASE_URL"], autocommit=True
    ) as admin:
        if not admin.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (db,)
        ).fetchone():
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
        if not admin.execute(
            "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
        ).fetchone():
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
        else:
            admin.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
    admin_url = urlunparse(parsed._replace(path="/" + db))
    with psycopg.connect(admin_url, autocommit=True) as c:
        c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        c.execute(
            "CREATE TABLE IF NOT EXISTS public.orders (id integer PRIMARY KEY, customer_id integer, total numeric)"
        )
        c.execute(
            "INSERT INTO orders SELECT g,g%100,g::numeric FROM generate_series(1,500) g ON CONFLICT DO NOTHING"
        )
        c.execute("ANALYZE orders")
        c.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(db), sql.Identifier(role)
            )
        )
        c.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
        )
        c.execute(sql.SQL("GRANT SELECT ON orders TO {}").format(sql.Identifier(role)))
    live_url = (
        f"postgresql://{role}:{password}@{parsed.hostname}:{parsed.port or 5432}/{db}"
    )
    with httpx.Client(
        base_url=BASE, timeout=20
    ) as client:
        assert client.get("/api/session").status_code == 200
        assert (
            client.post(
                "/api/login", json={"password": os.environ["ADMIN_PASSWORD"]}
            ).status_code
            == 200
        )
        conn = client.post(
            "/api/connections",
            json={"label": "Verified read-only fixture", "url": live_url},
        )
        assert conn.status_code == 200, conn.text
        query = "SELECT id, total FROM orders WHERE customer_id=42 ORDER BY id LIMIT 50"
        created = client.post(
            "/api/jobs",
            json={
                "query": query,
                "connection_id": conn.json()["id"],
                "request_key": secrets.token_hex(16),
            },
        )
        assert created.status_code == 202, created.text
        id = created.json()["id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            j = client.get("/api/jobs/" + id).json()
            if j["state"] not in {"queued", "running"}:
                break
            time.sleep(1)
        assert j["state"] == "completed", j.get("error")
        r = j["report"]
        assert r["conditions"]["mode"] == "live plan-only"
        assert r["original"] is None and r["best"] is None
        assert all(c["status"] == "unverified" for c in r["candidates"])
        # No execution times or records in the non-executing plan.
        assert all("Actual Total Time" not in node for node in r["plan_before"])
        evidence = {
            "url": BASE,
            "mode": "authenticated live plan-only",
            "job_id": id,
            "checks": [
                "Least-privilege read-only fixture accepted",
                "Connection stored encrypted server-side",
                "Real Groq proposals from bounded schema and non-executing JSON EXPLAIN",
                "No records, execution times, indexes or verified claims",
            ],
            "report": r,
        }
        Path("docs/live-verification.json").write_text(
            json.dumps(evidence, indent=2, default=str), encoding="utf8"
        )
        print(
            json.dumps(
                {
                    "checks": evidence["checks"],
                    "job_id": id,
                    "model_calls": r["usage"]["calls"],
                }
            )
        )


if __name__ == "__main__":
    main()
