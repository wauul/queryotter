"""Personal workspace HTTP API; database/model operations are durable worker jobs."""

import csv
import base64
import hashlib
import hmac
import io
import json
import os
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from backend import accounts, store, workspaces, usage
from backend.adapters.base import AdapterError
from backend.adapters.registry import ADAPTERS, catalog
from backend import providers

router = APIRouter(prefix="/api/assistant")
from backend.connector import register

register(router)


def account(request):
    return accounts.current(request)["id"]


@router.get("/catalog")
def support():
    workspaces.maintenance()
    return {
        "engines": catalog(),
        "providers": providers.presets(),
        "authentication": accounts.providers(),
    }


@router.get("/session")
def session(request: Request):
    user = accounts.current(request, optional=True)
    if not user:
        return {"user": None, "authentication": accounts.providers()}
    workspaces.prune(user["id"])
    return {
        "user": {k: user.get(k) for k in ["id", "name", "email"]},
        "workspace": workspaces.workspace(user["id"]),
        "usage": usage.current(user["id"]),
        "authentication": accounts.providers(),
        "demo": accounts.is_demo(user["id"]),
    }


@router.post("/auth/{provider}/start")
def sign_in(provider: str, request: Request, response: Response):
    if not store.limit(
        "oauth:"
        + hashlib.sha256(
            request.cookies.get("qot_oauth_browser", "").encode()
        ).hexdigest(),
        10,
        300,
    ):
        raise HTTPException(429, "Too many sign-in attempts. Try again shortly.")
    return accounts.start(provider, request, response)


@router.get("/auth/{provider}/callback")
def callback(provider: str, request: Request):
    response = HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/#workspace"><title>Signing in — QueryOtter</title><p>Sign-in verified. Opening your workspace…</p><a href="/#workspace">Open QueryOtter</a></html>'
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    accounts.callback(provider, request, response)
    return response


class OwnerLogin(BaseModel):
    password: str = Field(max_length=200)


@router.post("/auth/owner")
def owner_login(data: OwnerLogin, request: Request, response: Response):
    # Explicit operator access for administration/testing; this is not OAuth.
    if not store.limit("assistant-owner-login", 5, 300):
        raise HTTPException(
            429, "Too many owner sign-in attempts. Try again in five minutes."
        )
    expected = os.environ.get("ADMIN_PASSWORD", "")
    if not expected or not hmac.compare_digest(expected, data.password):
        raise HTTPException(401, "Incorrect owner password.")
    user = workspaces.user_for_identity("operator", "owner", "QueryOtter owner")
    accounts.issue_session(response, request, user["id"])
    return {"authenticated": True, "method": "operator password"}


@router.post("/logout")
def logout(request: Request, response: Response):
    accounts.logout(request, response)
    return {"authenticated": False}


@router.post("/demo/start")
def demo_start(request: Request, response: Response):
    existing = accounts.current(request, optional=True)
    if existing:
        return {"started": True}
    if not store.limit(
        "demo-accounts:" + time.strftime("%Y-%m-%d", time.gmtime()), 50, 86400
    ):
        raise HTTPException(
            429,
            "Today's public demo session budget is used. Published benchmark reports remain available.",
        )
    import secrets

    user = workspaces.user_for_identity("demo", secrets.token_hex(16), "Demo workspace")
    accounts.issue_session(response, request, user["id"], 86400)
    with store.connect() as c:
        c.execute(
            "UPDATE q_workspaces SET retention_days=1 WHERE user_id=?", (user["id"],)
        )
    return {
        "started": True,
        "demo": True,
        "note": "Synthetic data only. Sessions expire after one day; model calls share the public daily budget.",
    }


class Settings(BaseModel):
    name: str = Field(default="My workspace", min_length=1, max_length=80)
    timezone: str = Field(default="UTC", max_length=80)
    retention_days: int = Field(default=30, ge=1, le=90)


