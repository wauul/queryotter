import os, json, time, hashlib, hmac, secrets, base64
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
from backend import store
from backend.cases import CASES, BY_ID
from backend.safety import validate_query, Unsupported
from dotenv import load_dotenv

load_dotenv()
store.init()
app = FastAPI(title="QueryOtter", docs_url=None, redoc_url=None)


@app.middleware("http")
async def guard(request, call_next):
    if request.url.path == "/healthz" and request.method == "GET":
        return await call_next(request)
    expected = os.environ.get("SERVICE_TOKEN")
    if not expected or not hmac.compare_digest(
        request.headers.get("x-service-token", ""), expected
    ):
        return JSONResponse(
            {"detail": "Worker service authentication required."}, status_code=401
        )
    if int(request.headers.get("content-length", "0")) > 18000:
        return JSONResponse({"detail": "Request too large."}, status_code=413)
    # Refuse cross-origin writes; reverse proxy supplies canonical origin.
    origin = request.headers.get("origin")
    allowed = request.headers.get("x-app-origin")
    if (
        request.method not in ("GET", "HEAD")
        and origin
        and allowed
        and origin != allowed
    ):
        return JSONResponse(
            {"detail": "Cross-origin writes are not allowed."}, status_code=403
        )
    return await call_next(request)


def signed(owner):
    payload = base64.urlsafe_b64encode(
        json.dumps({"id": owner, "expires": time.time() + 86400}).encode()
    ).decode()
    return (
        payload
        + "."
        + hmac.new(
            os.environ["SESSION_SECRET"].encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
    )


def owner(request):
    try:
        payload, signature = request.cookies["qot_session"].split(".")
        expected = hmac.new(
            os.environ["SESSION_SECRET"].encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        value = json.loads(base64.urlsafe_b64decode(payload))
        if value["expires"] < time.time():
            raise ValueError()
        return value["id"]
    except Exception:
        raise HTTPException(401, "Start a session first.") from None


def cookie(response, request, id):
    response.set_cookie(
        "qot_session",
        signed(id),
        httponly=True,
        secure=request.headers.get("x-forwarded-proto") == "https",
        samesite="lax",
        max_age=86400,
    )


def require_admin(request):
    if owner(request) != "admin":
        raise HTTPException(
            401, "Owner sign-in is required for live connections and custom queries."
        )


def require_job(id, request):
    j = store.get(id, owner(request))
    if not j:
        raise HTTPException(404, "Investigation not found.")
    return j


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "worker": "separate process",
        "live_mode": "metadata and non-executing plans only",
    }


@app.get("/api/session")
def session(request: Request, response: Response):
    try:
        id = owner(request)
    except HTTPException:
        id = "anon_" + secrets.token_hex(16)
    cookie(response, request, id)
    return {"authenticated": id == "admin", "live_enabled": True}


@app.get("/healthz", include_in_schema=False)
def platform_health():
    return {"status": "ok"}


class Login(BaseModel):
    password: str = Field(max_length=200)


@app.post("/api/login")
def login(data: Login, request: Request, response: Response):
    who = owner(request)
    if not store.limit("login:" + who, 5, 300):
        raise HTTPException(
            429, "Too many sign-in attempts. Try again in five minutes."
        )
    expected = os.environ.get("ADMIN_PASSWORD", "")
    if not expected or not hmac.compare_digest(data.password, expected):
        raise HTTPException(401, "Incorrect owner password.")
    cookie(response, request, "admin")
    return {"authenticated": True}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    cookie(response, request, "anon_" + secrets.token_hex(16))
    return {"authenticated": False}


@app.get("/api/examples")
def examples():
    return [{k: v for k, v in c.items() if k != "baseline"} for c in CASES]


@app.get("/api/reports/{case_id}")
def cached(case_id: str):
    if case_id not in BY_ID:
        raise HTTPException(404, "Unknown example.")
    path = Path("public/reports") / (case_id + ".json")
    if not path.exists():
        raise HTTPException(
            404, "No published measurement yet; start an investigation."
        )
    return json.loads(path.read_text(encoding="utf8"))


class JobInput(BaseModel):
    case_id: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, max_length=12000)
    connection_id: str | None = Field(default=None, max_length=100)
    request_key: str = Field(min_length=8, max_length=100)


