"""Workspace authorization and encrypted application data, shared by API and worker."""

import hashlib
import json
import os
import time
import uuid
from cryptography.fernet import Fernet
from backend import store
from backend.adapters.base import AdapterError


def identifier():
    return uuid.uuid4().hex


def encrypt(value):
    return (
        Fernet(os.environ["ENCRYPTION_KEY"].encode())
        .encrypt(json.dumps(value, default=str).encode())
        .decode()
    )


def decrypt(value):
    return json.loads(
        Fernet(os.environ["ENCRYPTION_KEY"].encode()).decrypt(value.encode())
    )


def init():
    real = "DOUBLE PRECISION" if store.postgres() else "REAL"
    statements = [
        f"CREATE TABLE IF NOT EXISTS q_users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT,created {real},status TEXT NOT NULL DEFAULT 'active')",
        "CREATE TABLE IF NOT EXISTS q_identities(provider TEXT NOT NULL,subject TEXT NOT NULL,user_id TEXT NOT NULL REFERENCES q_users(id),PRIMARY KEY(provider,subject))",
        f"CREATE TABLE IF NOT EXISTS q_sessions(hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES q_users(id),created {real},expires {real},last_seen {real})",
        f"CREATE TABLE IF NOT EXISTS q_oauth(state TEXT PRIMARY KEY,provider TEXT NOT NULL,browser_hash TEXT NOT NULL,secret TEXT NOT NULL,expires {real})",
        "CREATE TABLE IF NOT EXISTS q_workspaces(id TEXT PRIMARY KEY,user_id TEXT NOT NULL UNIQUE REFERENCES q_users(id),name TEXT NOT NULL,onboarded INTEGER NOT NULL DEFAULT 0,retention_days INTEGER NOT NULL DEFAULT 30,timezone TEXT NOT NULL DEFAULT 'UTC')",
        f"CREATE TABLE IF NOT EXISTS q_connections(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES q_workspaces(id),label TEXT NOT NULL,engine TEXT NOT NULL,provider TEXT NOT NULL,secret TEXT NOT NULL,status TEXT NOT NULL,validated {real},capabilities TEXT,summary TEXT NOT NULL,created {real})",
        f"CREATE TABLE IF NOT EXISTS q_schema(connection_id TEXT PRIMARY KEY REFERENCES q_connections(id),secret TEXT NOT NULL,expires {real},revision TEXT NOT NULL)",
        f"CREATE TABLE IF NOT EXISTS q_saved(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES q_workspaces(id),connection_id TEXT NOT NULL REFERENCES q_connections(id),name TEXT NOT NULL,query TEXT NOT NULL,prompt TEXT,created {real},updated {real})",
        f"CREATE TABLE IF NOT EXISTS q_runs(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES q_workspaces(id),connection_id TEXT NOT NULL REFERENCES q_connections(id),kind TEXT NOT NULL,query TEXT,prompt TEXT,usage TEXT NOT NULL,summary TEXT NOT NULL,result_secret TEXT,result_expires {real},created {real})",
        f"CREATE TABLE IF NOT EXISTS q_model_calls(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES q_users(id),usage TEXT NOT NULL,created {real})",
        f"CREATE TABLE IF NOT EXISTS q_connectors(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES q_workspaces(id),label TEXT NOT NULL,token_hash TEXT NOT NULL,last_seen {real})",
        f"CREATE TABLE IF NOT EXISTS q_connector_tasks(id TEXT PRIMARY KEY,connector_id TEXT NOT NULL REFERENCES q_connectors(id),profile TEXT NOT NULL,action TEXT NOT NULL,request_secret TEXT NOT NULL,response_secret TEXT,state TEXT NOT NULL,expires {real})",
        "CREATE INDEX IF NOT EXISTS q_runs_workspace ON q_runs(workspace_id,created DESC)",
        "CREATE INDEX IF NOT EXISTS q_connections_workspace ON q_connections(workspace_id)",
        "CREATE INDEX IF NOT EXISTS q_model_calls_user ON q_model_calls(user_id,created)",
    ]
    with store.connect() as c:
        for statement in statements:
            c.execute(statement)