@router.post("/settings")
def settings(data: Settings, request: Request):
    user = account(request)
    w = workspaces.workspace(user)
    try:
        ZoneInfo(data.timezone)
    except Exception:
        raise AdapterError(
            "Choose a valid IANA time zone, such as Europe/Paris.", "timezone"
        ) from None
    with store.connect() as c:
        c.execute(
            "UPDATE q_workspaces SET name=?,timezone=?,retention_days=?,onboarded=1 WHERE id=? AND user_id=?",
            (data.name, data.timezone, data.retention_days, w["id"], user),
        )
    workspaces.prune(user)
    return workspaces.workspace(user)


@router.get("/connections")
def connections(request: Request):
    user = account(request)
    w = workspaces.workspace(user)
    with store.connect() as c:
        rows = c.execute(
            "SELECT id FROM q_connections WHERE workspace_id=? ORDER BY created DESC",
            (w["id"],),
        ).fetchall()
    return [workspaces.connection(user, row[0]) for row in rows]


class ConnectionInput(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    engine: str = Field(max_length=40)
    provider: str = Field(default="generic", max_length=40)
    config: dict


def prepare_connection(data):
    if data.engine not in ADAPTERS or data.provider not in {
        p["id"] for p in providers.presets()
    }:
        raise AdapterError("Select a supported engine and provider.", "unsupported")
    preset = next(p for p in providers.presets() if p["id"] == data.provider)
    if data.engine not in preset["engines"]:
        raise AdapterError(
            "This provider preset does not offer the selected engine.",
            "connection_format",
        )
    allowed = {
        "url",
        "auth_token",
        "path",
        "schema",
        "tls",
        "ca_certificate",
        "data",
        "service_account",
        "project_id",
        "database_id",
        "infer_document_schema",
        "connector_id",
        "profile",
    }
    if set(data.config) - allowed:
        raise AdapterError(
            "Unknown connection configuration fields.", "connection_format"
        )
    config = data.config.copy()
    for key, value in config.items():
        if key == "infer_document_schema":
            if not isinstance(value, bool):
                raise AdapterError("Document inference must be true or false.", "connection_format")
        elif key == "service_account":
            if not isinstance(value, dict):
                raise AdapterError("Service account credentials must be a JSON object.", "credentials")
        elif not isinstance(value, str):
            raise AdapterError("Connection text fields must contain strings.", "connection_format")
    if len(json.dumps(config).encode()) > 2_950_000:
        raise AdapterError(
            "Connection configuration exceeds its size budget.", "upload"
        )
    if config.get("url") and len(config["url"]) > 2000:
        raise AdapterError("Connection URL is too long.", "connection_format")
    if config.get("tls", "verify-full") != "verify-full":
        raise AdapterError(
            "Direct cloud connections require certificate and hostname verification. Use the scoped local connector for private development databases.",
            "tls",
        )
    summary = {
        "scope": "uploaded copy"
        if data.engine == "sqlite"
        else "direct public TLS connection",
        "schema": config.get("schema"),
        "secrets": "encrypted; never returned",
    }
    if config.get("url"):
        if (
            data.engine == "firebase_realtime"
            or data.engine == "sqlite"
            and config["url"].startswith("https://")
        ):
            try:
                parsed = urlparse(config["url"])
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError()
                summary.update(
                    {
                        "host": parsed.hostname,
                        "port": parsed.port,
                        "masked_url": "https://" + parsed.netloc + parsed.path,
                    }
                )
            except ValueError:
                raise AdapterError(
                    "Use the native HTTPS database URL without credentials, query parameters or fragments.",
                    "connection_format",
                ) from None
        else:
            parsed = providers.parse_url(config["url"])
            if (
                parsed["engine"] != data.engine
                and not (
                    data.engine == "cockroachdb" and parsed["engine"] == "postgresql"
                )
                and not (data.engine == "mariadb" and parsed["engine"] == "mysql")
            ):
                raise AdapterError(
                    "The connection URL dialect does not match the selected engine.",
                    "connection_format",
                )
            summary.update(parsed)
    if config.get("connector_id"):
        summary.update(
            {
                "scope": "scoped local connector",
                "connector_id": config["connector_id"],
                "profile": config.get("profile"),
            }
        )
    return config, summary


@router.post("/connections")
def add_connection(data: ConnectionInput, request: Request):
    if accounts.is_demo(account(request)):
        raise HTTPException(
            403,
            "Sign in with a verified identity to connect your own database. Demo workspaces use synthetic copies.",
        )
    config, summary = prepare_connection(data)
    if config.get("connector_id"):
        from backend.connector import require_connector

        require_connector(account(request), config["connector_id"])
    return workspaces.add_connection(
        account(request), data.label, data.engine, data.provider, config, summary
    )


@router.post("/connections/demo")
def add_demo(request: Request):
    from backend.demo import sqlite_demo

    return workspaces.add_connection(
        account(request),
        "Otter shop · SQLite copy",
        "sqlite",
        "generic",
        sqlite_demo(),
        {"scope": "seeded disposable SQLite copy", "synthetic": True},
    )


@router.post("/connections/{cid}/remove")
def remove_connection(cid: str, request: Request):
    workspaces.remove_connection(account(request), cid)
    return {"removed": True}


@router.get("/connections/{cid}/schema")
def schema(cid: str, request: Request):
    workspaces.connection(account(request), cid)
    metadata, revision = workspaces.cached_schema(cid)
    return {
        "metadata": metadata,
        "revision": revision,
        "needs_refresh": metadata is None,
    }


@router.post("/connections/{cid}/rotate")
def rotate(cid: str, data: ConnectionInput, request: Request):
    user = account(request)
    if accounts.is_demo(user):
        raise HTTPException(
            403,
            "Demo credentials cannot be rotated into a private database connection.",
        )
    d = workspaces.connection(user, cid)
    if data.engine != d["engine"]:
        raise AdapterError(
            "Create a new connection when changing database engines.",
            "connection_format",
        )
    config, summary = prepare_connection(data)
    if config.get("connector_id"):
        from backend.connector import require_connector

        require_connector(user, config["connector_id"])
    with store.connect() as c:
        c.execute(
            "UPDATE q_connections SET label=?,provider=?,secret=?,summary=?,status='untested',validated=NULL,capabilities=NULL WHERE id=? AND workspace_id=?",
            (
                data.label,
                data.provider,
                workspaces.encrypt(config),
                json.dumps(summary),
                cid,
                d["workspace_id"],
            ),
        )
        c.execute("DELETE FROM q_schema WHERE connection_id=?", (cid,))
    return workspaces.connection(user, cid)


class ParseInput(BaseModel):
    url: str = Field(max_length=2000)


@router.post("/parse-connection")
def parse_connection(data: ParseInput, request: Request):
    account(request)
    return providers.parse_url(data.url)


class JobInput(BaseModel):
    connection_id: str = Field(max_length=50)
    action: str = Field(max_length=30)
    prompt: str | None = Field(default=None, max_length=3000)
    query: str | None = Field(default=None, max_length=12000)
    previous_run: str | None = Field(default=None, max_length=50)
    candidate: str | None = Field(default=None, max_length=12000)
    indexes: list[str] = Field(default_factory=list, max_length=2)
    request_key: str = Field(min_length=8, max_length=100)


@router.post("/jobs", status_code=202)
def create_job(data: JobInput, request: Request):
    user = account(request)
    workspaces.connection(user, data.connection_id)
    if data.action not in {
        "test",
        "discover",
        "generate",
        "validate",
        "run",
        "optimize",
        "benchmark",
    }:
        raise AdapterError("Unknown assistant operation.", "unsupported")
    if (
        data.action == "generate"
        and not data.prompt
        or data.action in {"validate", "run", "optimize", "benchmark"}
        and not data.query
    ):
        raise AdapterError("Provide the request or native query for this operation.")
    if data.action == "benchmark" and not data.candidate:
        raise AdapterError("Select a candidate for the disposable-copy benchmark.")
    payload = data.model_dump(exclude={"request_key"})
    packed = json.dumps({"assistant": payload}, sort_keys=True)
    with store.connect() as c:
        previous = c.execute(
            "SELECT id,query FROM jobs WHERE owner=? AND request_key=?",
            (user, data.request_key),
        ).fetchone()
        if previous:
            if previous["query"] != packed:
                raise HTTPException(
                    409, "This request key belongs to another operation."
                )
            return store.get(previous["id"], user)
        active = c.execute(
            "SELECT count(*) FROM jobs WHERE owner=? AND state IN ('queued','running')",
            (user,),
        ).fetchone()[0]
    if active:
        raise HTTPException(
            429, "One active operation per workspace. Wait or select Cancel."
        )
    if not store.limit("user:" + user + ":requests", 30, 3600):
        raise HTTPException(429, "The hourly operation limit is reached.")
    try:
        return store.create(user, data.request_key, None, packed)
    except store.ActiveJob:
        raise HTTPException(429, "One active operation per workspace.") from None


@router.get("/jobs/{jid}")
def get_job(jid: str, request: Request):
    job = store.get(jid, account(request))
    if not job:
        raise HTTPException(404, "Operation not found.")
    job.pop("query", None)
    return job


@router.post("/jobs/{jid}/cancel")
def cancel(jid: str, request: Request):
    user = account(request)
    get_job(jid, request)
    with store.connect() as c:
        c.execute(
            "UPDATE jobs SET cancel=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END WHERE id=? AND owner=? AND state IN ('queued','running')",
            (jid, user),
        )
    return get_job(jid, request)


def run_record(user, rid, result=False):
    w = workspaces.workspace(user)
    with store.connect() as c:
        row = c.execute(
            "SELECT * FROM q_runs WHERE id=? AND workspace_id=?", (rid, w["id"])
        ).fetchone()
    if not row:
        raise HTTPException(404, "Query history entry not found.")
    record = dict(row)
    secret = record.pop("result_secret")
    record["usage"], record["summary"] = (
        json.loads(record["usage"]),
        json.loads(record["summary"]),
    )
    if result:
        if not secret or (record["result_expires"] or 0) <= time.time():
            raise HTTPException(
                410,
                "This result snapshot expired after 15 minutes. Select Run to create a new snapshot.",
            )
        return workspaces.decrypt(secret)
    return record


@router.get("/results/{rid}")
def results(rid: str, request: Request, page: int = 1, page_size: int = 50):
    data = run_record(account(request), rid, result=True)
    page_size = max(1, min(100, page_size))
    page = max(1, min(500, page))
    start = (page - 1) * page_size
    return {
        **{k: v for k, v in data.items() if k not in {"rows", "documents"}},
        "rows": data["rows"][start : start + page_size],
        "documents": data.get("documents", [])[start : start + page_size],
        "page": page,
        "page_size": page_size,
    }


@router.get("/results/{rid}/export")
def export_result(rid: str, request: Request, format: str = "json"):
    data = run_record(account(request), rid, result=True)
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)

        # Prevent spreadsheet formula evaluation when exporting untrusted values.
        def safe(v):
            s = "" if v is None else str(v)
            return (
                "'" + s
                if s.lstrip().startswith(("=", "+", "-", "@"))
                and not isinstance(v, (int, float))
                else s
            )

        writer.writerow([safe(v) for v in data["columns"]])
        writer.writerows([[safe(v) for v in row] for row in data["rows"]])
        body, media = output.getvalue(), "text/csv"
    elif format == "json":
        body, media = json.dumps(data, indent=2, default=str), "application/json"
    else:
        raise HTTPException(422, "Choose JSON or CSV export.")
    return Response(
        body,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="queryotter-{rid}.{format}"'
        },
    )


