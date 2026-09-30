"""Atomic token reservations. Unknown provider usage retains the reservation."""

import json
import os
import time
from backend import store
from backend.adapters.base import AdapterError


def bucket(user):
    return "user:" + user + ":tokens:" + time.strftime("%Y-%m-%d", time.gmtime())


def maximum():
    return min(
        100000, max(1000, int(os.environ.get("USER_DAILY_TOKEN_LIMIT", "20000")))
    )


def reserve(user, amount):
    now = time.time()
    key = bucket(user)
    with store.connect() as c:
        if not store.postgres():
            c.execute("BEGIN IMMEDIATE")
        row = (
            c.execute(
                "INSERT INTO limits(bucket,n,reset) VALUES(?,?,?) ON CONFLICT(bucket) DO UPDATE SET n=CASE WHEN limits.reset<=? THEN excluded.n ELSE limits.n+excluded.n END,reset=CASE WHEN limits.reset<=? THEN excluded.reset ELSE limits.reset END WHERE limits.reset<=? OR limits.n+excluded.n<=? RETURNING n",
                (key, amount, now + 86400, now, now, now, maximum()),
            ).fetchone()
            if amount <= maximum()
            else None
        )
    if not row:
        raise AdapterError(
            "Today's model token budget is used. Native queries and saved results remain available.",
            "budget",
        )
    return key


def reconcile(key, reserved, actual):
    if actual is None:
        return
    with store.connect() as c:
        c.execute(
            "UPDATE limits SET n=CASE WHEN n+? < 0 THEN 0 ELSE n+? END WHERE bucket=?",
            (actual - reserved, actual - reserved, key),
        )


def current(user):
    with store.connect() as c:
        row = c.execute(
            "SELECT n FROM limits WHERE bucket=? AND reset>?",
            (bucket(user), time.time()),
        ).fetchone()
        runs = c.execute(
            "SELECT usage FROM q_runs WHERE workspace_id=(SELECT id FROM q_workspaces WHERE user_id=?) AND created>?",
            (user, time.time() - 86400),
        ).fetchall()
        calls = c.execute(
            "SELECT usage FROM q_model_calls WHERE user_id=? AND created>?",
            (user, time.time() - 86400),
        ).fetchall()
        experiments = c.execute("SELECT report FROM jobs WHERE owner=? AND case_id IS NOT NULL AND report IS NOT NULL AND created>?", (user, time.time() - 86400)).fetchall()
    entries = [json.loads(r[0]) for r in runs]
    for experiment in experiments:
        measured = json.loads(experiment[0]).get("usage", {})
        entries.append({"database_calls": measured.get("tool_calls", 0), "seconds": measured.get("runtime_seconds", 0)})
    model_entries = [json.loads(r[0]) for r in calls]
    return {
        "daily_token_limit": maximum(),
        "tokens_used_or_reserved": row[0] if row else 0,
        "last_24h": {
            k: round(
                sum(
                    float(e.get(k) or 0)
                    for e in (
                        model_entries
                        if k
                        in {
                            "input_tokens",
                            "output_tokens",
                            "model_calls",
                            "estimated_cost_usd",
                        }
                        else entries
                    )
                ),
                6,
            )
            for k in [
                "input_tokens",
                "output_tokens",
                "model_calls",
                "database_calls",
                "seconds",
                "estimated_cost_usd",
            ]
        },
        "model_calls_with_unknown_usage": sum(
            e.get("input_tokens") is None or e.get("output_tokens") is None
            for e in model_entries
        ),
        "cost_note": "Estimate uses Groq published list prices; it is not a bill. Failed calls without usage retain their token reservation.",
    }


def record(user, measured):
    from backend.workspaces import identifier

    with store.connect() as c:
        c.execute(
            "INSERT INTO q_model_calls(id,user_id,usage,created) SELECT ?,id,?,? FROM q_users WHERE id=? AND status='active'",
            (identifier(), json.dumps(measured), time.time(), user),
        )
