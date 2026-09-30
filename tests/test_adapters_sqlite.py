import pytest
from datetime import datetime, timezone
from backend.demo import sqlite_demo
from backend.adapters.base import AdapterError
from backend.adapters.relational import SQLite
from backend.adapters.sql import validate_sql, bind_literals, bounded_query, bounded_result


@pytest.fixture
def adapter():
    with SQLite(sqlite_demo(datetime(2026, 9, 30, tzinfo=timezone.utc))) as a:
        yield a


def test_discover_validate_plan_execute_and_snapshot(adapter):
    metadata = adapter.discover()
    assert {t["name"] for t in metadata["tables"]} == {"customers", "orders"}
    assert metadata["relationships"] == [["orders", "customer_id", "customers", "id"]]
    query = "SELECT c.id,c.name,SUM(o.total) AS total_paid FROM customers c JOIN orders o ON o.customer_id=c.id WHERE o.status='paid' AND o.created_at>='2026-08-01T00:00:00+00:00' AND o.created_at<'2026-09-01T00:00:00+00:00' GROUP BY c.id,c.name ORDER BY total_paid DESC,c.id LIMIT 5"
    valid = adapter.validate(query, metadata)
    plan = adapter.plan(valid, metadata)
    assert plan["executed"] is False and plan["plan"]
    result = adapter.execute(valid, metadata)
    # Independently calculated from fixture rules, including NULL and date edges.
    assert result["rows"] == [
        [6, "Customer 6", 700],
        [8, "Customer 8", 700],
        [1, "Customer 1", 560],
        [3, "Customer 3", 560],
        [5, "Customer 5", 560],
    ]
    assert result["claims"]["business_meaning_verified"] is False
    assert not result["truncated"]


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM orders",
        "SELECT load_extension('evil')",
        "SELECT * FROM missing",
        "SELECT invented FROM orders",
        "SELECT * FROM orders; DROP TABLE orders",
        "ATTACH DATABASE '/etc/passwd' AS p",
        "SELECT random() FROM orders",
        "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x",
    ],
)
def test_reject_unsafe_unknown_and_schema_drift(adapter, query):
    with pytest.raises(AdapterError):
        adapter.validate(query, adapter.discover())


def test_literal_binding_and_duplicate_null_results(adapter):
    metadata = adapter.discover()
    _, tree = validate_sql(
        "SELECT customer_id,total FROM orders WHERE status='paid' AND id%2=1 ORDER BY id",
        "sqlite",
        metadata,
    )
    statement, values = bind_literals(tree, "sqlite", "sqlite")
    assert "paid" not in statement and "paid" in values.values()
    result = adapter.execute(tree.sql(dialect="sqlite"), metadata)
    assert any(row[0] is None for row in result["rows"])
    assert any(row[1] is None for row in result["rows"])
    with pytest.raises(sqlite3.DatabaseError):
        adapter.connection.execute("CREATE TABLE malicious(x)")


import sqlite3


def test_server_row_budget_and_incremental_byte_limit(adapter):
    metadata = adapter.discover()
    seen = []
    adapter.connection.set_trace_callback(seen.append)
    result = adapter.execute("SELECT a.id FROM customers a CROSS JOIN customers b CROSS JOIN customers c ORDER BY a.id", metadata)
    assert result["row_count"] == 500 and result["truncated"]
    assert "LIMIT 501" in seen[-1]
    assert len(adapter.execute("SELECT id FROM customers LIMIT 2 OFFSET 1", metadata)["rows"]) == 2
    consumed = []
    def huge():
        for i in range(500):
            consumed.append(i)
            yield ["x" * 1_100_000]
    with pytest.raises(AdapterError, match="2 MB"):
        bounded_result(["x"], huge(), 0)
    assert len(consumed) == 2
    import sqlglot
    for syntax in ["SELECT TOP 10 PERCENT id FROM orders", "SELECT TOP 10 WITH TIES id FROM orders ORDER BY id"]:
        with pytest.raises(AdapterError, match="preserve"):
            bounded_query(sqlglot.parse_one(syntax, read="tsql"))
