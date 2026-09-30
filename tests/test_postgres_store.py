import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg
from psycopg import sql
from dotenv import dotenv_values
from backend import store


@pytest.fixture
def pg_store(monkeypatch):
    url = os.environ.get("STORE_TEST_DATABASE_URL") or dotenv_values(".env").get(
        "EXPERIMENT_DATABASE_URL"
    )
    if not url:
        pytest.skip("No disposable PostgreSQL test database")
    name = "qot_store_test_" + uuid.uuid4().hex[:12]
    monkeypatch.setenv("JOB_DATABASE_URL", url)
    monkeypatch.setenv("JOB_DATABASE_SCHEMA", name)
    store.init()
    yield
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def test_atomic_limits_under_concurrency(pg_store):
    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = list(pool.map(lambda _: store.limit("shared", 5, 300), range(20)))
    assert sum(allowed) == 5
    assert not store.limit("shared", 5, 300)


def test_claim_idempotency_isolation_and_restart(pg_store):
    first = store.create("owner", "key-one", "already-fast", "SELECT id FROM orders")
    assert (
        store.create("owner", "key-one", "already-fast", "SELECT id FROM orders")["id"]
        == first["id"]
    )
    with pytest.raises(store.ActiveJob):
        store.create("owner", "key-two", "already-fast", "SELECT id FROM orders")
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(8)))
    claimed = [j for j in claims if j]
    assert len(claimed) == 1 and claimed[0]["id"] == first["id"]
    assert store.get(first["id"], "another") is None
    store.recover()
    assert store.claim()["id"] == first["id"]
    store.recover()
    assert store.get(first["id"], "owner")["state"] == "failed"
    store.finish(first["id"], "completed", {"verified": True})
    store.event(first["id"], "done", "Test completed")
    store.init()
    assert store.get(first["id"], "owner")["report"] == {"verified": True}
    assert len(store.get(first["id"], "owner")["events"]) == 1


def test_worker_lock_and_wake_after_commit(pg_store):
    with store.worker_lock():
        with pytest.raises(BlockingIOError):
            with store.worker_lock():
                pass
    with store.worker_lock():
        pass
    seen = []
    store.set_waker(lambda: seen.append(store.claim()))
    try:
        j = store.create("owner", "wake-key", None, "SELECT id FROM orders")
        assert seen[0]["id"] == j["id"]
    finally:
        store.set_waker(None)
