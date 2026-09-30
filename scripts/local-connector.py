"""Run this outbound-only connector on your trusted database network."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from backend.adapters.registry import ADAPTERS
from backend.adapters.network import network_scope
from backend.adapters.base import AdapterError


def process_task(task, profiles):
    profile = profiles.get(task["profile"])
    try:
        if not profile or profile["engine"] != task["request"]["engine"]:
            raise AdapterError(
                "Requested profile absent or has a different engine.", "profile"
            )
        if task["action"] not in {"discover", "execute", "plan"}:
            raise AdapterError("Unsupported connector operation.", "unsupported")
        hosts = profile.get("allowed_hosts", [])
        if not hosts or any(
            h in {"169.254.169.254", "metadata.google.internal"} for h in hosts
        ):
            raise AdapterError(
                "Configure explicit database hosts; metadata endpoints are forbidden.",
                "profile",
            )
        with network_scope(private_hosts=tuple(hosts)):
            definition = ADAPTERS[profile["engine"]]
            adapter = definition.__new__(definition)
            try:
                definition.__init__(adapter, profile["config"])
                metadata = adapter.discover()
                value = (
                    {
                        "metadata": metadata,
                        "capabilities": adapter.capabilities.public(),
                    }
                    if task["action"] == "discover"
                    else getattr(adapter, task["action"])(
                        task["request"]["query"], metadata
                    )
                )
            finally:
                if hasattr(adapter, "temporary_files"):
                    adapter.close()
        return {"value": value}
    except AdapterError as error:
        return {"error": str(error), "code": error.code}
    except Exception as error:
        return {
            "error": "Local operation failed ("
            + type(error).__name__
            + "). Check TLS, credentials and read-only grants.",
            "code": "connection",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    origin = os.environ.get(
        "QOT_CONNECTOR_ORIGIN", "https://queryotter.vercel.app"
    ).rstrip("/")
    url = urlparse(origin)
    if (
        (url.scheme != "https" and url.hostname not in {"localhost", "127.0.0.1"})
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise SystemExit("Connector origin must be a canonical HTTPS URL.")
    cid, token = os.environ["QOT_CONNECTOR_ID"], os.environ["QOT_CONNECTOR_TOKEN"]
    profiles = json.loads(Path(args.profiles).read_text())
    if not isinstance(profiles, dict):
        raise SystemExit("Profiles must be an object keyed by profile name.")
    with httpx.Client(
        headers={"Authorization": "Bearer " + token}, timeout=10, follow_redirects=False
    ) as api:
        base = origin + "/api/assistant/connectors/" + cid
        print(
            "Connector ready. Credentials remain on this machine; only configured profiles are available."
        )
        while True:
            response = api.post(base + "/poll", json={})
            if response.status_code == 401:
                raise SystemExit("Connector token invalid or revoked.")
            response.raise_for_status()
            task = response.json().get("task")
            if task:
                done = api.post(
                    base + "/complete",
                    json={
                        "task_id": task["id"],
                        "response": process_task(task, profiles),
                    },
                )
                if done.status_code not in {200, 409}:
                    done.raise_for_status()
                print(
                    "Task completed or expired. No records, queries or credentials logged."
                )
            if args.once:
                return
            time.sleep(2)


if __name__ == "__main__":
    main()
