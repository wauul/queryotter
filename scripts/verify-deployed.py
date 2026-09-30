"""Exercise a hosted deployment with real job execution; never print credentials."""

import os, time, json, secrets, sys
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = sys.argv[1] if len(sys.argv) > 1 else "https://queryotter.vercel.app"


def main():
    evidence = {"url": BASE, "checks": []}
    with (
        httpx.Client(base_url=BASE, timeout=20) as a,
        httpx.Client(base_url=BASE, timeout=20) as b,
    ):
        assert a.get("/").status_code == 200
        for c in (a, b):
            assert c.get("/api/session").status_code == 200
        assert a.get("/api/health").json()["status"] == "ok"
        evidence["checks"].append("Hosted page and connector healthy")
        if "--owner" in sys.argv:
            assert a.post(
                "/api/login", json={"password": os.environ["ADMIN_PASSWORD"]}
            ).status_code == 200
        evidence["submission_mode"] = "owner" if "--owner" in sys.argv else "anonymous"
        key = secrets.token_hex(16)
        payload = {"case_id": "customer-orders", "request_key": key}
        response = a.post("/api/jobs", json=payload)
        assert response.status_code == 202, response.text
        job = response.json()
        id = job["id"]
        assert a.post("/api/jobs", json=payload).json()["id"] == id
        assert b.get("/api/jobs/" + id).status_code == 404
        assert b.get("/api/jobs/" + id + "/report").status_code == 404
        assert b.post("/api/jobs/" + id + "/cancel", json={}).status_code == 404
        evidence["checks"].append("Duplicate submission and cross-session isolation")
        deadline = time.monotonic() + 190
        while time.monotonic() < deadline:
            poll = a.get("/api/jobs/" + id)
            assert poll.status_code == 200, f"Job polling returned HTTP {poll.status_code}"
            job = poll.json()
            if job["state"] not in {"queued", "running"}:
                break
            time.sleep(1)
        assert job["state"] == "completed", job.get("error")
        assert job["report"]["usage"]["provider"] == "Groq / OpenAI-compatible"
        assert job["report"]["usage"]["input_tokens"] > 0
        assert all(
            c["correctness"]["passed"]
            for c in job["report"]["candidates"]
            if c["status"] == "verified improvement"
        )
        assert any(j["id"] == id for j in a.get("/api/jobs").json())
        assert a.get("/api/jobs/" + id + "/report").json() == job["report"]
        evidence["checks"].append(
            "Fresh Groq investigation, persisted history and report export"
        )
        evidence["job_id"] = id
        evidence["report"] = job["report"]
        cancel = a.post(
            "/api/jobs",
            json={"case_id": "sort-total", "request_key": secrets.token_hex(16)},
        )
        assert cancel.status_code == 202
        cid = cancel.json()["id"]
        a.post("/api/jobs/" + cid + "/cancel", json={})
        for _ in range(50):
            state = a.get("/api/jobs/" + cid).json()["state"]
            if state == "cancelled":
                break
            time.sleep(0.5)
        assert state == "cancelled"
        evidence["checks"].append("Cancellation reaches persisted terminal state")
        assert (
            a.post(
                "/api/jobs",
                json={"case_id": "unsafe", "request_key": secrets.token_hex(16)},
            ).status_code
            == 422
        )
        assert (
            a.post(
                "/api/login", json={"password": os.environ["ADMIN_PASSWORD"]}
            ).status_code
            == 200
        )
        invalid = a.post(
            "/api/connections",
            json={
                "label": "Invalid verification connection",
                "url": "postgresql://readonly:DO_NOT_EXPOSE@127.0.0.1:1/absent",
            },
        )
        assert invalid.status_code == 422 and "DO_NOT_EXPOSE" not in invalid.text
        evidence["checks"].append(
            "Unsafe SQL refused, owner auth and redacted invalid connection"
        )
    Path("docs/deployed-verification.json").write_text(
        json.dumps(evidence, indent=2, default=str), encoding="utf8"
    )
    print(
        json.dumps(
            {
                "url": BASE,
                "checks": evidence["checks"],
                "job_id": evidence["job_id"],
                "original_ms": job["report"]["original"]["median_ms"],
                "optimized_ms": job["report"]["best"]["optimized"]["median_ms"]
                if job["report"]["best"]
                else None,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