@router.get("/history")
def history(request: Request):
    user = account(request)
    workspaces.prune(user)
    w = workspaces.workspace(user)
    with store.connect() as c:
        rows = c.execute(
            "SELECT id FROM q_runs WHERE workspace_id=? ORDER BY created DESC LIMIT 100",
            (w["id"],),
        ).fetchall()
    return [run_record(user, r[0]) for r in rows]


@router.get("/history/{rid}/export")
def export_operation(rid: str, request: Request):
    record = run_record(account(request), rid)
    return Response(json.dumps(record, indent=2, default=str), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="queryotter-operation.json"'})


class SavedInput(BaseModel):
    connection_id: str = Field(max_length=50)
    name: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=12000)
    prompt: str | None = Field(default=None, max_length=3000)


@router.get("/saved")
def saved(request: Request):
    w = workspaces.workspace(account(request))
    with store.connect() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT * FROM q_saved WHERE workspace_id=? ORDER BY updated DESC LIMIT 100",
                (w["id"],),
            ).fetchall()
        ]


@router.post("/saved")
def save(data: SavedInput, request: Request):
    d = workspaces.connection(account(request), data.connection_id)
    with store.connect() as c:
        count = c.execute(
            "SELECT count(*) FROM q_saved WHERE workspace_id=?", (d["workspace_id"],)
        ).fetchone()[0]
        if count >= 100:
            raise HTTPException(429, "The workspace can store 100 saved queries.")
        rid = workspaces.identifier()
        c.execute(
            "INSERT INTO q_saved VALUES(?,?,?,?,?,?,?,?)",
            (
                rid,
                d["workspace_id"],
                data.connection_id,
                data.name,
                data.query,
                data.prompt,
                time.time(),
                time.time(),
            ),
        )
    return {"id": rid}


