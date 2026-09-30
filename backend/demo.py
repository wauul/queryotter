"""Synthetic UTC data; no real customer records. Reproducible for an as-of date."""

import base64
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path


def fixtures(as_of=None):
    as_of = as_of or datetime.now(timezone.utc)
    month = as_of.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous = (month - timedelta(days=1)).replace(day=1)
    customers = [(i, f"Customer {i}", "FR" if i % 2 else "US") for i in range(1, 9)]
    orders = []
    for i in range(1, 41):
        dt = previous + timedelta(days=i % 20, hours=i % 24)
        orders.append(
            (i, 1 + i % 8, float(i * 7), "paid" if i % 5 else "pending", dt.isoformat())
        )
    orders += [
        (41, 1, None, "paid", previous.isoformat()),
        (42, 1, 9999.0, "paid", month.isoformat()),
        (43, None, 12.0, "paid", previous.isoformat()),
        (44, 2, 50.0, "paid", (previous - timedelta(seconds=1)).isoformat()),
    ]
    return {
        "customers": customers,
        "orders": orders,
        "as_of": as_of.isoformat(),
        "previous_month_start": previous.isoformat(),
        "month_start": month.isoformat(),
    }


def sqlite_demo(as_of=None):
    data = fixtures(as_of)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "demo.db"
        with sqlite3.connect(path) as c:
            c.executescript(
                "CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,country TEXT); CREATE TABLE orders(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),total NUMERIC,status TEXT NOT NULL,created_at TEXT NOT NULL);"
            )
            c.executemany("INSERT INTO customers VALUES(?,?,?)", data["customers"])
            c.executemany("INSERT INTO orders VALUES(?,?,?,?,?)", data["orders"])
        c.close()
        return {
            "engine": "sqlite",
            "data": base64.b64encode(path.read_bytes()).decode(),
            "demo": True,
            "as_of": data["as_of"],
            "timezone": "UTC",
        }
