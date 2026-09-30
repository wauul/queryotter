import json
import os
import secrets
import time
import pytest
from fastapi.testclient import TestClient
from backend.api import app
from backend import accounts, store, workspaces, generation, usage
from backend.worker import execute
from backend.adapters.relational import SQLite
from backend.adapters.base import AdapterError
from backend.copy_benchmark import measure
from backend.demo import sqlite_demo


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.delenv("JOB_DATABASE_URL", raising=False)
    monkeypatch.setattr(store, "DB", tmp_path / "workspace.db")
    store.init()
    workspaces.init()


def client(subject):
    c = TestClient(app, base_url="http://localhost")
    c.headers.update(
        {
            "x-service-token": os.environ["SERVICE_TOKEN"],
            "x-app-origin": "http://localhost",
        }
    )
    user = workspaces.user_for_identity("test", subject, subject)
    token = secrets.token_urlsafe(32)
    with store.connect() as db:
        db.execute(
            "INSERT INTO q_sessions VALUES(?,?,?,?,?)",
            (
                accounts.digest(token),
                user["id"],
                time.time(),
                time.time() + 10000,
                time.time(),
            ),
        )
    c.cookies.set("qot_auth", token)
    return c, user["id"]


def test_calendar_boundaries_preserve_dst_and_year_rollover():
    from datetime import datetime, timezone

    dates = generation.date_context("Europe/Paris", datetime(2026, 4, 15, tzinfo=timezone.utc))
    assert dates["last_month_start_utc"] == "2026-02-28T23:00:00+00:00"
    assert dates["last_month_end_exclusive_utc"] == "2026-03-31T22:00:00+00:00"
    elapsed = datetime.fromisoformat(dates["last_month_end_exclusive_utc"]) - datetime.fromisoformat(dates["last_month_start_utc"])
    assert elapsed.total_seconds() == 743 * 3600
    january = generation.date_context("UTC", datetime(2026, 1, 15, tzinfo=timezone.utc))
    assert january["last_month_start_utc"] == "2025-12-01T00:00:00+00:00"
    assert january["last_month_end_exclusive_utc"] == "2026-01-01T00:00:00+00:00"
    with pytest.raises(AdapterError, match="IANA"):
        generation.date_context("Not/AZone")


def test_postgres_portfolio_uses_revocable_workspace_identity():
    from backend.api import signed

    alice, uid = client("portfolio-alice")
    bob, _ = client("portfolio-bob")
    response = alice.post("/api/jobs", json={"case_id":"customer-orders","request_key":secrets.token_hex(12)})
    assert response.status_code == 202
    jid = response.json()["id"]
    assert alice.get("/api/jobs/"+jid).status_code == 200
    assert bob.get("/api/jobs/"+jid).status_code == 404
    assert alice.post("/api/jobs/"+jid+"/cancel").json()["state"] == "cancelled"
    exported = alice.get("/api/assistant/account/export").json()
    assert exported["postgresql_experiments"][0]["id"] == jid
    assert bob.get("/api/assistant/account/export").json()["postgresql_experiments"] == []
    assert alice.post("/api/jobs", json={"query":"SELECT id FROM orders","request_key":secrets.token_hex(12)}).status_code == 401
    alice.cookies.clear()
    alice.cookies.set("qot_session", signed(uid))
    assert alice.get("/api/jobs/"+jid).status_code == 401


def job(c, cid, action, **fields):
    response = c.post(
        "/api/assistant/jobs",
        json={
            "connection_id": cid,
            "action": action,
            "request_key": secrets.token_hex(12),
            **fields,
        },
    )
    assert response.status_code == 202, response.text
    execute(store.claim())
    return c.get("/api/assistant/jobs/" + response.json()["id"]).json()


