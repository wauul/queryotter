"""Only disposable loopback services; no hosted credentials or production mutation."""

import json
import time
from datetime import datetime, timezone
import httpx
from backend.demo import fixtures, sqlite_demo

PASSWORD = "Qot_TestOnly_48219"
AS_OF = datetime(2026, 9, 30, tzinfo=timezone.utc)
DATA = fixtures(AS_OF)


def wait(operation):
    start = time.monotonic()
    while True:
        try:
            return operation()
        except Exception:
            if time.monotonic() - start > 90:
                raise
            time.sleep(2)


def seed(engine):
    if engine == "sqlite":
        return sqlite_demo(AS_OF)
    if engine in {"postgresql", "cockroachdb"}:
        import psycopg

        port = 55433 if engine == "postgresql" else 26258
        conn = wait(
            lambda: psycopg.connect(
                host="127.0.0.1",
                port=port,
                user="postgres" if engine == "postgresql" else "root",
                password=PASSWORD if engine == "postgresql" else None,
                dbname="shop" if engine == "postgresql" else "defaultdb",
                autocommit=True,
                connect_timeout=3,
            )
        )
        if engine == "cockroachdb":
            conn.execute("CREATE DATABASE IF NOT EXISTS shop")
            conn.close()
            conn = psycopg.connect(
                host="127.0.0.1", port=port, user="root", dbname="shop", autocommit=True
            )
        with conn:
            conn.execute("DROP TABLE IF EXISTS orders")
            conn.execute("DROP TABLE IF EXISTS customers")
            conn.execute(
                "CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,country TEXT)"
            )
            conn.execute(
                "CREATE TABLE orders(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),total NUMERIC,status TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL)"
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO customers VALUES(%s,%s,%s)", DATA["customers"]
                )
                cur.executemany(
                    "INSERT INTO orders VALUES(%s,%s,%s,%s,%s)", DATA["orders"]
                )
            if engine == "postgresql":
                conn.execute(
                    "DO $$ BEGIN CREATE ROLE qot_reader LOGIN PASSWORD 'Qot_TestOnly_48219'; EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                )
                conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            else:
                conn.execute("CREATE USER IF NOT EXISTS qot_reader")
                conn.execute("REVOKE CREATE ON SCHEMA public FROM public")
            conn.execute("GRANT CONNECT ON DATABASE shop TO qot_reader")
            conn.execute("GRANT USAGE ON SCHEMA public TO qot_reader")
            conn.execute("GRANT SELECT ON customers,orders TO qot_reader")
        return {
            "url": f"postgresql://qot_reader:{PASSWORD if engine == 'postgresql' else ''}@127.0.0.1:{port}/shop",
            "schema": "public",
        }
    if engine in {"mysql", "mariadb"}:
        import pymysql

        port = 3307 if engine == "mysql" else 3308
        conn = wait(
            lambda: pymysql.connect(
                host="127.0.0.1",
                port=port,
                user="root",
                password=PASSWORD,
                database="shop",
                autocommit=True,
                connect_timeout=3,
            )
        )
        try:
            with conn.cursor() as cur:
                for statement in [
                    "DROP TABLE IF EXISTS orders",
                    "DROP TABLE IF EXISTS customers",
                    "CREATE TABLE customers(id INTEGER PRIMARY KEY,name VARCHAR(100) NOT NULL,country VARCHAR(10))",
                    "CREATE TABLE orders(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),total DECIMAL(12,2),status VARCHAR(20) NOT NULL,created_at DATETIME NOT NULL,FOREIGN KEY(customer_id) REFERENCES customers(id))",
                ]:
                    cur.execute(statement)
                cur.executemany(
                    "INSERT INTO customers VALUES(%s,%s,%s)", DATA["customers"]
                )
                cur.executemany(
                    "INSERT INTO orders VALUES(%s,%s,%s,%s,%s)",
                    [
                        (
                            id,
                            cid,
                            total,
                            status,
                            datetime.fromisoformat(dt).replace(tzinfo=None),
                        )
                        for id, cid, total, status, dt in DATA["orders"]
                    ],
                )
                cur.execute(
                    "CREATE USER IF NOT EXISTS 'qot_reader'@'%' IDENTIFIED BY 'Qot_TestOnly_48219'"
                )
                cur.execute("GRANT SELECT ON shop.* TO 'qot_reader'@'%'")
        finally:
            conn.close()
        return {
            "url": f"{engine}://qot_reader:{PASSWORD}@127.0.0.1:{port}/shop",
            "schema": "shop",
        }
    if engine == "sqlserver":
        import pytds

        conn = wait(
            lambda: pytds.connect(
                server="127.0.0.1",
                port=1434,
                user="sa",
                password=PASSWORD + "!",
                database="master",
                login_timeout=3,
                autocommit=True,
                disable_connect_retry=True,
            )
        )
        with conn.cursor() as cur:
            cur.execute("IF DB_ID('shop') IS NULL CREATE DATABASE shop")
        conn.close()
        with pytds.connect(
            server="127.0.0.1",
            port=1434,
            user="sa",
            password=PASSWORD + "!",
            database="shop",
            autocommit=True,
        ) as conn:
            with conn.cursor() as cur:
                for statement in [
                    "DROP TABLE IF EXISTS orders",
                    "DROP TABLE IF EXISTS customers",
                    "CREATE TABLE customers(id INTEGER PRIMARY KEY,name VARCHAR(100) NOT NULL,country VARCHAR(10))",
                    "CREATE TABLE orders(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),total DECIMAL(12,2),status VARCHAR(20) NOT NULL,created_at DATETIMEOFFSET NOT NULL)",
                ]:
                    cur.execute(statement)
                cur.executemany(
                    "INSERT INTO customers VALUES(%s,%s,%s)", DATA["customers"]
                )
                cur.executemany(
                    "INSERT INTO orders VALUES(%s,%s,%s,%s,%s)", DATA["orders"]
                )
                cur.execute(
                    "IF NOT EXISTS(SELECT 1 FROM sys.server_principals WHERE name='qot_reader') CREATE LOGIN qot_reader WITH PASSWORD='Qot_TestOnly_48219!', CHECK_POLICY=OFF"
                )
                cur.execute(
                    "IF NOT EXISTS(SELECT 1 FROM sys.database_principals WHERE name='qot_reader') CREATE USER qot_reader FOR LOGIN qot_reader"
                )
                cur.execute("GRANT SELECT,VIEW DEFINITION,SHOWPLAN TO qot_reader")
        return {
            "url": f"mssql://qot_reader:{PASSWORD}!@127.0.0.1:1434/shop",
            "schema": "dbo",
        }
    customers = [
        {"id": id, "name": name, "country": country}
        for id, name, country in DATA["customers"]
    ]
    orders = [
        {
            "id": id,
            "customer_id": cid,
            "total": total,
            "status": status,
            "created_at": datetime.fromisoformat(dt),
        }
        for id, cid, total, status, dt in DATA["orders"]
    ]
    orders += [
        {"id": 45, "status": "pending", "tags": ["new", "priority"]},
        {"id": 46, "status": "pending", "total": "unknown"},
    ]
    if engine == "mongodb":
        from pymongo import MongoClient

        client = MongoClient(
            f"mongodb://root:{PASSWORD}@127.0.0.1:27018/admin",
            serverSelectionTimeoutMS=3000,
        )
        wait(lambda: client.admin.command("ping"))
        db = client.shop
        for name, docs in [("customers", customers), ("orders", orders)]:
            db[name].drop()
            db[name].insert_many(docs)
        try:
            db.command(
                "createUser",
                "qot_reader",
                pwd=PASSWORD,
                roles=[{"role": "read", "db": "shop"}],
            )
        except Exception as error:
            if getattr(error, "code", None) != 51003:
                raise
        client.close()
        return {
            "url": f"mongodb://qot_reader:{PASSWORD}@127.0.0.1:27018/shop?authSource=shop",
            "infer_document_schema": True,
        }
    if engine == "firestore":
        from backend.adapters.documents import firestore_literal

        base = "http://127.0.0.1:8089/v1/projects/demo-queryotter/databases/(default)/documents"
        wait(
            lambda: httpx.post(
                base + ":listCollectionIds",
                json={"pageSize": 1},
                headers={"Authorization": "Bearer owner"},
                timeout=3,
            ).raise_for_status()
        )
        for name, docs in [("customers", customers), ("orders", orders)]:
            for doc in docs:
                fields = {
                    k: firestore_literal(
                        {"timestamp": v.isoformat()} if isinstance(v, datetime) else v
                    )
                    for k, v in doc.items()
                }
                r = httpx.patch(
                    base + "/" + name + "/" + str(doc["id"]),
                    json={"fields": fields},
                    headers={"Authorization": "Bearer owner"},
                    timeout=3,
                )
                r.raise_for_status()
        return {
            "project_id": "demo-queryotter",
            "emulator": True,
            "port": 8089,
            "infer_document_schema": True,
        }
    if engine == "firebase_realtime":
        base = "http://127.0.0.1:9009"
        wait(
            lambda: httpx.get(
                base + "/.json?ns=demo-queryotter",
                headers={"Authorization": "Bearer owner"},
                timeout=3,
            ).raise_for_status()
        )
        payload = {
            name: {
                str(d["id"]): {
                    k: v.isoformat() if isinstance(v, datetime) else v
                    for k, v in d.items()
                }
                for d in docs
            }
            for name, docs in [("customers", customers), ("orders", orders)]
        }
        r = httpx.put(
            base + "/.json?ns=demo-queryotter",
            json=payload,
            headers={"Authorization": "Bearer owner"},
            timeout=3,
        )
        r.raise_for_status()
        from pathlib import Path

        rules = json.loads((Path(__file__).parent / "database.rules.json").read_text())
        r = httpx.put(
            base + "/.settings/rules.json?ns=demo-queryotter",
            json=rules,
            headers={"Authorization": "Bearer owner"},
            timeout=3,
        )
        r.raise_for_status()
        return {
            "url": base,
            "namespace": "demo-queryotter",
            "emulator": True,
            "infer_document_schema": True,
        }
    raise ValueError("unknown fixture")
