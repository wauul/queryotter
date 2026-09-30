"""Idempotently copy the local job store to Neon without disclosing its contents."""

import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
from dotenv import dotenv_values
from cryptography.fernet import Fernet
from psycopg import sql


def main():
    settings = dotenv_values(".data/cloud.env")
    assert urlparse(settings["JOB_DATABASE_URL"]).hostname.endswith(".neon.tech")
    source = Path(".data/jobs.sqlite3")
    assert source.is_file()
    os.environ.update(settings)
    from backend import store

    store.init()
    with sqlite3.connect(source) as local:
        local.row_factory = sqlite3.Row
        assert (
            local.execute(
                "SELECT count(*) FROM jobs WHERE state IN ('queued','running')"
            ).fetchone()[0]
            == 0
        ), "Wait for local jobs before migration"
        counts = {}
        with store.connect() as destination:
            for table in ["jobs", "events", "connections", "limits"]:
                rows = local.execute("SELECT * FROM " + table).fetchall()
                for row in rows:
                    record = dict(row)
                    if table == "connections":
                        f = Fernet(settings["ENCRYPTION_KEY"].encode())
                        u = urlparse(f.decrypt(record["secret"].encode()).decode())
                        if (
                            record["label"] == "Verified read-only fixture"
                            and u.hostname in {"127.0.0.1", "localhost"}
                            and u.path == "/qot_live_fixture"
                        ):
                            record["secret"] = f.encrypt(
                                settings["LIVE_DEMO_DATABASE_URL"].encode()
                            ).decode()
                            record["label"] = "Neon read-only demo"
                    keys = list(record)
                    statement = sql.SQL(
                        "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING"
                    ).format(
                        sql.Identifier(table),
                        sql.SQL(",").join(map(sql.Identifier, keys)),
                        sql.SQL(",").join(sql.Placeholder() for _ in keys),
                    )
                    destination.raw.execute(statement, list(record.values()))
                counts[table] = len(rows)
            destination.raw.execute(
                "SELECT setval(pg_get_serial_sequence('qot_app.events','id'), COALESCE((SELECT max(id) FROM events),1), EXISTS(SELECT 1 FROM events))"
            )
    print("Migrated row counts:", counts)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Migration failed ({type(error).__name__}); record contents suppressed.")
        raise SystemExit(1)
