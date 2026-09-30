# Adapter architecture

The registry selects an engine, not a hosting provider. PostgreSQL, MySQL, MariaDB, SQLite, SQL Server, CockroachDB, MongoDB, Firestore Standard Core and Firebase Realtime Database each implement connection testing, discovery, validation and bounded read-only execution. Their capabilities explicitly describe plans, profiling, candidates, controlled benchmarking, cancellation and timeouts. Provider presets only supply connection guidance.

## Operation boundaries

`backend/adapters/base.py` owns deadlines, cancellation checkpoints, certificate handling and limits. `registry.py` selects adapters and closes partially constructed drivers on failure. `network.py` rejects private/cloud metadata routes and rechecks DNS. `sql.py` validates a single native SELECT, binds literal values and applies a server-side 501-row sentinel before incremental buffering. `relational.py`, `documents.py` and `libsql.py` own native permissions, metadata and execution. Error classification returns actionable messages without raw driver bodies or credentials.

The durable worker resolves a workspace-authorized connection and rechecks its configuration revision after work. Schema caches live for five minutes; explicit refresh and secret rotation invalidate them. Prisma models are optional context reconciled against discovery. They cannot invent a missing table or authorize execution.

Generation sends at most eight relevant tables/collections and 60 columns per table, within a 36,000-character context limit. It includes actual engine/version, relationships, indexes and explicit date boundaries. A draft may require clarification. At most one validation repair follows the initial model call. Generation never calls execution. Native Run is a separate authorized job.

## Native representations

These examples require the corresponding discovered synthetic schema; they are not universal templates.

| Engine | Representation and distinction |
|---|---|
| PostgreSQL / CockroachDB | PostgreSQL dialect SELECT; Cockroach uses its distributed plan and permissions. Timestamp types and transaction features differ. |
| MySQL / MariaDB | MySQL dialect SELECT; UTC session, verified TLS and native read-only transaction/statement timeout. MariaDB has its own timeout and grants handling. |
| SQL Server | T-SQL SELECT with TOP/FETCH rather than LIMIT; SELECT-only login, optional SHOWPLAN. TOP PERCENT and WITH TIES are rejected because a result cap could change their meaning. |
| SQLite | SQLite SELECT against an immutable uploaded copy. Extension loading, virtual tables and side-effecting functions are blocked. |
| MongoDB | JSON find or aggregation pipeline, not executable JavaScript. Supported stages/operators form an allowlist; `$out`, `$merge` and JavaScript are rejected. |
| Firestore | Standard Core structured query: collection, filters, ordering and limit. No SQL joins or arbitrary aggregation. Composite indexes may be required; the product reports that dependency. |
| Realtime Database | Path, one order key, equality/range and limit. Native filtering cannot answer general joins or SUM queries. `.indexOn` must be configured by the database owner where needed. |

MongoDB example:

```json
{"collection":"orders","filter":{"status":"paid"},"sort":{"total":-1,"id":1},"limit":5}
```

Firestore example:

```json
{"collection":"orders","filters":[{"field":"status","op":"==","value":"paid"}],"order_by":[{"field":"total","direction":"desc"}],"limit":5}
```

Realtime example:

```json
{"path":"orders","order_by":"status","equal_to":"paid","limit":5,"last":false}
```

Document discovery is inferred and incomplete. Optional inference reads at most 20 documents per collection inside the adapter; only field names/types go to the model. Missing fields, NULLs, arrays and varying types remain distinct. Unknown fields are rejected until refreshed discovery finds them. JSON results preserve native document shape; tabular rendering cannot fully express every missing/type distinction.

## Execution controls and evidence

All adapters expose bounded read execution; cloud SQL credentials must have no write grants. SQL parser validation complements permissions and transaction/driver controls. SELECT-only does not imply harmless arbitrary functions, so the SQL function allowlist rejects UDFs and side-effect constructs. Discovery excludes views. Results stop at 500 rows and 2 MB, expire after 15 minutes and paginate from one encrypted snapshot. Uploaded SQLite files are limited to 2 MiB, 30 tables and 500 columns.

Relational native statements use a three-second execution bound where supported and an eight-second operation deadline. Firebase/libSQL have bounded HTTP requests and response bytes. Cancellation is cooperative: a current driver request can finish at its native timeout; cancelled connector requests reject late responses. [Actual in-flight fixtures](../public/execution-boundaries.json) cover the six relational engines. Document tests verify cancellation/deadline checkpoints, not immediate native interruption.

A plan is evidence about access paths, not a measured improvement. Run latency is observed client time. Candidates are unmeasured until a controlled benchmark checks full result semantics. SQLite benchmarks use a second disposable copy. The preserved PostgreSQL portfolio uses independent seeded experiments, never changes a connected production database. Other engines explicitly report controlled benchmarking as unsupported.

See the [support matrix](support-matrix.md), [evaluation](evaluation.md), [provider guides](provider-guides.md) and [local connector](local-connector.md).
