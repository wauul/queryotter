from backend.db import sandbox, explain, result
from backend.investigate import run, Cancelled
from backend.cases import CASES
from backend import store
from backend.worker import execute
from psycopg import sql
import pytest, time


def test_execution_role_restored_inside_index_transaction():
    with sandbox(300) as (c, _):
        with c.transaction(force_rollback=True):
            explain(c, "SELECT id FROM orders WHERE id=1", True)
            c.execute("CREATE INDEX ON orders(customer_id)")
            result(c, "SELECT id FROM orders WHERE id=1")
            assert c.execute("SELECT current_user").fetchone()[0] != "qot_reader"


def test_statement_timeout_and_cleanup():
    with sandbox(100) as (c, schema):
        c.execute("SET statement_timeout='20ms'")
        with pytest.raises(Exception):
            c.execute("SELECT pg_sleep(1)")
        c.execute("SET statement_timeout='3s'")
        assert c.execute("SELECT 1").fetchone()[0] == 1


def test_cancellation_rolls_back_schema():
    def cancel():
        raise Cancelled()

    with pytest.raises(Cancelled):
        run(CASES[0]["sql"], check=cancel, baseline=[])


def test_worker_cancel_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "jobs.sqlite3")
    store.init()
    j = store.create("owner", "persist-key", "already-fast", CASES[9]["sql"])
    claimed = store.claim()
    assert claimed["id"] == j["id"]
    with store.connect() as c:
        c.execute("UPDATE jobs SET cancel=1 WHERE id=?", (j["id"],))
    execute(claimed)
    store.init()
    assert store.get(j["id"], "owner")["state"] == "cancelled"
    assert store.get(j["id"], "other") is None
