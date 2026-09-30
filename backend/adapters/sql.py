import json
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from backend.adapters.base import AdapterError


FUNCTIONS = {
    "AND",
    "OR",
    "CASE",
    "EXISTS",
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "COALESCE",
    "NULLIF",
    "IF",
    "IFNULL",
    "LOWER",
    "UPPER",
    "ABS",
    "ROUND",
    "CAST",
    "TRY_CAST",
    "EXTRACT",
    "DATE_TRUNC",
    "TIMESTAMP_TRUNC",
    "DATE",
    "DATETIME",
    "TIME",
    "TIMESTAMP",
    "STRFTIME",
    "DATE_FORMAT",
    "DATE_ADD",
    "DATE_SUB",
    "DATEDIFF",
    "DATE_DIFF",
    "TIMESTAMPDIFF",
    "TIMESTAMP_DIFF",
    "CURRENT_DATE",
    "CURRENT_TIMESTAMP",
    "CURRENT_TIME",
    "TRIM",
    "LTRIM",
    "RTRIM",
    "SUBSTRING",
    "LENGTH",
    "CHAR_LENGTH",
    "CONCAT",
    "CONCAT_WS",
    "ROW_NUMBER",
    "RANK",
    "DENSE_RANK",
    "LAG",
    "LEAD",
    "YEAR",
    "MONTH",
    "DAY",
    "DAYOFMONTH",
    "WEEK",
    "WEEKDAY",
    "TIME_TO_STR",
    "STR_TO_DATE",
    "TIME_STR_TO_DATE",
    "TIME_STR_TO_TIME",
    "TIME_STR_TO_UNIX",
    "TS_OR_DS_TO_DATE",
    "TS_OR_DS_ADD",
    "TS_OR_DS_DIFF",
    "DATE_FROM_PARTS",
    "TIME_TO_TIME_STR",
}
FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Into,
    exp.Lock,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
)


def validate_sql(query, dialect, metadata):
    if not isinstance(query, str) or not query.strip() or len(query) > 12000:
        raise AdapterError("Enter one SELECT query of at most 12,000 characters.")
    try:
        statements = [s for s in sqlglot.parse(query, read=dialect) if s is not None]
    except sqlglot.errors.SqlglotError:
        raise AdapterError(
            "The query could not be parsed in the selected database dialect.", "syntax"
        ) from None
    if len(statements) != 1 or not isinstance(
        statements[0], (exp.Select, exp.SetOperation)
    ):
        raise AdapterError(
            "Only one read-only SELECT is allowed; writes and commands are blocked.",
            "unsafe",
        )
    tree = statements[0]
    for node in tree.walk():
        if isinstance(node, FORBIDDEN) or isinstance(node, exp.Table) and node.catalog:
            raise AdapterError(
                "Writes, locks, commands and cross-database access are blocked.",
                "unsafe",
            )
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise AdapterError(
                "Recursive queries are outside the bounded workspace.", "unsupported"
            )
        if isinstance(node, exp.Func):
            if isinstance(node.parent, exp.Dot):
                raise AdapterError(
                    "Schema-qualified function calls are outside the built-in read-only allowlist.",
                    "unsafe",
                )
            name = (
                node.name.upper()
                if isinstance(node, exp.Anonymous)
                else node.sql_name().upper()
            )
            if name not in FUNCTIONS:
                raise AdapterError(
                    f"Function {name[:40]} is not in the read-only allowlist.", "unsafe"
                )
        if isinstance(node, exp.Placeholder) or isinstance(node, exp.Parameter):
            raise AdapterError(
                "Use literal values in the editor; the executor binds supported literal values automatically.",
                "parameters",
            )
    tables = metadata.get("tables", [])
    names = {t["name"] for t in tables}
    ctes = {c.alias for c in tree.find_all(exp.CTE)}
    allowed_schemas = {t.get("schema", "") for t in tables}
    for table in tree.find_all(exp.Table):
        if (
            table.name not in names | ctes
            or table.db
            and table.db not in allowed_schemas
        ):
            raise AdapterError(
                "The query references a table outside the discovered schema. Refresh the schema or correct the table name.",
                "schema_drift",
            )
    mapping = {t["name"]: {c["name"]: "UNKNOWN" for c in t["columns"]} for t in tables}
    try:
        qualify(
            tree.copy(),
            dialect=dialect,
            schema=mapping,
            qualify_columns=True,
            validate_qualify_columns=True,
            infer_schema=False,
        )
    except sqlglot.errors.SqlglotError:
        raise AdapterError(
            "A column or relationship could not be resolved from actual schema metadata.",
            "schema_drift",
        ) from None
    for node in tree.walk():
        node.comments = []
    return tree.sql(dialect=dialect), tree


def bind_literals(tree, dialect, style):
    bound = tree.copy()
    values = {}
    for literal in list(bound.find_all(exp.Literal)):
        if isinstance(
            literal.parent, (exp.Limit, exp.Offset, exp.Interval, exp.DataTypeParam)
        ):
            continue
        key = f"qot_p{len(values)}"
        value = (
            literal.this
            if literal.is_string
            else float(literal.this)
            if "." in literal.this
            else int(literal.this)
        )
        values[key] = value
        literal.replace(exp.Placeholder(this=key))
    query = bound.sql(dialect=dialect)
    if style != "sqlite":
        query = query.replace("%", "%%")
    for key in values:
        # SQLGlot emits dialect-specific named placeholders. Driver binding never
        # interpolates the values, and the only replacement text is an internal ID.
        native = exp.Placeholder(this=key).sql(dialect=dialect)
        if style != "sqlite":
            native = native.replace("%", "%%")
        query = query.replace(native, f":{key}" if style == "sqlite" else f"%({key})s")
    return query, values


def bounded_query(tree, limit=501):
    """Apply the row budget at the server, before a driver buffers the result."""
    bound = tree.copy()
    existing = bound.args.get("limit")
    if existing:
        options = existing.args.get("limit_options")
        if options and (options.args.get("percent") or options.args.get("with_ties")):
            raise AdapterError(
                "TOP PERCENT and WITH TIES cannot preserve their meaning under the workspace row cap. Use an explicit row count and ordering.",
                "unsupported",
            )
        count = existing.args.get("expression") or existing.args.get("count")
        if not isinstance(count, exp.Literal) or count.is_string or not count.this.isdigit():
            raise AdapterError("Use a literal non-negative row limit.", "syntax")
        limit = min(limit, int(count.this))
    return bound.limit(limit)


def bounded_result(columns, rows, elapsed_ms, limit=500):
    converted = []
    size = 2
    clipped = False
    for row in rows:
        if len(converted) == limit:
            clipped = True
            break
        values = [
            v if v is None or isinstance(v, (str, int, float, bool)) else str(v)
            for v in row
        ]
        size += len(json.dumps(values, default=str).encode()) + 2
        if size > 2_000_000:
            raise AdapterError(
                "Results exceed the 2 MB budget. Select fewer fields or rows.",
                "result_limit",
            )
        converted.append(values)
    return {
        "columns": columns,
        "rows": converted,
        "row_count": len(converted),
        "truncated": clipped,
        "elapsed_ms": round(elapsed_ms, 3),
        "limit": limit,
        "claims": {
            "syntactically_valid": True,
            "executable": True,
            "business_meaning_verified": False,
        },
        "pagination": "Pages use this bounded result snapshot; they do not re-run the query.",
    }
