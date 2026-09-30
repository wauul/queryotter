"""Actual server timeouts on disposable loopback fixtures, never production."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from integration.fixtures import seed
from backend.adapters.registry import open_adapter
from backend.adapters.base import AdapterError


def verify(engine):
    os.environ["QOT_TEST_NETWORKS"] = "1"
    config = seed(engine)
    started = time.monotonic()
    try:
        with open_adapter(engine, config) as adapter:
            metadata = adapter.discover()
            # The aggregate must finish the Cartesian product before returning one row.
            # A LIMIT therefore cannot make this deliberately expensive fixture cheap.
            query = "SELECT SUM(" + " + ".join(x + ".total" for x in "abcdefgh") + ") AS work FROM " + " CROSS JOIN ".join("orders " + x for x in "abcdefgh")
            adapter.deadline = time.monotonic() + 4
            adapter.execute(query, metadata)
        raise AssertionError("expensive fixture unexpectedly completed")
    except AdapterError as error:
        assert error.code == "timeout", (engine, error.code)
    seconds = time.monotonic() - started
    assert seconds < 10, (engine, seconds)
    return {"actual_in_flight_timeout": True, "seconds_including_discovery": round(seconds, 3), "scope": "8-way synthetic orders Cartesian aggregate on a local service/copy"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engines", nargs="*", default=[])
    parser.add_argument("--output", default="public/execution-boundaries.json")
    args = parser.parse_args()
    evidence = {}
    failed = False
    for engine in args.engines or ["sqlite", "postgresql", "mysql", "mariadb", "cockroachdb", "sqlserver"]:
        try:
            evidence[engine] = verify(engine)
            print(engine, "TIMEOUT PASS", evidence[engine]["seconds_including_discovery"])
        except Exception as error:
            failed = True
            evidence[engine] = {"actual_in_flight_timeout": False, "error_type": type(error).__name__}
            print(engine, "FAIL", type(error).__name__)
            if os.environ.get("QOT_FIXTURE_DEBUG") == "1":
                import traceback
                traceback.print_exc()
    Path(args.output).write_text(json.dumps(evidence, indent=2) + "\n")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
