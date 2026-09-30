"""SQLite benchmark in a disposable second copy, with typed result comparison."""

import base64
import collections
import hashlib
import json
import random
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path
import sqlglot
from sqlglot import exp
from backend.adapters.base import AdapterError
from backend.adapters.sql import validate_sql, bind_literals


def canonical(rows, ordered):
    def key(row):
        return json.dumps(
            [(type(v).__name__, v.hex() if isinstance(v, bytes) else v) for v in row],
            separators=(",", ":"),
            default=str,
        )

    entries = [key(r) for r in rows]
    return entries if ordered else collections.Counter(entries)


def measure(config, original, candidate, indexes, metadata, check=lambda: None):
    if len(indexes) > 2 or any(
        not isinstance(i, str) or len(i) > 1500 for i in indexes
    ):
        raise AdapterError(
            "Use at most two index statements of 1,500 characters each.", "unsafe"
        )
    sql, tree = validate_sql(original, "sqlite", metadata)
    replacement, other = validate_sql(candidate, "sqlite", metadata)
    if bool(tree.args.get("order")) != bool(other.args.get("order")):
        raise AdapterError(
            "The candidate changes the ordering requirement.", "semantics"
        )
    ordered = bool(tree.args.get("order"))
    statements = [bind_literals(t, "sqlite", "sqlite") for t in [tree, other]]
    with tempfile.TemporaryDirectory(prefix="qot_benchmark_") as directory:
        file = Path(directory) / "copy.db"
        file.write_bytes(base64.b64decode(config["data"], validate=True))
        c = sqlite3.connect(file)
        work = {"statements": 0}
        c.set_trace_callback(lambda _: work.update(statements=work["statements"] + 1))
        try:
            c.enable_load_extension(False)
            c.execute("PRAGMA trusted_schema=OFF")
            c.execute("PRAGMA temp_store=MEMORY")
            c.execute("PRAGMA cache_size=-2048")
            c.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2_000_000)
            deadline = time.monotonic() + 30

            def progress():
                check()
                return int(time.monotonic() > deadline)

            c.set_progress_handler(progress, 1000)
            before = (
                c.execute("PRAGMA page_count").fetchone()[0]
                * c.execute("PRAGMA page_size").fetchone()[0]
            )
            base_plan = c.execute(
                "EXPLAIN QUERY PLAN " + statements[0][0], statements[0][1]
            ).fetchall()
            baseline_cursor = c.execute(*statements[0])
            baseline_columns = [d[0] for d in baseline_cursor.description]
            baseline = baseline_cursor.fetchmany(501)
            if len(baseline) > 500:
                raise AdapterError(
                    "Correctness comparison requires the full result to fit the 500-row snapshot. Add an appropriate bound or use a controlled fixture.",
                    "semantics",
                )

            def run(i):
                check()
                start = time.perf_counter()
                cursor = c.execute(*statements[i])
                rows = cursor.fetchmany(501)
                columns = [d[0] for d in cursor.description]
                if i == 1 and columns != baseline_columns:
                    raise AdapterError(
                        "The candidate changes output column names/order. Preserve the result interface before benchmarking.",
                        "semantics",
                    )
                if len(rows) > 500:
                    raise AdapterError(
                        "Candidate result exceeds the full correctness scope.",
                        "semantics",
                    )
                return rows, (time.perf_counter() - start) * 1000

            # Baseline timing is taken before experimental indexes exist.
            run(0)
            original_times = [run(0)[1] for _ in range(7)]
            applied = []
            for index in indexes[:2]:
                try:
                    parsed = sqlglot.parse_one(index, read="sqlite")
                except sqlglot.errors.SqlglotError:
                    raise AdapterError(
                        "An experimental index could not be parsed.", "unsafe"
                    ) from None
                table = next(parsed.find_all(exp.Table), None)
                if (
                    not isinstance(parsed, exp.Create)
                    or str(parsed.args.get("kind", "")).upper() != "INDEX"
                    or parsed.args.get("unique")
                    or table is None
                    or table.name not in {t["name"] for t in metadata["tables"]}
                ):
                    raise AdapterError(
                        "Only non-unique plain-column indexes on discovered tables are supported in the disposable copy.",
                        "unsafe",
                    )
                known = {
                    f["name"]
                    for t in metadata["tables"]
                    if t["name"] == table.name
                    for f in t["columns"]
                }
                for column in parsed.find_all(exp.Column):
                    if column.name not in known:
                        raise AdapterError(
                            "Index references an undiscovered field.", "schema_drift"
                        )
                for node in parsed.walk():
                    if isinstance(node, (exp.Func, exp.Select, exp.Where, exp.Literal)):
                        raise AdapterError(
                            "Expression, partial and functional indexes are outside this benchmark.",
                            "unsupported",
                        )
                generated = parsed.sql(dialect="sqlite")
                c.execute(generated)
                applied.append(generated)
            # The second copy is read-only again before model-generated queries run.
            c.execute("PRAGMA query_only=ON")
            from backend.adapters.relational import SQLite

            c.set_authorizer(SQLite._authorize)
            changed, _ = run(1)
            equal = canonical(baseline, ordered) == canonical(changed, ordered)
            candidate_times = []
            if equal:
                run(1)
                candidate_times = [run(1)[1] for _ in range(7)]
            c.set_authorizer(None)
            after = (
                c.execute("PRAGMA page_count").fetchone()[0]
                * c.execute("PRAGMA page_size").fetchone()[0]
            )
            candidate_plan = c.execute(
                "EXPLAIN QUERY PLAN " + statements[1][0], statements[1][1]
            ).fetchall()

            def summary(samples):
                if not samples:
                    return None
                median = statistics.median(samples)
                return {
                    "samples_ms": samples,
                    "median_ms": median,
                    "mad_ms": statistics.median(abs(s - median) for s in samples),
                }

            a, b = summary(original_times), summary(candidate_times)
            improvement = bool(
                equal
                and b
                and a["median_ms"] > b["median_ms"] * 1.1
                and a["median_ms"] - b["median_ms"] > 2 * (a["mad_ms"] + b["mad_ms"])
            )
            return {
                "measured": True,
                "database_calls": work["statements"],
                "correct": equal,
                "improvement_observed": improvement,
                "scope": {
                    "database": "disposable uploaded copy",
                    "rows": len(baseline),
                    "comparison": "ordered typed rows"
                    if ordered
                    else "typed multiset including duplicates and NULLs",
                    "other_datasets_verified": False,
                },
                "baseline": a,
                "candidate": b,
                "speedup": a["median_ms"] / b["median_ms"]
                if b and b["median_ms"]
                else None,
                "plans": {"baseline": base_plan, "candidate": candidate_plan},
                "experimental_indexes": applied,
                "index_tradeoffs": {
                    "observed_allocated_bytes": max(0, after - before),
                    "writes": "Additional indexes can slow writes and consume storage; this copy does not measure write latency.",
                },
                "methodology": "One warm-up, seven sequential warm samples before and after candidate indexes; median and MAD. Client wall time includes fetching the full bounded result. Cache/order effects can remain; a win requires >10% and a difference above twice combined MAD.",
            }
        finally:
            c.close()
