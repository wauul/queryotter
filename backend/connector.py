"""Outbound-only, revocable, workspace-scoped local connector."""

import json
import hmac
import secrets
import time
from fastapi import Request, HTTPException
from pydantic import BaseModel, Field
from backend import store, workspaces, accounts
from backend.adapters.base import Adapter, AdapterError, Capabilities


def require_connector(user, cid):
    w = workspaces.workspace(user)
    with store.connect() as c:
        row = c.execute(
            "SELECT * FROM q_connectors WHERE id=? AND workspace_id=?", (cid, w["id"])
        ).fetchone()
    if not row:
        raise AdapterError("Local connector not found in this workspace.", "not_found")
    return dict(row)


def authenticate(cid, request):
    token = request.headers.get("authorization", "")
    with store.connect() as c:
        row = c.execute(
            "SELECT k.* FROM q_connectors k JOIN q_workspaces w ON w.id=k.workspace_id JOIN q_users u ON u.id=w.user_id WHERE k.id=? AND u.status='active'",
            (cid,),
        ).fetchone()
    if (
        not token.startswith("Bearer ")
        or not row
        or not hmac.compare_digest(accounts.digest(token[7:]), row["token_hash"])
    ):
        raise HTTPException(401, "Connector token is invalid or revoked.")
    return dict(row)


class Enrollment(BaseModel):
    label: str = Field(min_length=1, max_length=80)


class Completion(BaseModel):
    task_id: str = Field(max_length=40)
    response: dict


def register(router):
    @router.get("/connectors")
    def listing(request: Request):
        w = workspaces.workspace(accounts.current(request)["id"])
        with store.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT id,label,last_seen FROM q_connectors WHERE workspace_id=?",
                    (w["id"],),
                ).fetchall()
            ]

    @router.post("/connectors")
    def enroll(data: Enrollment, request: Request):
        user = accounts.current(request)["id"]
        if accounts.is_demo(user):
            raise HTTPException(
                403, "Sign in with a verified identity to enroll a connector."
            )
        w = workspaces.workspace(user)
        cid, token = workspaces.identifier(), secrets.token_urlsafe(32)
        with store.connect() as c:
            if (
                c.execute(
                    "SELECT count(*) FROM q_connectors WHERE workspace_id=?", (w["id"],)
                ).fetchone()[0]
                >= 3
            ):
                raise HTTPException(
                    429, "A workspace can enroll three local connectors."
                )
            c.execute(
                "INSERT INTO q_connectors VALUES(?,?,?,?,NULL)",
                (cid, w["id"], data.label, accounts.digest(token)),
            )
        return {
            "id": cid,
            "token": token,
            "note": "Shown once. Store this token only on your connector machine. Removing the connector revokes it.",
        }

    @router.post("/connectors/{cid}/remove")
    def remove(cid: str, request: Request):
        require_connector(accounts.current(request)["id"], cid)
        with store.connect() as c:
            c.execute("DELETE FROM q_connector_tasks WHERE connector_id=?", (cid,))
            c.execute("DELETE FROM q_connectors WHERE id=?", (cid,))
        return {"revoked": True}

    @router.post("/connectors/{cid}/poll")
    def poll(cid: str, request: Request):
        authenticate(cid, request)
        if not store.limit("connector:" + cid, 90, 60):
            raise HTTPException(429, "Connector polling limit reached.")
        with store.connect() as c:
            c.execute(
                "UPDATE q_connectors SET last_seen=? WHERE id=?", (time.time(), cid)
            )
            c.execute(
                "DELETE FROM q_connector_tasks WHERE connector_id=? AND expires<?",
                (cid, time.time()),
            )
            row = c.execute(
                "UPDATE q_connector_tasks SET state='running' WHERE state='queued' AND id=(SELECT id FROM q_connector_tasks WHERE connector_id=? AND state='queued' AND expires>? ORDER BY expires LIMIT 1) RETURNING *",
                (cid, time.time()),
            ).fetchone()
        return {
            "task": {
                "id": row["id"],
                "profile": row["profile"],
                "action": row["action"],
                "request": workspaces.decrypt(row["request_secret"]),
            }
            if row
            else None
        }

    @router.post("/connectors/{cid}/complete")
    def complete(cid: str, data: Completion, request: Request):
        authenticate(cid, request)
        if len(json.dumps(data.response, default=str).encode()) > 2_200_000:
            raise HTTPException(413, "Connector result exceeds its response budget.")
        with store.connect() as c:
            row = c.execute(
                "UPDATE q_connector_tasks SET state='completed',response_secret=? WHERE id=? AND connector_id=? AND state='running' AND expires>? RETURNING id",
                (workspaces.encrypt(data.response), data.task_id, cid, time.time()),
            ).fetchone()
        if not row:
            raise HTTPException(
                409, "Task expired, cancelled or belongs to another connector."
            )
        return {"accepted": True}