@router.post("/saved/{rid}/remove")
def remove_saved(rid: str, request: Request):
    w = workspaces.workspace(account(request))
    with store.connect() as c:
        c.execute("DELETE FROM q_saved WHERE id=? AND workspace_id=?", (rid, w["id"]))
    return {"removed": True}


@router.post("/history/clear")
def clear_history(request: Request):
    user = account(request)
    w = workspaces.workspace(user)
    with store.connect() as c:
        c.execute("DELETE FROM q_runs WHERE workspace_id=?", (w["id"],))
        ids = c.execute(
            "SELECT id FROM jobs WHERE owner=? AND state NOT IN ('queued','running')",
            (user,),
        ).fetchall()
        for row in ids:
            c.execute("DELETE FROM events WHERE job=?", (row[0],))
        c.execute(
            "DELETE FROM jobs WHERE owner=? AND state NOT IN ('queued','running')",
            (user,),
        )
    return {"removed": True}


@router.get("/account/export")
def export_account(request: Request):
    user = accounts.current(request)
    with store.connect() as c:
        experiments = c.execute("SELECT * FROM jobs WHERE owner=? AND case_id IS NOT NULL ORDER BY created DESC LIMIT 100", (user["id"],)).fetchall()
    data = {
        "account": {k: user.get(k) for k in ["id", "name", "email", "created"]},
        "workspace": workspaces.workspace(user["id"]),
        "connections": connections(request),
        "saved_queries": saved(request),
        "history": history(request),
        "postgresql_experiments": [store.job(row) for row in experiments],
        "note": "Database credentials are excluded. Result snapshots must be exported separately within their 15-minute lifetime.",
    }
    return Response(
        json.dumps(data, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="queryotter-account.json"'
        },
    )


