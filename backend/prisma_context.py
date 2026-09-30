"""Prisma is optional context, checked against authoritative database metadata."""

import re
from backend.adapters.base import AdapterError


def parse(source):
    if not isinstance(source, str) or len(source) > 30000:
        raise AdapterError(
            "Paste a Prisma schema of at most 30,000 characters.", "schema_limit"
        )
    source = re.sub(r"//[^\n]*", "", source)
    models = []
    for match in re.finditer(r"\bmodel\s+(\w+)\s*\{([^{}]*)\}", source, re.S):
        name, body = match.groups()
        mapped = re.search(r'@@map\("([^"\n]+)"\)', body)
        fields = []
        for line in body.splitlines():
            field = re.match(r"\s*(\w+)\s+([\w?\[\]]+)\s*(.*)", line)
            if not field:
                continue
            logical, kind, options = field.groups()
            mapping = re.search(r'@map\("([^"\n]+)"\)', options)
            relation = re.search(
                r"@relation\(.*?fields:\s*\[([^]]+)\].*?references:\s*\[([^]]+)\]",
                options,
            )
            fields.append(
                {
                    "model_field": logical,
                    "database_field": mapping.group(1) if mapping else logical,
                    "type": kind,
                    "relation": {
                        "model": kind.rstrip("?[]"),
                        "fields": [s.strip() for s in relation.group(1).split(",")],
                        "references": [s.strip() for s in relation.group(2).split(",")],
                    }
                    if relation
                    else None,
                }
            )
        models.append(
            {
                "model": name,
                "table": mapped.group(1) if mapped else name,
                "fields": fields[:100],
            }
        )
    if not models:
        raise AdapterError(
            "No Prisma model blocks were found. This import does not establish a database connection.",
            "schema",
        )
    return models[:30]


def reconcile(models, metadata):
    tables = {t["name"]: {c["name"] for c in t["columns"]} for t in metadata["tables"]}
    return [
        {
            "model": m["model"],
            "table": m["table"],
            "verified_table": m["table"] in tables,
            "fields": [
                {
                    **f,
                    "verified_field": f["database_field"]
                    in tables.get(m["table"], set()),
                    "relationship_note": "ORM relation context; verify against database constraints and business meaning."
                    if f["relation"]
                    else None,
                }
                for f in m["fields"]
            ],
        }
        for m in models
    ]