class RemoteAdapter(Adapter):
    def __init__(self, engine, config, check):
        super().__init__(config, check)
        from backend.adapters.registry import ADAPTERS

        self.engine, self.definition = engine, ADAPTERS[engine]
        self.dialect, self.capabilities = (
            self.definition.dialect,
            self.definition.capabilities,
        )
        from dataclasses import replace

        self.capabilities = replace(self.capabilities, controlled_benchmarking=False)
        self.limitations = [
            *self.definition.limitations,
            "Credentials stay on the scoped local connector machine.",
        ]
        self.cid, self.profile = config["connector_id"], config.get("profile", "")
        if not self.profile or len(self.profile) > 80:
            raise AdapterError(
                "Choose a configured local connector profile.", "connection_format"
            )

    def request(self, action, **data):
        task = workspaces.identifier()
        with store.connect() as c:
            row = c.execute(
                "SELECT last_seen FROM q_connectors WHERE id=?", (self.cid,)
            ).fetchone()
            if not row or not row[0] or row[0] < time.time() - 120:
                raise AdapterError(
                    "Local connector offline. Start it on the database network.",
                    "connector_offline",
                )
            c.execute(
                "INSERT INTO q_connector_tasks VALUES(?,?,?,?,?,NULL,'queued',?)",
                (
                    task,
                    self.cid,
                    self.profile,
                    action,
                    workspaces.encrypt({"engine": self.engine, **data}),
                    time.time() + 20,
                ),
            )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                self.check()
                with store.connect() as c:
                    row = c.execute(
                        "SELECT state,response_secret FROM q_connector_tasks WHERE id=? AND connector_id=?",
                        (task, self.cid),
                    ).fetchone()
                if not row:
                    raise AdapterError(
                        "Connector removed or task expired.", "connector_offline"
                    )
                if row["state"] == "completed":
                    answer = workspaces.decrypt(row["response_secret"])
                    if answer.get("error"):
                        raise AdapterError(
                            str(answer["error"])[:600],
                            answer.get("code", "connector_error"),
                        )
                    return answer["value"]
                time.sleep(0.25)
            raise AdapterError(
                "Connector task timed out. Check profile and database availability.",
                "timeout",
            )
        finally:
            with store.connect() as c:
                c.execute(
                    "DELETE FROM q_connector_tasks WHERE id=? AND connector_id=?",
                    (task, self.cid),
                )

    def discover(self):
        answer = self.request("discover")
        self.capabilities = Capabilities(**answer["capabilities"])
        from dataclasses import replace

        self.capabilities = replace(self.capabilities, controlled_benchmarking=False)
        return answer["metadata"]

    def validate(self, query, schema):
        return self.definition.validate(self, query, schema)

    def execute(self, query, schema):
        self.validate(query, schema)
        return self.request("execute", query=query)

    def plan(self, query, schema):
        self.validate(query, schema)
        return self.request("plan", query=query)

    def close(self):
        pass
