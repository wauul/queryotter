import sqlite3, json, time, uuid, os
from pathlib import Path

DB = Path(os.environ.get("JOB_STORE", ".data/jobs.sqlite3"))


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    with connect() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_key TEXT NOT NULL, case_id TEXT, query TEXT, state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, cancel INTEGER NOT NULL DEFAULT 0, report TEXT, error TEXT, UNIQUE(owner,request_key));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, stage TEXT, message TEXT, at REAL);
        CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY, owner TEXT NOT NULL, label TEXT NOT NULL, secret TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS limits(bucket TEXT PRIMARY KEY, n INTEGER NOT NULL, reset REAL NOT NULL);""")


def job(row):
    if not row:
        return None
    d = dict(row)
    d["report"] = json.loads(d["report"]) if d["report"] else None
    with connect() as c:
        d["events"] = [
            dict(x)
            for x in c.execute(
                "SELECT stage,message,at FROM events WHERE job=? ORDER BY id",
                (d["id"],),
            )
        ]
    d.pop("request_key", None)
    d.pop("owner", None)
    return d


def get(id, owner):
    with connect() as c:
        return job(
            c.execute(
                "SELECT * FROM jobs WHERE id=? AND owner=?", (id, owner)
            ).fetchone()
        )


def create(owner, key, case_id, query):
    with connect() as c:
        c.execute(
            "INSERT OR IGNORE INTO jobs(id,owner,request_key,case_id,query,state,created,updated) VALUES(?,?,?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                owner,
                key,
                case_id,
                query,
                "queued",
                time.time(),
                time.time(),
            ),
        )
        return job(
            c.execute(
                "SELECT * FROM jobs WHERE owner=? AND request_key=?", (owner, key)
            ).fetchone()
        )


def event(id, stage, message):
    with connect() as c:
        c.execute(
            "INSERT INTO events(job,stage,message,at) VALUES(?,?,?,?)",
            (id, stage, message, time.time()),
        )
        c.execute("UPDATE jobs SET updated=? WHERE id=?", (time.time(), id))


def finish(id, state, report=None, error=None):
    with connect() as c:
        c.execute(
            "UPDATE jobs SET state=?,report=?,error=?,updated=? WHERE id=?",
            (
                state,
                json.dumps(report, default=str) if report else None,
                error,
                time.time(),
                id,
            ),
        )


def claim():
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT * FROM jobs WHERE state='queued' AND cancel=0 ORDER BY created LIMIT 1"
        ).fetchone()
        if row:
            c.execute(
                "UPDATE jobs SET state='running',attempts=attempts+1,updated=? WHERE id=?",
                (time.time(), row["id"]),
            )
        return dict(row) if row else None


def limit(bucket, maximum, window):
    now = time.time()
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT n,reset FROM limits WHERE bucket=?", (bucket,)
        ).fetchone()
        if row and row["reset"] > now and row["n"] >= maximum:
            return False
        if not row or row["reset"] <= now:
            c.execute(
                "INSERT OR REPLACE INTO limits VALUES(?,1,?)", (bucket, now + window)
            )
        else:
            c.execute("UPDATE limits SET n=n+1 WHERE bucket=?", (bucket,))
        return True
