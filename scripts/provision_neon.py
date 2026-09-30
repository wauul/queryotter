"""Provision only QueryOtter's dedicated Neon project. Never print credentials."""

import os
import secrets
from pathlib import Path
from urllib.parse import urlparse, urlunparse, quote, urlencode
import psycopg
from psycopg import sql
from dotenv import dotenv_values
from backend.connections import tls_options


def main():
    initial = Path(".data/neon-bootstrap-url").read_text().strip()
    parsed = urlparse(initial)
    assert (
        parsed.hostname == "ep-gentle-glitter-b117jrlg.c-5.eu-central-1.aws.neon.tech"
    )
    query = urlencode(
        {
            "sslmode": "verify-full",
            "sslrootcert": "system",
            "channel_binding": "require",
        }
    )
    initial = urlunparse(parsed._replace(query=query))
    local = dotenv_values(".env")
    saved = dotenv_values(".data/cloud.env")
    roles = {
        "JOB_DATABASE_URL": ("qot_app_runtime", "queryotter_app"),
        "EXPERIMENT_DATABASE_URL": ("qot_experiment_runtime", "queryotter_experiments"),
        "LIVE_DEMO_DATABASE_URL": ("qot_live_reader", "queryotter_experiments"),
    }
    settings = {
        key: local[key]
        for key in [
            "SERVICE_TOKEN",
            "SESSION_SECRET",
            "ENCRYPTION_KEY",
            "ADMIN_PASSWORD",
            "MODEL_API_KEY",
            "MODEL_BASE_URL",
            "MODEL_NAME",
        ]
    }
    settings.update(
        {
            "MODEL_PROVIDER": "openai-compatible",
            "DEMO_DAILY_LIMIT": "6",
            "JOB_SECONDS": "180",
        }
    )
    for key, (role, db) in roles.items():
        password = (
            urlparse(saved[key]).password
            if saved.get(key)
            else secrets.token_urlsafe(32)
        )
        settings[key] = urlunparse(
            parsed._replace(
                netloc=f"{role}:{quote(password, safe='')}@{parsed.hostname}",
                path="/" + db,
                query=query,
            )
        )
    Path(".data/cloud.env").write_text(
        "".join(f"{key}={value}\n" for key, value in settings.items()), encoding="utf8"
    )
    with psycopg.connect(
        initial, autocommit=True, connect_timeout=15, **tls_options(initial)
    ) as c:
        for key, (role, _) in roles.items():
            if not c.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
            ).fetchone():
                password = urlparse(settings[key]).password
                c.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Identifier(role), sql.Literal(password))
                )
        if not c.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='qot_reader'"
        ).fetchone():
            c.execute(
                "CREATE ROLE qot_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            )
        c.execute(
            "GRANT qot_reader TO qot_experiment_runtime WITH INHERIT FALSE, SET TRUE"
        )
        for key in ["JOB_DATABASE_URL", "EXPERIMENT_DATABASE_URL"]:
            role, db = roles[key]
            c.execute(
                sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                    sql.Identifier(role), sql.Identifier(parsed.username)
                )
            )
            if not c.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (db,)
            ).fetchone():
                c.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(db), sql.Identifier(role)
                    )
                )
            c.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(db)
                )
            )
            c.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(db), sql.Identifier(role)
                )
            )
        c.execute("GRANT CONNECT ON DATABASE queryotter_experiments TO qot_live_reader")
    with psycopg.connect(
        settings["EXPERIMENT_DATABASE_URL"],
        autocommit=True,
        connect_timeout=15,
        **tls_options(settings["EXPERIMENT_DATABASE_URL"]),
    ) as c:
        c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        c.execute(
            "CREATE TABLE IF NOT EXISTS public.orders (id integer PRIMARY KEY, customer_id integer, total numeric)"
        )
        c.execute(
            "INSERT INTO orders SELECT g,g%100,g::numeric FROM generate_series(1,500) g ON CONFLICT DO NOTHING"
        )
        c.execute("ANALYZE orders")
        c.execute("GRANT USAGE ON SCHEMA public TO qot_live_reader")
        c.execute("GRANT SELECT ON orders TO qot_live_reader")
    os.environ.update(settings)
    from backend import store

    store.init()
    print(
        "Neon ready: isolated app and experiment databases, restricted SQL execution role, read-only live fixture, verified TLS."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Provisioning failed ({type(error).__name__}); credentials suppressed.")
        raise SystemExit(1)
