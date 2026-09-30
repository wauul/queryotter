"""Connection, discovery, syntax, bounded execution, plans and independent semantics."""

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from integration.fixtures import seed, DATA
from backend.adapters.registry import open_adapter
from backend.adapters.base import AdapterError
from backend.adapters.documents import Firestore


def relational_query(engine):
    top = "TOP (5) " if engine == "sqlserver" else ""
    limit = "" if engine == "sqlserver" else " LIMIT 5"
    return (
        f"SELECT {top}c.id,c.name,SUM(o.total) AS paid_total FROM customers c JOIN orders o ON c.id=o.customer_id WHERE o.status='paid' AND o.created_at>='2026-08-01' AND o.created_at<'2026-09-01' GROUP BY c.id,c.name ORDER BY paid_total DESC,c.id"
        + limit
    )


def verify(engine):
    os.environ["QOT_TEST_NETWORKS"] = "1"
    config = seed(engine)
    start = time.monotonic()
    tests = []
    with open_adapter(engine, config) as adapter:
        metadata = adapter.discover()
        assert {"customers", "orders"}.issubset({t["name"] for t in metadata["tables"]})
        tests.append("actual connection and schema/collection discovery")
        adapter.deadline = time.monotonic() + 20
        if adapter.dialect:
            query = relational_query(engine)
            adapter.validate(query, metadata)
            result = adapter.execute(query, metadata)
            totals = Counter()
            for id, cid, total, status, created in DATA["orders"]:
                if (
                    cid is not None
                    and total is not None
                    and status == "paid"
                    and "2026-08-01" <= created < "2026-09-01"
                ):
                    totals[cid] += total
            expected = [
                (cid, f"Customer {cid}", total)
                for cid, total in sorted(totals.items(), key=lambda p: (-p[1], p[0]))[
                    :5
                ]
            ]
            normalized = [(int(r[0]), r[1], float(r[2])) for r in result["rows"]]
            assert normalized == expected, (engine, normalized, expected)
            tests.append(
                "join, SUM, NULLs, date boundaries and deterministic ordering against independently computed expected rows"
            )
            duplicate_query = (
                "SELECT customer_id FROM orders WHERE customer_id IS NULL"
                + ("" if engine == "sqlserver" else " LIMIT 100")
            )
            assert len(adapter.execute(duplicate_query, metadata)["rows"]) == 1
            for unsafe in [
                "DELETE FROM orders",
                "SELECT load_file('/etc/passwd')",
                "SELECT imaginary FROM customers",
                "SELECT id FROM absent",
                "SELECT id FROM customers; SELECT id FROM orders",
            ]:
                try:
                    adapter.validate(unsafe, metadata)
                except AdapterError:
                    pass
                else:
                    raise AssertionError("unsafe or invented query accepted")
            tests.append(
                "writes, side-effect functions, missing tables/columns and multiple statements rejected"
            )
            bounded = adapter.execute(
                "SELECT a.id AS a,b.id AS b,c.id AS c FROM customers a CROSS JOIN customers b CROSS JOIN customers c",
                metadata,
            )
            assert len(bounded["rows"]) == 500 and bounded["truncated"]
            tests.append("512-row query bounded to 500 with explicit truncation")
        elif engine == "mongodb":
            query = {
                "collection": "orders",
                "operation": "find",
                "filter": {"status": "paid", "total": {"$gte": 200}},
                "projection": {"_id": 0, "id": 1, "total": 1},
                "sort": [["id", 1]],
                "limit": 100,
            }
            result = adapter.execute(query, metadata)
            expected = [
                id
                for id, cid, total, status, created in DATA["orders"]
                if status == "paid" and total is not None and total >= 200
            ]
            assert [d["id"] for d in result["documents"]] == expected
            aggregate = {
                "collection": "orders",
                "operation": "aggregate",
                "pipeline": [
                    {"$match": {"status": "paid"}},
                    {
                        "$group": {
                            "_id": "$customer_id",
                            "paid_total": {"$sum": "$total"},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ],
                "limit": 100,
            }
            rows = adapter.execute(aggregate, metadata)["documents"]
            assert any(r["_id"] is None and float(r["paid_total"]) == 12 for r in rows)
            tests.append(
                "native find and aggregation, missing fields/type variation, NULL aggregation against expected rows"
            )
            query = json.dumps(query)
        elif engine == "firestore":
            query = {
                "collection": "orders",
                "filters": [{"field": "total", "op": ">=", "value": 200}],
                "order_by": [{"field": "total", "direction": "asc"}],
                "limit": 100,
            }
            result = adapter.execute(query, metadata)
            expected = {
                id
                for id, cid, total, status, created in DATA["orders"]
                if total is not None and total >= 200
            }
            # Firestore cross-type order admits strings after numbers: schema variation matters.
            observed = {d["id"] for d in result["documents"]}
            assert expected.issubset(observed) and observed - expected <= {46}
            tests.append(
                "native structured filters/order/limit, missing fields and type-order caveat"
            )
            query = json.dumps(query)
        else:
            query = {
                "path": "orders",
                "order_by": "status",
                "equal_to": "paid",
                "limit": 100,
            }
            result = adapter.execute(query, metadata)
            assert {d["id"] for d in result["documents"]} == {
                id
                for id, cid, total, status, created in DATA["orders"]
                if status == "paid"
            }
            tests.append(
                "native order/equality/limit and actual missing fields against expected IDs"
            )
            query = json.dumps(query)
        if not adapter.dialect:
            invalid = {
                "mongodb": [
                    {
                        "collection": "orders",
                        "operation": "find",
                        "filter": {"$where": "evil()"},
                    },
                    {
                        "collection": "orders",
                        "operation": "aggregate",
                        "pipeline": [{"$out": "stolen"}],
                    },
                    {
                        "collection": "orders",
                        "operation": "find",
                        "projection": {"id": {"$gt": 1}},
                    },
                ],
                "firestore": [
                    {
                        "collection": "orders",
                        "filters": [{"field": "imaginary", "op": "==", "value": 1}],
                    },
                    {"collection": "orders", "limit": 501},
                    {"collection": "orders", "sql": "DELETE"},
                ],
                "firebase_realtime": [
                    {"path": "imaginary", "limit": 1},
                    {"path": "orders", "order_by": "imaginary"},
                    {"path": "orders", "limit": 501},
                ],
            }[engine]
            for item in invalid:
                try:
                    adapter.validate(json.dumps(item), metadata)
                except AdapterError:
                    pass
                else:
                    raise AssertionError("unsafe/unknown native query accepted")
            tests.append(
                "native writes/unknown fields/unsupported query shapes rejected"
            )
        adapter.deadline = time.monotonic() - 1
        try:
            adapter.checkpoint()
        except AdapterError as error:
            assert error.code == "timeout"
        else:
            raise AssertionError("expired deadline accepted")
        adapter.deadline = time.monotonic() + 20
        tests.append("expired deadline prevents further database work")
        from backend.investigate import Cancelled

        prior = adapter.check

        def cancel():
            raise Cancelled()

        adapter.check = cancel
        try:
            adapter.checkpoint()
        except Cancelled:
            pass
        else:
            raise AssertionError("cancellation checkpoint ignored")
        adapter.check = prior
        tests.append(
            "cooperative cancellation checkpoint verified; native in-flight interruption remains timeout-bound"
        )
        if adapter.capabilities.query_plans:
            plan = adapter.plan(query, metadata)
            assert not plan["executed"] and plan["plan"]
            tests.append("actual non-executing plan")
        else:
            try:
                adapter.plan(query, metadata)
            except AdapterError as error:
                assert error.code == "unsupported"
            else:
                raise AssertionError("unsupported plan pretended available")
            tests.append("unsupported plan explicitly reported")
        capabilities = adapter.capabilities.public()
        version = metadata["version"]
    if engine in {"postgresql", "mysql", "mariadb", "sqlserver", "mongodb"}:
        parsed = urlparse(config["url"])
        bad = {**config, "url": config["url"].replace(":" + parsed.password + "@", ":Qot_wrongTestCredentials@")}
        try:
            with open_adapter(engine, bad):
                raise AssertionError("invalid credentials accepted")
        except AdapterError as error:
            assert error.code == "credentials", (engine, error.code)
            assert "Qot_wrongTestCredentials" not in str(error)
        tests.append("actual invalid database password rejected with redacted, actionable credential error")
    if engine in {"postgresql", "mysql", "mariadb", "cockroachdb", "sqlserver"}:
        try:
            with open_adapter(engine, {**config, "force_tls": True, "ca_certificate": "-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----"}):
                raise AssertionError("invalid CA accepted")
        except AdapterError as error:
            assert error.code == "tls"
        tests.append("malformed TLS CA rejected; this does not verify the hosted provider certificate path")
    return {
        "status": "Verified against official local service/emulator",
        "version": version,
        "checked": time.strftime("%Y-%m-%d", time.gmtime()),
        "tests": tests,
        "generation": "Real Groq evaluation pending; deterministic fixture query validation/execution verified",
        "hosted_provider": "Requires user credentials",
        "capabilities": capabilities,
        "seconds": round(time.monotonic() - start, 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engines", nargs="*")
    parser.add_argument("--output", default="public/adapter-verification.json")
    args = parser.parse_args()
    output = Path(args.output)
    existing = json.loads(output.read_text()) if output.exists() else {}
    failed = False
    for engine in args.engines or [
        "sqlite",
        "postgresql",
        "mysql",
        "mariadb",
        "cockroachdb",
        "sqlserver",
        "mongodb",
        "firestore",
        "firebase_realtime",
    ]:
        try:
            existing[engine] = verify(engine)
            print(engine, "PASS", existing[engine]["version"])
        except Exception as error:
            failed = True
            existing[engine] = {
                "status": "Integration verification failed",
                "error_type": type(error).__name__,
                "generation": "unverified",
                "hosted_provider": "Requires user credentials",
            }
            print(engine, "FAIL", type(error).__name__)
            if os.environ.get("QOT_FIXTURE_DEBUG") == "1":
                import traceback

                traceback.print_exc()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(existing, indent=2, default=str) + "\n")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
