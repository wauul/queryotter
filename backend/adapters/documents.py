"""Bounded native MongoDB, Firestore Standard Core and Realtime Database reads."""

import json
import os
import re
import time
from itertools import islice
from datetime import datetime
from urllib.parse import urlparse, quote
import httpx
from backend.adapters.base import Adapter, AdapterError, Capabilities
from backend.adapters.network import validate_host, private_plaintext
from backend.adapters.sql import bounded_result


def native(query):
    try:
        value = json.loads(query) if isinstance(query, str) else query
    except (ValueError, TypeError):
        raise AdapterError("Use a JSON native query object.", "syntax") from None
    if not isinstance(value, dict) or len(json.dumps(value, default=str)) > 12000:
        raise AdapterError("Use a bounded JSON query object.", "syntax")
    return value


def mongo_values(value):
    if isinstance(value, dict):
        if set(value) == {"$date"}:
            try:
                parsed = datetime.fromisoformat(value["$date"].replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("timezone")
                return parsed
            except (ValueError, AttributeError):
                raise AdapterError(
                    "MongoDB date literals require an ISO timestamp with a time zone.",
                    "syntax",
                ) from None
        return {k: mongo_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mongo_values(v) for v in value]
    return value


def field_types(records):
    fields = {}
    for record in records:

        def inspect(value, prefix="", depth=0):
            if depth > 3 or not isinstance(value, dict):
                return
            for key, item in list(value.items())[:100]:
                path = prefix + str(key)
                kind = (
                    "null"
                    if item is None
                    else "boolean"
                    if isinstance(item, bool)
                    else "number"
                    if isinstance(item, (int, float))
                    else "array"
                    if isinstance(item, list)
                    else "object"
                    if isinstance(item, dict)
                    else "timestamp"
                    if hasattr(item, "isoformat")
                    else "string"
                )
                entry = fields.setdefault(
                    path, {"name": path, "types": set(), "seen": 0}
                )
                entry["types"].add(kind)
                entry["seen"] += 1
                if isinstance(item, dict):
                    inspect(item, path + ".", depth + 1)

        inspect(record)
    return [
        {
            "name": k,
            "type": " | ".join(sorted(v["types"])),
            "nullable": "null" in v["types"],
            "may_be_missing": v["seen"] < len(records),
        }
        for k, v in sorted(fields.items())
    ][:100]


def bounded_documents(documents):
    bounded = []
    size = 2
    for document in islice(documents, 501):
        size += len(json.dumps(document, default=str).encode()) + 2
        if size > 2_000_000:
            raise AdapterError(
                "Document results exceed the 2 MB budget. Select fewer fields or documents.",
                "result_limit",
            )
        bounded.append(document)
    return bounded


def document_result(documents, elapsed):
    documents = bounded_documents(documents)
    names = sorted({str(k) for d in documents[:500] for k in d})[:100]
    rows = [[d.get(k) for k in names] for d in documents]
    result = bounded_result(names, rows, elapsed)
    result["document_note"] = (
        "Missing fields are shown as empty cells; raw documents preserve missing-field distinctions in JSON export."
    )
    result["documents"] = json.loads(json.dumps(documents[:500], default=str))
    if len(json.dumps(result).encode()) > 2_000_000:
        raise AdapterError(
            "Document results exceed the 2 MB budget. Select fewer fields or documents.",
            "result_limit",
        )
    return result


class MongoDB(Adapter):
    engine = "mongodb"
    capabilities = Capabilities(query_plans=True, profiling=True)
    limitations = [
        "Schemas may be inferred from up to 20 documents only when enabled; missing fields and type variation remain uncertain.",
        "Only bounded find and a read-only aggregation allowlist are supported. No JavaScript, writes, admin commands or production indexes.",
        "Plans use queryPlanner verbosity; client latency is measured only when Run is selected. No automatic production profiling.",
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        from pymongo import MongoClient
        from pymongo.monitoring import CommandListener

        owner = self

        class WorkCounter(CommandListener):
            def started(self, event):
                owner.database_calls += 1

            def succeeded(self, event):
                pass

            def failed(self, event):
                pass

        from pymongo.uri_parser import parse_uri

        url = config.get("url", "")
        if not url.startswith(("mongodb://", "mongodb+srv://")):
            raise AdapterError(
                "Use a MongoDB or Atlas connection URL.", "connection_format"
            )
        parsed = parse_uri(url)
        if set(parsed.get("options", {})) - {
            "authSource",
            "authsource",
            "authMechanism",
            "authmechanism",
            "replicaSet",
            "replicaset",
            "retryWrites",
            "retrywrites",
            "retryReads",
            "retryreads",
            "appName",
            "appname",
            "tls",
            "ssl",
        }:
            raise AdapterError(
                "Unsupported MongoDB URL options. Use database credentials, authSource and replicaSet; file paths, proxies and external authentication plugins are not accepted.",
                "connection_format",
            )
        if str(
            parsed.get("options", {}).get(
                "authMechanism",
                parsed.get("options", {}).get("authmechanism", "SCRAM-SHA-256"),
            )
        ) not in {"SCRAM-SHA-256", "SCRAM-SHA-1"}:
            raise AdapterError(
                "This adapter supports dedicated SCRAM database logins.", "credentials"
            )
        if not parsed["database"]:
            raise AdapterError(
                "Include a database name in the URL.", "connection_format"
            )
        for host, port in parsed["nodelist"]:
            validate_host(host, port)
        local = os.environ.get("QOT_TEST_NETWORKS") == "1" and all(
            h in {"localhost", "127.0.0.1"} for h, p in parsed["nodelist"]
        )
        local = local or all(private_plaintext(h, config) for h, p in parsed["nodelist"])
        tls = (
            {"tls": False}
            if local
            else {
                "tls": True,
                "tlsAllowInvalidCertificates": False,
                "tlsAllowInvalidHostnames": False,
                "tlsCAFile": self.ca_file(),
            }
        )
        self.client = MongoClient(
            url,
            **tls,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
            maxPoolSize=1,
            event_listeners=[WorkCounter()],
        )
        self.connection = self.client[parsed["database"]]
        status = self.connection.command(
            {"connectionStatus": 1, "showPrivileges": True}
        )
        privileges = status.get("authInfo", {}).get("authenticatedUserPrivileges", [])
        if not privileges and os.environ.get("QOT_TEST_NETWORKS") != "1":
            self.close()
            raise AdapterError(
                "Use authenticated read-only MongoDB credentials.", "permissions"
            )
        allowed = {
            "find",
            "listCollections",
            "listIndexes",
            "killCursors",
            "changeStream",
            "collStats",
            "dbStats",
            "listSearchIndexes",
            "planCacheRead",
            "dbHash",
        }
        for privilege in privileges:
            if not set(privilege.get("actions", [])).issubset(allowed):
                self.close()
                raise AdapterError(
                    "This MongoDB role has write or administration actions. Use the read role on one database.",
                    "permissions",
                )

    def discover(self):
        tables = []
        indexes = []
        for info in islice(self.connection.list_collections(), 20):
            self.checkpoint()
            name = info["name"]
            if name.startswith("system."):
                continue
            validator = (
                info.get("options", {}).get("validator", {}).get("$jsonSchema", {})
            )
            fields = [
                {
                    "name": k,
                    "type": str(v.get("bsonType", "unknown")),
                    "nullable": k not in validator.get("required", []),
                }
                for k, v in validator.get("properties", {}).items()
            ][:100]
            sampled = 0
            if not fields and self.config.get("infer_document_schema"):
                sample = self.connection[name].find({}, max_time_ms=3000).limit(20)
                try:
                    documents = bounded_documents(sample)
                finally:
                    sample.close()
                fields = field_types(documents)
                sampled = len(documents)
            tables.append(
                {
                    "name": name,
                    "schema": "",
                    "columns": fields,
                    "inferred": bool(sampled),
                    "sampled_documents": sampled,
                }
            )
            indexes.extend(
                [
                    {
                        "collection": name,
                        "name": i.get("name"),
                        "keys": list(i.get("key", {}).items()),
                    }
                    for i in self.connection[name].list_indexes()
                ][:20]
            )
        version = self.connection.command("buildInfo").get("version", "unknown")
        return {
            "engine": self.engine,
            "version": version,
            "tables": tables,
            "indexes": indexes,
            "relationships": [],
            "complete": False,
            "sample_records_sent_to_model": False,
            "limitations": self.limitations,
        }

    def validate(self, query, schema):
        q = native(query)
        tables = {t["name"]: t for t in schema["tables"]}
        if q.get("collection") not in tables:
            raise AdapterError("Choose a discovered collection.", "schema_drift")
        if q.get("operation") not in {"find", "aggregate"}:
            raise AdapterError(
                "Only find and read-only aggregation are supported.", "unsafe"
            )
        if set(q) - {
            "collection",
            "operation",
            "filter",
            "projection",
            "sort",
            "limit",
            "pipeline",
        }:
            raise AdapterError(
                "Unknown native query options are not permitted.", "unsafe"
            )
        limit = q.get("limit", 100)
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise AdapterError("Use a limit between 1 and 500.", "result_limit")
        allowed = {
            "$eq",
            "$ne",
            "$gt",
            "$gte",
            "$lt",
            "$lte",
            "$in",
            "$nin",
            "$and",
            "$or",
            "$not",
            "$nor",
            "$exists",
            "$type",
            "$elemMatch",
            "$all",
            "$size",
            "$match",
            "$project",
            "$sort",
            "$limit",
            "$skip",
            "$group",
            "$lookup",
            "$unwind",
            "$count",
            "$sum",
            "$avg",
            "$min",
            "$max",
            "$first",
            "$last",
            "$push",
            "$addToSet",
            "$ifNull",
            "$cond",
            "$multiply",
            "$divide",
            "$subtract",
            "$add",
            "$literal",
            "$dateToString",
            "$toDate",
            "$date",
        }

        def inspect(value, depth=0):
            if depth > 20:
                raise AdapterError(
                    "The native query nesting exceeds the limit.", "unsafe"
                )
            if isinstance(value, dict):
                for key, item in value.items():
                    if str(key).startswith("$") and key not in allowed:
                        raise AdapterError(
                            "This MongoDB operator is not in the read-only allowlist.",
                            "unsafe",
                        )
                    inspect(item, depth + 1)
            elif isinstance(value, list):
                if len(value) > 100:
                    raise AdapterError(
                        "Native arrays exceed the query budget.", "unsafe"
                    )
                for item in value:
                    inspect(item, depth + 1)

        inspect(q)
        mongo_values(
            q
        )  # Validate extended date literals without changing stored native JSON.
        fields = {c["name"] for c in tables[q["collection"]]["columns"]} | {"_id"}

        def known(name, available=fields):
            if not isinstance(name, str) or name not in available:
                raise AdapterError(
                    "A query field is absent from discovered metadata. Inferred schemas can be incomplete; refresh or provide a declared schema.",
                    "schema_drift",
                )

        def filter_fields(value, available):
            if not isinstance(value, dict):
                raise AdapterError("MongoDB filters must be JSON objects.", "syntax")
            for key, item in value.items():
                if key in {"$and", "$or", "$nor"}:
                    if not isinstance(item, list) or not item:
                        raise AdapterError(
                            "Logical filters require a nonempty array of objects.",
                            "syntax",
                        )
                    for nested in item:
                        filter_fields(nested, available)
                elif key == "$not":
                    filter_fields(item, available)
                elif key.startswith("$"):
                    raise AdapterError(
                        "Use field filters or supported logical filters.", "syntax"
                    )
                else:
                    known(key, available)

        def expression_fields(value, available):
            if isinstance(value, str) and value.startswith("$"):
                known(value[1:], available)
            elif isinstance(value, dict):
                if "$literal" not in value:
                    for item in value.values():
                        expression_fields(item, available)
            elif isinstance(value, list):
                for item in value:
                    expression_fields(item, available)

        if q["operation"] == "find":
            filter_fields(q.get("filter", {}), fields)
            projection = q.get("projection", {})
            if not isinstance(projection, dict) or any(
                not isinstance(v, (bool, int)) or v not in {0, 1, False, True}
                for v in projection.values()
            ):
                raise AdapterError(
                    "Find projections use field names and 0 or 1.", "syntax"
                )
            for field in projection:
                known(field)
            sort = q.get("sort", [])
            if isinstance(sort, dict):
                sort = list(sort.items())
                q["sort"] = sort
            if not isinstance(sort, list) or len(sort) > 8:
                raise AdapterError("Use at most eight sort fields.", "syntax")
            for part in sort:
                if (
                    not isinstance(part, (list, tuple))
                    or len(part) != 2
                    or part[1] not in {-1, 1}
                ):
                    raise AdapterError("Sort uses [field, 1 or -1] pairs.", "syntax")
                known(part[0])
        if q["operation"] == "aggregate":
            pipeline = q.get("pipeline", [])
            if not isinstance(pipeline, list) or len(pipeline) > 12:
                raise AdapterError("Use at most twelve aggregation stages.")
            for stage in pipeline:
                if (
                    not isinstance(stage, dict)
                    or len(stage) != 1
                    or next(iter(stage))
                    not in {
                        "$match",
                        "$project",
                        "$sort",
                        "$limit",
                        "$skip",
                        "$group",
                        "$lookup",
                        "$unwind",
                        "$count",
                    }
                ):
                    raise AdapterError("Unsupported aggregation stage.", "unsafe")
                if "$lookup" in stage:
                    lookup = stage["$lookup"]
                    if (
                        set(lookup) != {"from", "localField", "foreignField", "as"}
                        or lookup["from"] not in tables
                    ):
                        raise AdapterError(
                            "Use a simple lookup against a discovered collection.",
                            "schema_drift",
                        )
                    known(lookup["localField"], fields)
                    known(
                        lookup["foreignField"],
                        {c["name"] for c in tables[lookup["from"]]["columns"]}
                        | {"_id"},
                    )
                    if not isinstance(lookup["as"], str) or not re.fullmatch(
                        r"[A-Za-z_][\w]*", lookup["as"]
                    ):
                        raise AdapterError(
                            "Use a simple lookup output field.", "syntax"
                        )
                    fields = fields | {
                        lookup["as"],
                        *(
                            lookup["as"] + "." + c["name"]
                            for c in tables[lookup["from"]]["columns"]
                        ),
                    }
                if "$match" in stage:
                    filter_fields(stage["$match"], fields)
                if "$sort" in stage:
                    if not isinstance(stage["$sort"], dict) or any(
                        v not in {-1, 1} for v in stage["$sort"].values()
                    ):
                        raise AdapterError(
                            "Aggregation sort directions must be 1 or -1.", "syntax"
                        )
                    for field in stage["$sort"]:
                        known(field, fields)
                if "$group" in stage:
                    group = stage["$group"]
                    if not isinstance(group, dict) or "_id" not in group:
                        raise AdapterError(
                            "Aggregation groups require an _id expression.", "syntax"
                        )
                    expression_fields(group, fields)
                    fields = set(group)
                if "$project" in stage:
                    project = stage["$project"]
                    if not isinstance(project, dict):
                        raise AdapterError("Project must be an object.", "syntax")
                    for field, value in project.items():
                        if value in (0, 1) and isinstance(value, (int, bool)):
                            known(field, fields)
                        else:
                            expression_fields(value, fields)
                    if any(v != 0 for v in project.values()):
                        fields = {k for k, v in project.items() if v != 0} | (
                            {"_id"} if project.get("_id") != 0 else set()
                        )
                    else:
                        fields -= set(project)
                if "$unwind" in stage:
                    unwind = stage["$unwind"]
                    path = (
                        unwind
                        if isinstance(unwind, str)
                        else unwind.get("path")
                        if isinstance(unwind, dict)
                        else None
                    )
                    if not isinstance(path, str) or not path.startswith("$"):
                        raise AdapterError(
                            "Unwind requires a discovered array field.", "syntax"
                        )
                    known(path[1:], fields)
                if "$count" in stage:
                    if not isinstance(stage["$count"], str) or not re.fullmatch(
                        r"[A-Za-z_]\w*", stage["$count"]
                    ):
                        raise AdapterError("Use a simple count output field.", "syntax")
                    fields = {stage["$count"]}
                if "$limit" in stage and (
                    not isinstance(stage["$limit"], int)
                    or not 1 <= stage["$limit"] <= 500
                ):
                    raise AdapterError("Aggregation limits must be between 1 and 500.")
                if "$skip" in stage and (
                    not isinstance(stage["$skip"], int)
                    or not 0 <= stage["$skip"] <= 5000
                ):
                    raise AdapterError("Aggregation skips must be between 0 and 5000.")
        return q

    def execute(self, query, schema):
        q = mongo_values(self.validate(query, schema))
        start = time.perf_counter()
        collection = self.connection[q["collection"]]
        if q["operation"] == "find":
            cursor = collection.find(
                q.get("filter", {}), q.get("projection"), max_time_ms=3000
            ).limit(min(501, q.get("limit", 100)))
            if q.get("sort"):
                cursor = cursor.sort([tuple(v) for v in q["sort"]])
        else:
            cursor = collection.aggregate(
                q["pipeline"] + [{"$limit": min(501, q.get("limit", 100))}],
                maxTimeMS=3000,
                allowDiskUse=False,
                batchSize=100,
            )
        def documents():
            for item in cursor:
                self.checkpoint()
                yield item

        try:
            result = document_result(documents(), 0)
        finally:
            cursor.close()
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return result

    def plan(self, query, schema):
        q = mongo_values(self.validate(query, schema))
        command = (
            {
                "find": q["collection"],
                "filter": q.get("filter", {}),
                "limit": q.get("limit", 100),
            }
            if q["operation"] == "find"
            else {
                "aggregate": q["collection"],
                "pipeline": q["pipeline"],
                "cursor": {},
                "allowDiskUse": False,
            }
        )
        if q["operation"] == "find":
            if q.get("projection"):
                command["projection"] = q["projection"]
            if q.get("sort"):
                command["sort"] = dict(q["sort"])
        response = self.connection.command(
            {"explain": command, "verbosity": "queryPlanner", "maxTimeMS": 3000}
        )
        return {
            "kind": "MongoDB queryPlanner (non-executing)",
            "executed": False,
            "plan": response.get("queryPlanner") or response.get("stages", []),
        }

    def close(self):
        if hasattr(self, "client"):
            self.client.close()
        from pathlib import Path

        for file in self.temporary_files:
            Path(file).unlink(missing_ok=True)


class FirebaseBase(Adapter):
    capabilities = Capabilities(query_plans=False, profiling=False)
    token = None

    def _credentials(self):
        account = self.config.get("service_account")
        if (
            not isinstance(account, dict)
            or account.get("type") != "service_account"
            or account.get("token_uri") != "https://oauth2.googleapis.com/token"
        ):
            raise AdapterError(
                "Provide a dedicated read-only Google service account JSON key with the official Google token endpoint.",
                "credentials",
            )
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request

        class BoundedRequest(Request):
            def __call__(self, *args, **kwargs):
                kwargs["timeout"] = 5
                return super().__call__(*args, **kwargs)

        credentials = service_account.Credentials.from_service_account_info(
            account,
            scopes=[
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/firebase.database",
                "https://www.googleapis.com/auth/userinfo.email",
            ],
        )
        credentials.refresh(BoundedRequest())
        self.token = credentials.token

    def _request(self, method, url, **kwargs):
        self.checkpoint()
        self.database_calls += 1
        with httpx.Client(
            timeout=5,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + self.token} if self.token else {},
        ) as c:
            with c.stream(method, url, **kwargs) as r:
                if r.status_code in {401, 403}:
                    raise AdapterError(
                        "Credentials or read-only permissions were refused. Check IAM grants, database rules and project selection.",
                        "permissions",
                    )
                if r.status_code != 200:
                    raise AdapterError(
                        f"Firebase returned HTTP {r.status_code}. Check the query, selected database and required indexes.",
                        "database",
                    )
                data = bytearray()
                for chunk in r.iter_bytes():
                    self.checkpoint()
                    data.extend(chunk)
                    if len(data) > 2_000_000:
                        raise AdapterError(
                            "Firebase response exceeds 2 MB. Narrow the query.",
                            "result_limit",
                        )
                return json.loads(data)

    def close(self):
        pass


def firestore_value(v):
    if "timestampValue" in v:
        return datetime.fromisoformat(v["timestampValue"].replace("Z", "+00:00"))
    if "nullValue" in v:
        return None
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "booleanValue" in v:
        return v["booleanValue"]
    if "mapValue" in v:
        return {
            k: firestore_value(x) for k, x in v["mapValue"].get("fields", {}).items()
        }
    if "arrayValue" in v:
        return [firestore_value(x) for x in v["arrayValue"].get("values", [])]
    return next(iter(v.values()), None)


def firestore_literal(v):
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, dict) and set(v) == {"timestamp"}:
        from datetime import datetime

        datetime.fromisoformat(v["timestamp"].replace("Z", "+00:00"))
        return {"timestampValue": v["timestamp"]}
    if isinstance(v, list) and len(v) <= 30:
        return {"arrayValue": {"values": [firestore_literal(x) for x in v]}}
    raise AdapterError(
        "Unsupported Firestore filter value. Use scalar values, timestamp objects or bounded arrays."
    )