class DeleteInput(BaseModel):
    confirmation: str = Field(max_length=30)


@router.post("/account/delete")
def delete(data: DeleteInput, request: Request, response: Response):
    if data.confirmation != "DELETE":
        raise HTTPException(422, "Enter DELETE to confirm account deletion.")
    result = workspaces.delete_account(account(request))
    accounts.set_cookie(response, request, "qot_auth", "", 0)
    return result


class PrismaInput(BaseModel):
    source: str = Field(max_length=30000)


@router.post("/connections/{cid}/prisma")
def prisma(cid: str, data: PrismaInput, request: Request):
    from backend.prisma_context import parse, reconcile

    user = account(request)
    connection = workspaces.connection(user, cid, secret=True)
    metadata, _ = workspaces.cached_schema(cid)
    if not metadata:
        raise HTTPException(
            409,
            "Test or refresh the connection before importing optional Prisma context.",
        )
    models = reconcile(parse(data.source), metadata)
    config = connection["config"]
    config["prisma_models"] = models
    with store.connect() as c:
        c.execute(
            "UPDATE q_connections SET secret=? WHERE id=? AND workspace_id=?",
            (workspaces.encrypt(config), cid, connection["workspace_id"]),
        )
    return {
        "models": models,
        "note": "Database discovery remains authoritative. Prisma does not establish a connection or independently verify relationships.",
    }