def user_for_identity(provider, subject, name, email=None):
    with store.connect() as c:
        row = c.execute(
            "SELECT u.* FROM q_users u JOIN q_identities i ON u.id=i.user_id WHERE i.provider=? AND i.subject=?",
            (provider, subject),
        ).fetchone()
        if row:
            return dict(row)
        uid = identifier()
        c.execute(
            "INSERT INTO q_users(id,name,email,created) VALUES(?,?,?,?)",
            (uid, name[:100], email[:254] if email else None, time.time()),
        )
        c.execute("INSERT INTO q_identities VALUES(?,?,?)", (provider, subject, uid))
        wid = identifier()
        c.execute(
            "INSERT INTO q_workspaces(id,user_id,name) VALUES(?,?,?)",
            (wid, uid, "My workspace"),
        )
    return {"id": uid, "name": name[:100], "email": email, "status": "active"}


def workspace(user_id):
    with store.connect() as c:
        row = c.execute(
            "SELECT w.* FROM q_workspaces w JOIN q_users u ON u.id=w.user_id WHERE w.user_id=? AND u.status='active'",
            (user_id,),
        ).fetchone()
    if not row:
        raise AdapterError("Account or workspace not found.", "not_found")
    return dict(row)


def require_workspace(user_id, workspace_id):
    w = workspace(user_id)
    if w["id"] != workspace_id:
        raise AdapterError("Workspace not found.", "not_found")
    return w


def connection(user_id, connection_id, *, secret=False):
    w = workspace(user_id)
    with store.connect() as c:
        row = c.execute(
            "SELECT * FROM q_connections WHERE id=? AND workspace_id=?",
            (connection_id, w["id"]),
        ).fetchone()
    if not row:
        raise AdapterError("Connection not found.", "not_found")
    d = dict(row)
    d["capabilities"] = json.loads(d["capabilities"]) if d["capabilities"] else None
    d["summary"] = json.loads(d["summary"])
    d["configuration_revision"] = hashlib.sha256(d["secret"].encode()).hexdigest()
    if secret:
        d["config"] = decrypt(d["secret"])
    d.pop("secret")
    return d


def add_connection(user_id, label, engine, provider, config, summary):
    w = workspace(user_id)
    with store.connect() as c:
        count = c.execute(
            "SELECT count(*) FROM q_connections WHERE workspace_id=?", (w["id"],)
        ).fetchone()[0]
        if count >= 10:
            raise AdapterError(
                "A workspace can store at most ten connections. Remove an unused connection.",
                "budget",
            )
        cid = identifier()
        c.execute(
            "INSERT INTO q_connections(id,workspace_id,label,engine,provider,secret,status,summary,created) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                cid,
                w["id"],
                label,
                engine,
                provider,
                encrypt(config),
                "untested",
                json.dumps(summary),
                time.time(),
            ),
        )
    return connection(user_id, cid)


def remove_connection(user_id, cid):
    d = connection(user_id, cid)
    with store.connect() as c:
        jobs = c.execute(
            "SELECT id,query FROM jobs WHERE owner=?", (user_id,)
        ).fetchall()
        for job in jobs:
            try:
                references = (
                    json.loads(job["query"]).get("assistant", {}).get("connection_id")
                    == cid
                )
            except (ValueError, TypeError):
                references = False
            if references:
                c.execute("DELETE FROM events WHERE job=?", (job["id"],))
                c.execute(
                    "DELETE FROM jobs WHERE id=? AND owner=?", (job["id"], user_id)
                )
        c.execute("DELETE FROM q_schema WHERE connection_id=?", (cid,))
        c.execute(
            "DELETE FROM q_saved WHERE connection_id=? AND workspace_id=?",
            (cid, d["workspace_id"]),
        )
        c.execute(
            "DELETE FROM q_runs WHERE connection_id=? AND workspace_id=?",
            (cid, d["workspace_id"]),
        )
        c.execute(
            "DELETE FROM q_connections WHERE id=? AND workspace_id=?",
            (cid, d["workspace_id"]),
        )
    return True


def cache_schema(cid, metadata):
    revision = hashlib.sha256(
        json.dumps(metadata, sort_keys=True, default=str).encode()
    ).hexdigest()
    with store.connect() as c:
        c.execute(
            "INSERT INTO q_schema VALUES(?,?,?,?) ON CONFLICT(connection_id) DO UPDATE SET secret=excluded.secret,expires=excluded.expires,revision=excluded.revision",
            (cid, encrypt(metadata), time.time() + 300, revision),
        )
    return revision


def cached_schema(cid):
    with store.connect() as c:
        row = c.execute(
            "SELECT * FROM q_schema WHERE connection_id=? AND expires>?",
            (cid, time.time()),
        ).fetchone()
    return (decrypt(row["secret"]), row["revision"]) if row else (None, None)