class Firestore(FirebaseBase):
    engine = "firestore"
    limitations = [
        "Firestore Standard Core queries have native filter/index constraints; SQL joins and arbitrary GROUP BY are unavailable.",
        "Field inference is optional and incomplete; up to 20 documents per collection are inspected locally and only names/types reach the model.",
        "This adapter does not expose plans or controlled benchmark indexes; recommendations remain unverified.",
        "Google service-account IAM should be roles/datastore.viewer. IAM credentials bypass Firebase Security Rules.",
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        project = config.get("project_id", "")
        db = config.get("database_id", config.get("database", "(default)"))
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", project) or not re.fullmatch(
            r"\(default\)|[a-zA-Z0-9-]{1,63}", db
        ):
            raise AdapterError(
                "Enter a valid Firebase project and Firestore database ID.",
                "connection_format",
            )
        host = "https://firestore.googleapis.com"
        if config.get("emulator"):
            if os.environ.get("QOT_TEST_NETWORKS") != "1":
                raise AdapterError(
                    "Cloud connections cannot target a local emulator. Use the local connector.",
                    "private_network",
                )
            host = "http://127.0.0.1:" + str(int(config.get("port", 8080)))
            self.token = "owner"
        else:
            self._credentials()
        self.base = (
            host
            + "/v1/projects/"
            + quote(project, safe="")
            + "/databases/"
            + quote(db, safe="")
            + "/documents"
        )

    def _query(self, q):
        structured = {
            "from": [{"collectionId": q["collection"]}],
            "limit": q.get("limit", 100),
        }
        filters = []
        ops = {
            "==": "EQUAL",
            "!=": "NOT_EQUAL",
            "<": "LESS_THAN",
            "<=": "LESS_THAN_OR_EQUAL",
            ">": "GREATER_THAN",
            ">=": "GREATER_THAN_OR_EQUAL",
            "in": "IN",
            "not-in": "NOT_IN",
            "array-contains": "ARRAY_CONTAINS",
            "array-contains-any": "ARRAY_CONTAINS_ANY",
        }
        for f in q.get("filters", []):
            filters.append(
                {
                    "fieldFilter": {
                        "field": {"fieldPath": f["field"]},
                        "op": ops[f["op"]],
                        "value": firestore_literal(f["value"]),
                    }
                }
            )
        if filters:
            structured["where"] = (
                filters[0]
                if len(filters) == 1
                else {"compositeFilter": {"op": "AND", "filters": filters}}
            )
        if q.get("order_by"):
            structured["orderBy"] = [
                {
                    "field": {"fieldPath": v["field"]},
                    "direction": "DESCENDING"
                    if v.get("direction") == "desc"
                    else "ASCENDING",
                }
                for v in q["order_by"]
            ]
        return self._request(
            "POST", self.base + ":runQuery", json={"structuredQuery": structured}
        )

    def discover(self):
        names = self._request(
            "POST", self.base + ":listCollectionIds", json={"pageSize": 20}
        )
        tables = []
        for name in names.get("collectionIds", [])[:20]:
            records = []
            if self.config.get("infer_document_schema"):
                rows = self._query({"collection": name, "limit": 20})
                records = [
                    {
                        k: firestore_value(v)
                        for k, v in row["document"].get("fields", {}).items()
                    }
                    for row in rows
                    if "document" in row
                ]
            tables.append(
                {
                    "name": name,
                    "schema": "",
                    "columns": field_types(records),
                    "inferred": True,
                    "sampled_documents": len(records),
                }
            )
        return {
            "engine": self.engine,
            "version": "Standard Core API v1",
            "tables": tables,
            "indexes": [],
            "relationships": [],
            "complete": False,
            "sample_records_sent_to_model": False,
            "limitations": self.limitations,
        }

    def validate(self, query, schema):
        q = native(query)
        tables = {t["name"]: t for t in schema["tables"]}
        if q.get("collection") not in tables:
            raise AdapterError("Choose a discovered collection.", "schema_drift")
        if set(q) - {"collection", "filters", "order_by", "limit"}:
            raise AdapterError(
                "Only native Firestore filters, ordering and limit are supported.",
                "unsafe",
            )
        if (
            not isinstance(q.get("limit", 100), int)
            or not 1 <= q.get("limit", 100) <= 500
        ):
            raise AdapterError("Use a limit between 1 and 500.")
        fields = {c["name"] for c in tables[q["collection"]]["columns"]}
        if len(q.get("filters", [])) > 8 or len(q.get("order_by", [])) > 4:
            raise AdapterError("The filter or ordering budget is exceeded.")
        for f in q.get("filters", []):
            if set(f) != {"field", "op", "value"} or f["op"] not in {
                "==",
                "!=",
                "<",
                "<=",
                ">",
                ">=",
                "in",
                "not-in",
                "array-contains",
                "array-contains-any",
            }:
                raise AdapterError("Unsupported Firestore filter.")
            if f["field"] not in fields:
                raise AdapterError(
                    "A field is absent from the inferred metadata; refresh the schema.",
                    "schema_drift",
                )
            firestore_literal(f["value"])
        for order in q.get("order_by", []):
            if set(order) - {"field", "direction"} or order.get(
                "direction", "asc"
            ) not in {"asc", "desc"}:
                raise AdapterError("Unsupported Firestore ordering.")
            if order.get("field") not in fields:
                raise AdapterError("Unknown ordering field.", "schema_drift")
        return q

    def execute(self, query, schema):
        q = self.validate(query, schema)
        start = time.perf_counter()
        rows = self._query(q)
        documents = [
            {
                "_document_id": r["document"]["name"].rsplit("/", 1)[-1],
                **{
                    k: firestore_value(v)
                    for k, v in r["document"].get("fields", {}).items()
                },
            }
            for r in rows
            if "document" in r
        ]
        return document_result(documents, (time.perf_counter() - start) * 1000)


