CASES = [
 {"id":"customer-orders","title":"A customer's recent orders","category":"Missing index","sql":"SELECT id, customer_id, total, created_at FROM orders WHERE customer_id = 42 ORDER BY created_at DESC, id DESC LIMIT 50","baseline":["CREATE INDEX ON orders (customer_id, created_at DESC, id DESC)"]},
 {"id":"rare-status","title":"Find the rare refunds","category":"Selective filter","sql":"SELECT id, total FROM orders WHERE status = 'refunded' ORDER BY id LIMIT 100","baseline":["CREATE INDEX ON orders (status, id)"]},
 {"id":"common-status","title":"Most orders are completed","category":"Nonselective filter","sql":"SELECT status, count(*) AS n, sum(total) AS revenue FROM orders WHERE status = 'completed' GROUP BY status","baseline":["CREATE INDEX ON orders (status)"]},
 {"id":"sort-total","title":"Highest value purchases","category":"Expensive sorting","sql":"SELECT id, total FROM orders ORDER BY total DESC NULLS LAST, id DESC LIMIT 50","baseline":["CREATE INDEX ON orders (total DESC NULLS LAST, id DESC)"]},
 {"id":"join-city","title":"Orders from Paris","category":"Join","sql":"SELECT o.id, c.name, o.total FROM customers c JOIN orders o ON o.customer_id = c.id WHERE c.city = 'Paris' ORDER BY o.id LIMIT 100","baseline":["CREATE INDEX ON customers (city, id)","CREATE INDEX ON orders (customer_id, id)"]},
 {"id":"join-items","title":"A customer's line items","category":"Join cardinality","sql":"SELECT o.id, i.id AS item_id, i.quantity FROM orders o JOIN items i ON i.order_id = o.id WHERE o.customer_id = 42 ORDER BY o.id, i.id LIMIT 100","baseline":["CREATE INDEX ON orders (customer_id)","CREATE INDEX ON items (order_id, id)"]},
 {"id":"aggregate","title":"Revenue by customer","category":"Aggregation","sql":"SELECT customer_id, count(*) AS n, sum(total) AS revenue FROM orders WHERE customer_id < 20 GROUP BY customer_id ORDER BY customer_id","baseline":["CREATE INDEX ON orders (customer_id) INCLUDE (total)"]},
 {"id":"pagination","title":"Deep pagination","category":"Pagination","sql":"SELECT id, created_at FROM orders ORDER BY created_at DESC, id DESC LIMIT 50 OFFSET 50000","baseline":["CREATE INDEX ON orders (created_at DESC, id DESC)"]},
 {"id":"cte","title":"Recent orders, through a CTE","category":"CTE","sql":"WITH recent AS (SELECT id, customer_id, total FROM orders WHERE customer_id = 42) SELECT id, total FROM recent ORDER BY id LIMIT 50","baseline":["CREATE INDEX ON orders (customer_id, id)"]},
 {"id":"already-fast","title":"An indexed primary key lookup","category":"Already optimized","sql":"SELECT id, total FROM orders WHERE id = 42","baseline":[]},
 {"id":"null-trap","title":"NULLs and an anti-join","category":"Semantic trap","sql":"SELECT id FROM customers WHERE id NOT IN (SELECT customer_id FROM orders) ORDER BY id LIMIT 100","baseline":["CREATE INDEX ON orders (customer_id)"]},
 {"id":"duplicates","title":"Keep every repeated purchase","category":"Duplicate semantics","sql":"SELECT customer_id, total FROM orders WHERE customer_id = 42","baseline":["CREATE INDEX ON orders (customer_id)"]},
 {"id":"unsafe","title":"A write hidden inside a CTE","category":"Unsafe · rejected","sql":"WITH removed AS (DELETE FROM orders RETURNING id) SELECT id FROM removed","baseline":[]},
 {"id":"volatile","title":"Random ordering cannot be verified","category":"Volatile · rejected","sql":"SELECT id FROM orders ORDER BY random() LIMIT 10","baseline":[]},
 {"id":"ambiguous","title":"Pagination needs a tie-breaker","category":"Ambiguous · rejected","sql":"SELECT id FROM orders ORDER BY status LIMIT 50","baseline":[]}
]
import sqlglot
for case in CASES:
    case['sql']=sqlglot.parse_one(case['sql'],read='postgres').sql(dialect='postgres',pretty=True)
BY_ID = {c['id']:c for c in CASES}