@app.post("/api/jobs", status_code=202)
def create(data: JobInput, request: Request):
    who = owner(request)
    # Idempotency is checked before consuming rate or model budget.
    with store.connect() as c:
        previous = c.execute(
            "SELECT id,query,case_id FROM jobs WHERE owner=? AND request_key=?",
            (who, data.request_key),
        ).fetchone()
        if previous:
            if previous["case_id"] != data.case_id:
                raise HTTPException(
                    409, "Request key already belongs to another input."
                )
            if data.connection_id:
                same = previous["query"] == json.dumps(
                    {
                        "live": data.connection_id,
                        "sql": BY_ID[data.case_id]["sql"]
                        if data.case_id in BY_ID
                        else data.query,
                    }
                )
            elif data.case_id:
                same = previous["query"] == validate_query(BY_ID[data.case_id]["sql"])
            else:
                try:
                    same = previous["query"] == validate_query(data.query or "")
                except Unsupported:
                    same = False
            if not same:
                raise HTTPException(
                    409,
                    "Request key already belongs to different SQL or a different connection.",
                )
            return store.get(previous["id"], who)
        pending = c.execute(
            "SELECT count(*) FROM jobs WHERE owner=? AND state IN ('queued','running')",
            (who,),
        ).fetchone()[0]
    if pending >= 1:
        raise HTTPException(
            429,
            "One active investigation per session. Cancel or wait for the current run.",
        )
    if data.case_id:
        if data.case_id not in BY_ID:
            raise HTTPException(400, "Unknown seeded example.")
        query = BY_ID[data.case_id]["sql"]
    else:
        require_admin(request)
        if not data.query:
            raise HTTPException(400, "Provide a SELECT query.")
        query = data.query
    if data.connection_id:
        require_admin(request)
        with store.connect() as c:
            if not c.execute(
                "SELECT 1 FROM connections WHERE id=? AND owner=?",
                (data.connection_id, who),
            ).fetchone():
                raise HTTPException(404, "Connection not found.")
        query = json.dumps({"live": data.connection_id, "sql": query})
    else:
        try:
            query = validate_query(query)
        except Unsupported as e:
            raise HTTPException(422, str(e)) from None
    if not store.limit("requests:" + who, 10, 3600):
        raise HTTPException(429, "Hourly job limit reached.")
    if who != "admin" and not store.limit(
        "demo:" + time.strftime("%Y-%m-%d", time.gmtime()),
        int(os.environ.get("DEMO_DAILY_LIMIT", "6")),
        86400,
    ):
        raise HTTPException(
            429,
            "Today’s public model-run budget is used. Published reports remain available.",
        )
    try:
        return store.create(who, data.request_key, data.case_id, query)
    except store.ActiveJob:
        raise HTTPException(429, "One active investigation per session.") from None


@app.get("/api/jobs")
def history(request: Request):
    with store.connect() as c:
        return [
            store.job(r)
            for r in c.execute(
                "SELECT * FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 30",
                (owner(request),),
            ).fetchall()
        ]


@app.get("/api/jobs/{id}")
def get_job(id: str, request: Request):
    return require_job(id, request)


@app.post("/api/jobs/{id}/cancel")
def cancel(id: str, request: Request):
    j = require_job(id, request)
    if j["state"] in {"queued", "running"}:
        with store.connect() as c:
            c.execute(
                "UPDATE jobs SET cancel=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END WHERE id=?",
                (id,),
            )
    return require_job(id, request)


@app.get("/api/jobs/{id}/report")
def export(id: str, request: Request):
    j = require_job(id, request)
    if not j["report"]:
        raise HTTPException(409, "The report is not ready.")
    return Response(
        json.dumps(j["report"], indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="queryotter-{id}.json"'},
    )


class ConnectionInput(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=10, max_length=2000)


@app.post("/api/connections")
def connection(data: ConnectionInput, request: Request):
    require_admin(request)
    u = urlparse(data.url)
    if u.scheme not in {"postgres", "postgresql"} or not u.hostname:
        raise HTTPException(422, "Use a PostgreSQL connection URL.")
    if (
        u.hostname not in {"localhost", "127.0.0.1"}
        and "sslmode=verify-full" not in data.url
    ):
        raise HTTPException(422, "Remote connections require sslmode=verify-full.")
    secret = (
        Fernet(os.environ["ENCRYPTION_KEY"].encode())
        .encrypt(data.url.encode())
        .decode()
    )
    id = secrets.token_hex(16)
    # Validate least privilege before persistence. Never echo connection strings or provider errors.
    from backend.live import inspect_connection

    try:
        inspect_connection(data.url)
    except Exception:
        raise HTTPException(
            422,
            "Connection failed or role is too privileged. Require a read-only login with no schema CREATE permission; check TLS and network access.",
        ) from None
    with store.connect() as c:
        c.execute(
            "INSERT INTO connections VALUES(?,?,?,?)",
            (id, owner(request), data.label, secret),
        )
    return {"id": id, "label": data.label, "mode": "non-executing plans only"}


@app.get("/api/connections")
def connections(request: Request):
    require_admin(request)
    with store.connect() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT id,label FROM connections WHERE owner=?", (owner(request),)
            )
        ]