class RealtimeDatabase(FirebaseBase):
    engine = "firebase_realtime"
    limitations = [
        "Realtime Database supports one native ordering key with range/equality filtering, not relational joins or server-side aggregation.",
        "Field inference is optional, sampled and incomplete; nested arrays and type variation remain uncertain.",
        "No query plan or controlled benchmark facilities are exposed. Add .indexOn in your own rules only after reviewing recommendations.",
        "Provide a dedicated IAM read-only service account; administrative OAuth credentials may bypass database rules.",
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        url = urlparse(config.get("url", ""))
        emulator = (
            config.get("emulator")
            and os.environ.get("QOT_TEST_NETWORKS") == "1"
            and url.hostname == "127.0.0.1"
        )
        if not emulator and (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith((".firebaseio.com", ".firebasedatabase.app"))
        ):
            raise AdapterError(
                "Use the HTTPS Firebase Realtime Database instance URL, not a general URL.",
                "connection_format",
            )
        if url.username or url.password or url.query or url.fragment:
            raise AdapterError(
                "Put credentials in the service-account field, never in a URL.",
                "connection_format",
            )
        validate_host(url.hostname, url.port or 443)
        prefix = config.get("path", "").strip("/")
        if any(part in {".", ".."} for part in prefix.split("/")) or not re.fullmatch(
            r"[a-zA-Z0-9_/-]*", prefix
        ):
            raise AdapterError("Use a simple database path prefix.")
        self.base = config["url"].rstrip("/") + ("/" + prefix if prefix else "")
        if emulator:
            self.token = "owner"
        else:
            self._credentials()

    def _request(self, method, url, **kwargs):
        if self.config.get("emulator") and self.config.get("namespace"):
            kwargs["params"] = {
                **kwargs.get("params", {}),
                "ns": self.config["namespace"],
            }
        return super()._request(method, url, **kwargs)

    def discover(self):
        root_suffix = "/.json" if urlparse(self.base).path in {"", "/"} else ".json"
        roots = self._request(
            "GET", self.base + root_suffix, params={"shallow": "true"}
        )
        if not isinstance(roots, dict):
            raise AdapterError("Choose a path containing child collections.", "schema")
        tables = []
        for name in sorted(roots)[:20]:
            records = []
            if self.config.get("infer_document_schema"):
                data = (
                    self._request(
                        "GET",
                        self.base + "/" + quote(name, safe="") + ".json",
                        params={"orderBy": '"$key"', "limitToFirst": "20"},
                    )
                    or {}
                )
                if isinstance(data, (dict, list)):
                    records = [
                        v if isinstance(v, dict) else {"value": v}
                        for v in (data.values() if isinstance(data, dict) else data)
                        if v is not None
                    ]
            tables.append(
                {
                    "name": name,
                    "schema": "",
                    "columns": [
                        {**f, "name": f["name"].replace(".", "/")}
                        for f in field_types(records)
                    ],
                    "inferred": True,
                    "sampled_documents": len(records),
                }
            )
        return {
            "engine": self.engine,
            "version": "Realtime REST v1",
            "tables": tables,
            "indexes": [],
            "relationships": [],
            "complete": False,
            "sample_records_sent_to_model": False,
            "limitations": self.limitations,
        }

    def validate(self, query, schema):
        q = native(query)
        tables = {t["name"]: t for t in schema["tables"]}
        if isinstance(q.get("path"), str):
            q["path"] = q["path"].strip("/").removesuffix(".json")
        if q.get("path") not in tables:
            raise AdapterError("Select a discovered collection path.", "schema_drift")
        if set(q) - {
            "path",
            "order_by",
            "equal_to",
            "start_at",
            "end_at",
            "limit",
            "last",
        }:
            raise AdapterError(
                "Unsupported native Realtime Database options.", "unsafe"
            )
        if (
            not isinstance(q.get("limit", 100), int)
            or not 1 <= q.get("limit", 100) <= 500
        ):
            raise AdapterError("Use a limit between 1 and 500.")
        order = q.get("order_by", "$key")
        fields = {c["name"] for c in tables[q["path"]]["columns"]}
        if order == "$priority":
            raise AdapterError(
                "Priority ordering is not exposed by this adapter; select a field, $key or $value.",
                "unsupported",
            )
        if order not in {"$key", "$value"} and (
            order not in fields or not re.fullmatch(r"[\w/]+", order)
        ):
            raise AdapterError(
                "Select one discovered field for ordering.", "schema_drift"
            )
        if "equal_to" in q and ("start_at" in q or "end_at" in q):
            raise AdapterError("Use equality or a range, not both.")
        for key in ["equal_to", "start_at", "end_at"]:
            if key in q and not isinstance(q[key], (str, int, float, bool, type(None))):
                raise AdapterError("Filter values must be scalars.")
        return q

    def execute(self, query, schema):
        q = self.validate(query, schema)
        start = time.perf_counter()
        params = {
            "orderBy": json.dumps(q.get("order_by", "$key")),
            "limitToLast" if q.get("last") else "limitToFirst": str(
                q.get("limit", 100)
            ),
        }
        for key, native_key in [
            ("equal_to", "equalTo"),
            ("start_at", "startAt"),
            ("end_at", "endAt"),
        ]:
            if key in q:
                params[native_key] = json.dumps(q[key])
        data = (
            self._request(
                "GET",
                self.base + "/" + quote(q["path"], safe="") + ".json",
                params=params,
            )
            or {}
        )
        if not isinstance(data, dict):
            if isinstance(data, list):
                data = {str(i): v for i, v in enumerate(data) if v is not None}
            else:
                raise AdapterError("Query a child collection, not a scalar node.")
        documents = [
            {"_key": k, **(v if isinstance(v, dict) else {"value": v})}
            for k, v in data.items()
        ]
        # REST returns a JSON object, not sorted rows. Re-establish native ordering
        # with type order and key tie-breakers while preserving the server filter.
        field = q.get("order_by", "$key")

        def key_order(key):
            if re.fullmatch(r"-?(0|[1-9]\d*)", key) and -(2**31) <= int(key) < 2**31:
                return (0, int(key))
            return (1, key)

        def sort_key(d):
            if field == "$key":
                return key_order(d["_key"])
            v = (
                d["_key"]
                if field == "$key"
                else d.get("value")
                if field == "$value"
                else d.get(field)
            )
            if "/" in field:
                v = d
                for segment in field.split("/"):
                    v = v.get(segment) if isinstance(v, dict) else None
            rank = (
                0
                if v is None
                else 1
                if v is False
                else 2
                if v is True
                else 3
                if isinstance(v, (int, float))
                else 4
                if isinstance(v, str)
                else 5
            )
            return (rank, v if rank in {3, 4} else "", key_order(d["_key"]))

        documents.sort(key=sort_key)
        return document_result(documents, (time.perf_counter() - start) * 1000)