def test_outbound_connector_real_copy_round_trip_and_revocation(monkeypatch):
    import importlib.util
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("qot_local_connector", Path("scripts/local-connector.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner, _ = client("connector-owner")
    stranger, _ = client("connector-stranger")
    enrolled = owner.post("/api/assistant/connectors", json={"label": "Fixture copy"}).json()
    base = "/api/assistant/connectors/" + enrolled["id"]
    headers = {"authorization": "Bearer " + enrolled["token"]}
    assert owner.post(base + "/poll", json={}).status_code == 401
    assert stranger.post(base + "/remove", json={}).status_code == 404
    assert owner.post(base + "/poll", json={}, headers=headers).status_code == 200
    response = owner.post("/api/assistant/connections", json={"label": "Remote fixture copy", "engine": "sqlite", "provider": "generic", "config": {"connector_id": enrolled["id"], "profile": "copy"}})
    assert response.status_code == 200, response.text
    cid = response.json()["id"]
    profiles = {"copy": {"engine": "sqlite", "allowed_hosts": ["127.0.0.1"], "config": sqlite_demo()}}
    def round_trip(action, **fields):
        pending = owner.post("/api/assistant/jobs", json={"connection_id": cid, "action": action, "request_key": secrets.token_hex(12), **fields})
        assert pending.status_code == 202
        jid = pending.json()["id"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(execute, store.claim())
            until = time.monotonic() + 10
            while not future.done() and time.monotonic() < until:
                task = owner.post(base + "/poll", json={}, headers=headers).json().get("task")
                if task:
                    # Cloud task contains profile + query/engine only, never the upload/credential.
                    assert sqlite_demo()["data"] not in json.dumps(task)
                    done = owner.post(base + "/complete", headers=headers, json={"task_id": task["id"], "response": module.process_task(task, profiles)})
                    assert done.status_code == 200, done.text
                else:
                    time.sleep(.05)
            future.result(timeout=2)
        answer = owner.get("/api/assistant/jobs/" + jid).json()
        assert answer["state"] == "completed", answer
        return answer["report"]
    assert len(round_trip("test")["metadata"]["tables"]) == 2
    result = round_trip("run", query="SELECT id,name FROM customers ORDER BY id LIMIT 2")
    assert owner.get("/api/assistant/results/" + result["run_id"]).json()["rows"] == [[1,"Customer 1"],[2,"Customer 2"]]
    assert module.process_task({"profile":"missing","action":"discover","request":{"engine":"sqlite"}}, profiles)["code"] == "profile"
    assert owner.post(base + "/complete", headers=headers, json={"task_id":"expired","response":{"value":{}}}).status_code == 409
    assert owner.post(base + "/remove", json={}).status_code == 200
    assert owner.post(base + "/poll", json={}, headers=headers).status_code == 401
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM q_connector_tasks").fetchone()[0] == 0


def test_real_discovery_execution_pages_and_isolation():
    a, au = client("a")
    b, bu = client("b")
    cid = a.post("/api/assistant/connections/demo").json()["id"]
    tested = job(a, cid, "test")
    assert tested["state"] == "completed", tested
    assert len(tested["report"]["metadata"]["tables"]) == 2
    ran = job(a, cid, "run", query="SELECT id,name FROM customers ORDER BY id")
    assert ran["state"] == "completed", ran
    rid = ran["report"]["run_id"]
    path = "/api/assistant/results/" + rid
    assert a.get(path + "?page=2&page_size=3").json()["rows"][0] == [4, "Customer 4"]
    assert "rows" not in ran["report"]
    assert b.get(path).status_code == 404
    assert b.get("/api/assistant/jobs/" + ran["id"]).status_code == 404
    assert b.post("/api/assistant/jobs/" + ran["id"] + "/cancel").status_code == 404
    assert b.post("/api/assistant/connections/" + cid + "/remove").status_code == 404
    assert (
        b.post(
            "/api/assistant/jobs",
            json={
                "connection_id": cid,
                "action": "run",
                "query": "SELECT id FROM customers",
                "request_key": secrets.token_hex(12),
            },
        ).status_code
        == 404
    )
    assert a.get(path + "/export?format=csv").status_code == 200
    assert a.get("/api/assistant/account/export").json()["connections"][0]["id"] == cid
    assert "secret" not in a.get("/api/assistant/connections").text
    with store.connect() as db:
        db.execute("UPDATE q_runs SET result_expires=0 WHERE id=?", (rid,))
    assert a.get(path).status_code == 410


def test_generation_never_executes_and_refinement_stays_scoped(monkeypatch):
    c, uid = client("a")
    cid = c.post("/api/assistant/connections/demo").json()["id"]
    captured = []

    def call(user, system, data, check, **kwargs):
        captured.append(data)
        return {
            "query": "SELECT id,name FROM customers ORDER BY id LIMIT 5",
            "clarification": None,
            "explanation": "Five known customers.",
            "assumptions": [],
        }, {
            "model_calls": 1,
            "input_tokens": 10,
            "output_tokens": 20,
            "seconds": 0.1,
            "estimated_cost_usd": 0.00001,
        }

    monkeypatch.setattr(generation, "call", call)
    monkeypatch.setattr(
        SQLite, "execute", lambda *args: pytest.fail("Generation must never execute")
    )
    draft = job(c, cid, "generate", prompt="Show five customers")
    assert draft["state"] == "completed", draft
    assert draft["report"]["requires_run"]
    assert draft["report"]["validation"]["executable"] is None
    assert (
        c.get("/api/assistant/results/" + draft["report"]["run_id"]).status_code == 410
    )
    refined = job(
        c,
        cid,
        "generate",
        prompt="Now just three",
        previous_run=draft["report"]["run_id"],
    )
    assert captured[-1]["previous_query"] == draft["report"]["query"]
    assert all(
        sqlite_demo()["data"] not in json.dumps(d)
        and "service_account" not in json.dumps(d)
        for d in captured
    )
    second = c.post("/api/assistant/connections/demo").json()["id"]
    invalid = job(
        c, second, "generate", prompt="Refine", previous_run=draft["report"]["run_id"]
    )
    assert invalid["state"] == "rejected"


def test_clarification_and_bounded_repair(monkeypatch):
    config = sqlite_demo()
    calls = []

    def invalid(*args, **kwargs):
        calls.append(1)
        return {
            "query": "SELECT imaginary FROM missing",
            "explanation": "bad",
            "assumptions": [],
        }, {
            "model_calls": 1,
            "input_tokens": 10,
            "output_tokens": 10,
            "seconds": 0.1,
            "estimated_cost_usd": 0.001,
        }

    monkeypatch.setattr(generation, "call", invalid)
    with SQLite(config) as adapter:
        schema = adapter.discover()
        report = generation.generate("fake", adapter, schema, "five customers")
        assert (
            len(calls) == 2
            and report["repair_attempts"] == 1
            and report["query"] is None
        )
        monkeypatch.setattr(
            generation,
            "call",
            lambda *a, **kw: (
                {
                    "query": "SELECT id FROM customers",
                    "clarification": "Does best mean paid revenue or number of orders?",
                    "explanation": "Ambiguous.",
                    "assumptions": [],
                },
                {"model_calls": 1},
            ),
        )
        clarified = generation.generate("fake", adapter, schema, "best customers")
        assert clarified["query"] is None and clarified["clarification"]


def test_revocation_account_delete_and_active_job_cleanup():
    c, uid = client("a")
    cid = c.post("/api/assistant/connections/demo").json()["id"]
    assert (
        c.post(
            "/api/assistant/saved",
            json={
                "connection_id": cid,
                "name": "Customers",
                "query": "SELECT id FROM customers",
            },
        ).status_code
        == 200
    )
    data = c.post(
        "/api/assistant/jobs",
        json={
            "connection_id": cid,
            "action": "test",
            "request_key": secrets.token_hex(12),
        },
    ).json()
    claimed = store.claim()
    assert (
        c.post(
            "/api/assistant/account/delete", json={"confirmation": "wrong"}
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/assistant/account/delete", json={"confirmation": "DELETE"}
        ).status_code
        == 200
    )
    execute(claimed)  # Deletion must neither resurrect data nor crash the worker.
    assert c.get("/api/assistant/connections").status_code == 401
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM q_users").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM q_connections").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    c, uid = client("b")
    old_cookie = c.cookies.get("qot_auth")
    assert c.post("/api/assistant/logout").status_code == 200
    c.cookies.set("qot_auth", old_cookie)
    assert c.get("/api/assistant/connections").status_code == 401


def test_atomic_budgets_and_connection_rotation():
    c, uid = client("a")
    usage.reserve(uid, usage.maximum() - 20)
    with pytest.raises(AdapterError):
        usage.reserve(uid, 21)
    usage.reserve(uid, 20)
    assert usage.current(uid)["tokens_used_or_reserved"] == usage.maximum()
    cid = c.post("/api/assistant/connections/demo").json()["id"]
    job(c, cid, "test")
    response = c.post(
        "/api/assistant/connections/" + cid + "/rotate",
        json={
            "label": "Rotated copy",
            "engine": "sqlite",
            "provider": "generic",
            "config": {"data": sqlite_demo()["data"]},
        },
    )
    assert response.status_code == 200 and response.json()["status"] == "untested"
    assert workspaces.cached_schema(cid)[0] is None


def test_copy_benchmark_detects_null_duplicate_and_order_changes():
    config = sqlite_demo()
    with SQLite(config) as adapter:
        metadata = adapter.discover()
    same = measure(
        config,
        "SELECT customer_id FROM orders ORDER BY id",
        "SELECT customer_id FROM orders ORDER BY id",
        [],
        metadata,
    )
    assert same["correct"] and same["scope"]["comparison"] == "ordered typed rows"
    wrong = measure(
        config,
        "SELECT customer_id FROM orders",
        "SELECT DISTINCT customer_id FROM orders",
        [],
        metadata,
    )
    assert not wrong["correct"] and not wrong["improvement_observed"]
    indexed = measure(
        config,
        "SELECT id FROM orders WHERE status='paid'",
        "SELECT id FROM orders WHERE status='paid'",
        ["CREATE INDEX qot_paid ON orders(status)"],
        metadata,
    )
    assert indexed["correct"] and indexed["experimental_indexes"]
    with SQLite(config) as adapter:
        assert not any("qot_paid" in str(i) for i in adapter.discover()["indexes"])


def test_oauth_state_browser_binding_expiry_and_single_use():
    secret = workspaces.encrypt({"verifier": "private-verifier", "nonce": "nonce"})
    with store.connect() as db:
        db.execute(
            "INSERT INTO q_oauth VALUES(?,?,?,?,?)",
            ("state", "github", accounts.digest("browser"), secret, time.time() + 60),
        )
    with pytest.raises(Exception):
        accounts.consume_state("github", "state", "other-browser")
    assert accounts.consume_state("github", "state", "browser")["nonce"] == "nonce"
    with pytest.raises(Exception):
        accounts.consume_state("github", "state", "browser")


def test_rotation_cannot_attach_another_workspace_connector():
    a, _ = client("a")
    b, _ = client("b")
    connector = b.post("/api/assistant/connectors", json={"label": "Private"}).json()
    cid = a.post("/api/assistant/connections/demo").json()["id"]
    response = a.post(
        f"/api/assistant/connections/{cid}/rotate",
        json={
            "label": "Attempt",
            "provider": "generic",
            "engine": "sqlite",
            "config": {"connector_id": connector["id"], "profile": "private"},
        },
    )
    assert response.status_code == 404
    assert a.get("/api/assistant/connections").json()[0]["status"] == "untested"


def test_native_provider_urls_and_mismatched_engines():
    c, _ = client("a")
    for provider, engine, url in [
        (
            "firebase",
            "firebase_realtime",
            "https://example-default-rtdb.firebaseio.com",
        ),
        ("turso", "sqlite", "https://example-org.turso.io"),
    ]:
        response = c.post(
            "/api/assistant/connections",
            json={
                "label": "Native",
                "engine": engine,
                "provider": provider,
                "config": {"url": url},
            },
        )
        assert response.status_code == 200
        assert response.json()["summary"]["host"]
    bad = c.post(
        "/api/assistant/connections",
        json={
            "label": "Mismatch",
            "engine": "mongodb",
            "provider": "neon",
            "config": {"url": "mongodb://example.com/shop"},
        },
    )
    assert bad.status_code == 422
    bad = c.post(
        "/api/assistant/parse-connection",
        json={"url": "postgresql://example.com:broken/shop"},
    )
    assert bad.status_code == 422 and "invalid host or port" in bad.json()["detail"]


def test_maintenance_purges_expired_results_and_disposable_demo_accounts():
    c, uid = client("a")
    cid = c.post("/api/assistant/connections/demo").json()["id"]
    report = job(c, cid, "run", query="SELECT id FROM customers")
    demo = workspaces.user_for_identity("demo", "expired", "Disposable")
    workspaces.add_connection(
        demo["id"], "Synthetic", "sqlite", "generic", sqlite_demo(), {}
    )
    with store.connect() as db:
        db.execute(
            "UPDATE q_runs SET result_expires=? WHERE id=?",
            (time.time() - 1, report["report"]["run_id"]),
        )
        db.execute(
            "UPDATE q_users SET created=? WHERE id=?", (time.time() - 86401, demo["id"])
        )
    workspaces.maintenance()
    with store.connect() as db:
        assert db.execute("SELECT result_secret FROM q_runs").fetchone()[0] is None
        assert (
            db.execute(
                "SELECT count(*) FROM q_users WHERE id=?", (demo["id"],)
            ).fetchone()[0]
            == 0
        )
        assert db.execute("SELECT count(*) FROM q_connections").fetchone()[0] == 1


def test_optimizer_keeps_actual_evidence_when_model_budget_is_used(monkeypatch):
    c, uid = client("a")
    cid = c.post("/api/assistant/connections/demo").json()["id"]

    def unavailable(*args, **kwargs):
        raise AdapterError("Budget exhausted", "budget")

    monkeypatch.setattr(generation, "call", unavailable)
    report = job(c, cid, "optimize", query="SELECT id FROM orders WHERE status='paid'")
    assert report["state"] == "completed"
    assert report["report"]["plan"]["plan"]
    assert report["report"]["candidates"] == []
    assert "Budget exhausted" in report["report"]["diagnosis"]
    measured = job(
        c,
        cid,
        "benchmark",
        query="SELECT id FROM orders WHERE status='paid'",
        candidate="SELECT id FROM orders WHERE status='paid'",
        indexes=["CREATE INDEX qot_paid ON orders(status)"],
    )
    assert measured["state"] == "completed", measured
    assert measured["report"]["benchmark"]["correct"]
    assert measured["report"]["usage"]["model_calls"] == 0
    export_path = "/api/assistant/history/" + measured["report"]["run_id"] + "/export"
    exported = c.get(export_path)
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    assert exported.json()["summary"]["benchmark"]["correct"]
    other, _ = client("export-other")
    assert other.get(export_path).status_code == 404


def test_oidc_verifies_signature_audience_nonce_issuer_and_expiry():
    from authlib.jose import JsonWebKey, JsonWebToken
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    jwt = JsonWebToken(["RS256"])
    keys = {"keys":[key.as_dict()]}
    claims = {"sub":"subject", "aud":"client", "nonce":"expected", "iss":"https://accounts.google.com", "iat":int(time.time()), "exp":int(time.time())+300}
    def token(values):
        return jwt.encode({"alg":"RS256"},values,key).decode()
    assert accounts.verify_oidc("google",token(claims),"client","expected",keys)["sub"] == "subject"
    for patch in [{"aud":"other"},{"nonce":"other"},{"iss":"https://fake.example"},{"exp":int(time.time())-120}]:
        with pytest.raises(Exception):
            accounts.verify_oidc("google",token({**claims,**patch}),"client","expected",keys)
    tenant = "12345678-1234-1234-1234-123456789abc"
    ms = {**claims,"tid":tenant,"iss":f"https://login.microsoftonline.com/{tenant}/v2.0"}
    assert accounts.verify_oidc("microsoft",token(ms),"client","expected",keys)["tid"] == tenant
    with pytest.raises(Exception):
        accounts.verify_oidc("microsoft",token({**ms,"tid":"different"}),"client","expected",keys)


def test_failed_model_usage_is_visible_and_secrets_are_not_reported(monkeypatch):
    import httpx
    c, uid = client("a")
    monkeypatch.setattr(generation.httpx,"post",lambda *a,**k:httpx.Response(429,json={"error":"Sensitive provider body"}))
    with pytest.raises(AdapterError) as raised:
        generation.call(uid,generation.SYSTEM,{"request":"Synthetic"})
    assert raised.value.code == "model_access" and "HTTP 429" in str(raised.value)
    assert "Sensitive provider body" not in str(raised.value)
    metrics = usage.current(uid)
    assert metrics["last_24h"]["model_calls"] == 1
    assert metrics["model_calls_with_unknown_usage"] == 1
    assert metrics["tokens_used_or_reserved"] > 0
