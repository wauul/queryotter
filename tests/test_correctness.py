import pytest
from backend.db import sandbox
from backend.investigate import equivalent, summary, decide


def test_null_anti_join_trap_independent_oracle():
    with sandbox(300, 17, True) as (c, _):
        original = "SELECT id FROM customers WHERE id NOT IN (SELECT customer_id FROM orders) ORDER BY id"
        wrong = "SELECT id FROM customers WHERE NOT EXISTS (SELECT 1 FROM orders WHERE orders.customer_id=customers.id) ORDER BY id"
        assert (
            c.execute(original).fetchall() == []
        )  # NULL in NOT IN makes all nonmatching comparisons UNKNOWN.
        assert c.execute(wrong).fetchall() != []
        assert not equivalent(c, original, wrong)


def test_duplicate_trap_independent_oracle():
    with sandbox(300, 17, True) as (c, _):
        q = "SELECT customer_id,total FROM orders WHERE id IN (-2,-3)"
        assert c.execute(q).fetchall() == [(1, 0), (1, 0)]
        assert not equivalent(
            c, q, "SELECT DISTINCT customer_id,total FROM orders WHERE id IN (-2,-3)"
        )


def test_order_and_types():
    with sandbox(300, 31, True) as (c, _):
        assert not equivalent(
            c,
            "SELECT id FROM orders ORDER BY id",
            "SELECT id FROM orders ORDER BY id DESC",
        )
        assert not equivalent(
            c,
            "SELECT id FROM orders WHERE id=1",
            "SELECT CAST(id AS text) FROM orders WHERE id=1",
        )


def test_empty_data_equal_is_not_proof():
    with sandbox(0) as (c, _):
        assert equivalent(
            c, "SELECT id FROM orders", "SELECT id FROM orders WHERE id<0"
        )


def test_noisy_and_tiny_measurement_not_win():
    assert (
        decide(summary([4, 5, 6, 4, 5, 6, 5]), summary([3, 4, 5, 4, 5, 4, 5]))
        == "inconclusive"
    )
    assert decide(summary([0.03] * 7), summary([0.02] * 7)) == "inconclusive"
    assert decide(summary([5] * 7), summary([1] * 7)) == "verified improvement"