def prune(user_id):
    w = workspace(user_id)
    before = time.time() - w["retention_days"] * 86400
    with store.connect() as c:
        c.execute(
            "UPDATE q_runs SET result_secret=NULL WHERE workspace_id=? AND result_expires<?",
            (w["id"], time.time()),
        )
        c.execute(
            "DELETE FROM q_runs WHERE workspace_id=? AND created<?", (w["id"], before)
        )
        rows = c.execute(
            "SELECT id FROM jobs WHERE owner=? AND created<? AND state NOT IN ('queued','running')",
            (user_id, before),
        ).fetchall()
        for row in rows:
            c.execute("DELETE FROM events WHERE job=?", (row["id"],))
            c.execute("DELETE FROM jobs WHERE id=? AND owner=?", (row["id"], user_id))


def delete_account(user_id):
    w = workspace(user_id)
    with store.connect() as c:
        c.execute("UPDATE q_users SET status='deleting' WHERE id=?", (user_id,))
        c.execute("DELETE FROM q_sessions WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM q_model_calls WHERE user_id=?", (user_id,))
        jobs = c.execute("SELECT id FROM jobs WHERE owner=?", (user_id,)).fetchall()
        for job in jobs:
            c.execute("DELETE FROM events WHERE job=?", (job["id"],))
        c.execute("DELETE FROM jobs WHERE owner=?", (user_id,))
        connectors = c.execute(
            "SELECT id FROM q_connectors WHERE workspace_id=?", (w["id"],)
        ).fetchall()
        for item in connectors:
            c.execute(
                "DELETE FROM q_connector_tasks WHERE connector_id=?", (item["id"],)
            )
        c.execute("DELETE FROM q_connectors WHERE workspace_id=?", (w["id"],))
        connections = c.execute(
            "SELECT id FROM q_connections WHERE workspace_id=?", (w["id"],)
        ).fetchall()
        for item in connections:
            c.execute("DELETE FROM q_schema WHERE connection_id=?", (item["id"],))
        for table in ["q_runs", "q_saved", "q_connections"]:
            c.execute("DELETE FROM " + table + " WHERE workspace_id=?", (w["id"],))
        c.execute("DELETE FROM q_workspaces WHERE id=?", (w["id"],))
        c.execute("DELETE FROM q_identities WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM q_users WHERE id=?", (user_id,))
        c.execute("DELETE FROM limits WHERE bucket LIKE ?", (f"user:{user_id}:%",))
    return {
        "deleted": True,
        "note": "Removed from the active application. Hosting backups expire under the hosting provider’s retention policy.",
    }


def maintenance():
    """Hourly request-driven cleanup, including accounts that have stopped visiting."""
    if not store.limit("workspace-maintenance", 1, 3600):
        return
    now = time.time()
    with store.connect() as c:
        c.execute("DELETE FROM q_oauth WHERE expires<?", (now,))
        c.execute(
            "DELETE FROM q_sessions WHERE expires<? OR last_seen<?", (now, now - 86400)
        )
        c.execute("DELETE FROM q_schema WHERE expires<?", (now,))
        c.execute("DELETE FROM q_connector_tasks WHERE expires<?", (now,))
        c.execute("UPDATE q_runs SET result_secret=NULL WHERE result_expires<?", (now,))
        c.execute(
            "DELETE FROM q_model_calls WHERE EXISTS(SELECT 1 FROM q_workspaces w WHERE w.user_id=q_model_calls.user_id AND q_model_calls.created<?-w.retention_days*86400)",
            (now,),
        )
        c.execute(
            "DELETE FROM q_runs WHERE EXISTS(SELECT 1 FROM q_workspaces w WHERE w.id=q_runs.workspace_id AND q_runs.created<?-w.retention_days*86400)",
            (now,),
        )
        expired = c.execute(
            "SELECT j.id FROM jobs j JOIN q_workspaces w ON w.user_id=j.owner WHERE j.state NOT IN ('queued','running') AND j.created<?-w.retention_days*86400",
            (now,),
        ).fetchall()
        for row in expired:
            c.execute("DELETE FROM events WHERE job=?", (row[0],))
            c.execute("DELETE FROM jobs WHERE id=?", (row[0],))
        demos = c.execute(
            "SELECT u.id FROM q_users u JOIN q_identities i ON i.user_id=u.id WHERE i.provider='demo' AND u.created<? LIMIT 50",
            (now - 86400,),
        ).fetchall()
        c.execute(
            "DELETE FROM limits WHERE reset<? AND bucket NOT LIKE ?",
            (now - 86400, "user:%"),
        )
    for demo in demos:
        delete_account(demo[0])
