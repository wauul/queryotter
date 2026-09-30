"""libSQL/Turso SQL-over-HTTP transport with per-request query_only enforcement."""

import base64
import json
import time
from urllib.parse import urlparse
import httpx
from backend.adapters.base import Adapter, AdapterError, Capabilities
from backend.adapters.network import validate_host
from backend.adapters.sql import validate_sql, bind_literals, bounded_result


class LibSQL(Adapter):
    engine = "sqlite"
    dialect = "sqlite"
    capabilities = Capabilities(
        query_plans=True,
        profiling=True,
        controlled_benchmarking=False,
        cancellation=False,
    )
    limitations = [
        "Remote libSQL uses SQLite SQL through the documented SQL-over-HTTP pipeline. Use a read-only database token, never an organization API token.",
        "Every request sets connection query_only before executing. Experimental indexes are unavailable for remote databases.",
        "HTTP timeouts bound the client wait; this transport cannot prove server cancellation after disconnect. Plan recommendations remain unmeasured until Run.",
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        u = urlparse(config.get("url", ""))
        if (
            u.scheme not in {"libsql", "turso", "https"}
            or not u.hostname
            or u.username
            or u.password
            or u.query
            or u.fragment
            or u.path not in {"", "/"}
        ):
            raise AdapterError(
                "Use the database libsql://, turso:// or HTTPS base URL and a separate read-only database token.",
                "connection_format",
            )
        validate_host(u.hostname, u.port or 443)
        self.base = "https://" + u.netloc + "/v2/pipeline"
        if not config.get("auth_token") or len(config["auth_token"]) > 8000:
            raise AdapterError(
                "Provide a read-only database authentication token.", "credentials"
            )

    @staticmethod
    def value(value):
        kind = value["type"]
        if kind == "null":
            return None
        if kind == "integer":
            return int(value["value"])
        if kind == "float":
            return float(value["value"])
        if kind == "blob":
            return base64.b64decode(value["base64"]).hex()
        return value["value"]

    def request(self, statement, parameters=None):
        def literal(v):
            return (
                {"type": "null"}
                if v is None
                else {
                    "type": "integer"
                    if isinstance(v, int)
                    else "float"
                    if isinstance(v, float)
                    else "text",
                    "value": str(v),
                }
            )

        self.checkpoint()
        self.database_calls += 2
        statements = ["PRAGMA query_only=ON", statement]
        requests = [
            {
                "type": "execute",
                "stmt": {
                    "sql": s,
                    "named_args": [
                        {"name": k, "value": literal(v)}
                        for k, v in (parameters or {}).items()
                    ]
                    if i == 1
                    else [],
                },
            }
            for i, s in enumerate(statements)
        ]
        requests.append({"type": "close"})
        with httpx.Client(
            timeout=5, follow_redirects=False, verify=self.ca_file()
        ) as client:
            with client.stream(
                "POST",
                self.base,
                headers={"Authorization": "Bearer " + self.config["auth_token"]},
                json={"requests": requests},
            ) as r:
                if r.status_code != 200:
                    raise AdapterError(
                        f"libSQL returned HTTP {r.status_code}. Check the database token, TLS and URL.",
                        "connection",
                    )
                body = bytearray()
                for chunk in r.iter_bytes():
                    self.checkpoint()
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise AdapterError(
                            "libSQL result exceeds 2 MB. Select fewer rows or fields.",
                            "result_limit",
                        )
                response = json.loads(body)
        results = response.get("results", [])
        if len(results) < 2 or any(result.get("type") != "ok" for result in results):
            raise AdapterError(
                "libSQL query or read-only enforcement failed. Check native syntax and database token permissions.",
                "database",
            )
        data = results[1]["response"]["result"]
        return (
            [column["name"] for column in data["cols"]],
            [[self.value(v) for v in row] for row in data["rows"][:501]],
            data,
        )

    def discover(self):
        _, tables, _ = self.request(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 31"
        )
        if len(tables) > 30:
            raise AdapterError(
                "Choose a database with at most 30 tables.", "schema_limit"
            )
        metadata = []
        relationships = []
        for row in tables:
            name = row[0]
            quoted = '"' + name.replace('"', '""') + '"'
            _, columns, _ = self.request("PRAGMA table_info(" + quoted + ")")
            metadata.append(
                {
                    "name": name,
                    "schema": "",
                    "columns": [
                        {
                            "name": c[1],
                            "type": c[2] or "TEXT",
                            "nullable": not bool(c[3]),
                            "primary_key": bool(c[5]),
                        }
                        for c in columns
                    ],
                }
            )
            _, foreign, _ = self.request("PRAGMA foreign_key_list(" + quoted + ")")
            relationships.extend([[name, r[3], r[2], r[4]] for r in foreign])
        _, indexes, _ = self.request(
            "SELECT tbl_name,sql FROM sqlite_schema WHERE type='index' AND sql IS NOT NULL LIMIT 100"
        )
        _, version, _ = self.request("SELECT sqlite_version()")
        return {
            "engine": "sqlite",
            "transport": "libSQL SQL over HTTP",
            "version": version[0][0],
            "tables": metadata,
            "indexes": indexes,
            "relationships": relationships,
            "complete": True,
            "sample_records_sent_to_model": False,
            "limitations": self.limitations,
        }

    def validate(self, query, schema):
        return validate_sql(query, "sqlite", schema)[0]

    def execute(self, query, schema):
        _, tree = validate_sql(query, "sqlite", schema)
        # A bounded outer SELECT keeps server response size under the row limit.
        sql, params = bind_literals(tree, "sqlite", "sqlite")
        start = time.perf_counter()
        columns, rows, data = self.request(
            "SELECT * FROM (" + sql + ") AS qot_bounded LIMIT 501", params
        )
        result = bounded_result(columns, rows, (time.perf_counter() - start) * 1000)
        result["database_work"] = {
            k: data.get(k) for k in ["rows_read", "rows_written"] if k in data
        }
        return result

    def plan(self, query, schema):
        _, tree = validate_sql(query, "sqlite", schema)
        sql, params = bind_literals(tree, "sqlite", "sqlite")
        _, rows, _ = self.request("EXPLAIN QUERY PLAN " + sql, params)
        return {"kind": "libSQL EXPLAIN QUERY PLAN", "executed": False, "plan": rows}
