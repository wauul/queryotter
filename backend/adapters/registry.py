from contextlib import contextmanager
from backend.adapters.base import AdapterError
from backend.adapters.network import network_scope
from backend.adapters.relational import (
    PostgreSQL,
    MySQL,
    MariaDB,
    SQLite,
    SQLServer,
    CockroachDB,
)
from backend.adapters.documents import MongoDB, Firestore, RealtimeDatabase

ADAPTERS = {
    a.engine: a
    for a in [
        PostgreSQL,
        MySQL,
        MariaDB,
        SQLite,
        SQLServer,
        CockroachDB,
        MongoDB,
        Firestore,
        RealtimeDatabase,
    ]
}


@contextmanager
def open_adapter(engine, config, check=lambda: None):
    if engine not in ADAPTERS:
        raise AdapterError("This database engine is unsupported.", "unsupported")
    if config.get("connector_id"):
        from backend.connector import RemoteAdapter

        with RemoteAdapter(engine, config, check) as adapter:
            yield adapter
        return
    if engine == "sqlite" and config.get("url"):
        from backend.adapters.libsql import LibSQL

        definition = LibSQL
    else:
        definition = ADAPTERS[engine]
    with network_scope():
        # Keep a reference even if a constructor fails after allocating a socket/CA/copy.
        adapter = definition.__new__(definition)
        try:
            definition.__init__(adapter, config, check)
            yield adapter
        except AdapterError:
            raise
        except Exception as error:
            from backend.investigate import Cancelled
            from backend.adapters.errors import sanitized
            if isinstance(error, Cancelled):
                raise
            raise sanitized(error) from None
        finally:
            if hasattr(adapter, "temporary_files"):
                adapter.close()


def catalog():
    from pathlib import Path
    import json

    path = Path("public/adapter-verification.json")
    verified = json.loads(path.read_text()) if path.exists() else {}
    return [
        {
            "id": key,
            "name": {
                "postgresql": "PostgreSQL",
                "mysql": "MySQL",
                "mariadb": "MariaDB",
                "sqlite": "SQLite",
                "mongodb": "MongoDB",
                "sqlserver": "Microsoft SQL Server",
                "cockroachdb": "CockroachDB",
                "firestore": "Firebase Cloud Firestore",
                "firebase_realtime": "Firebase Realtime Database",
            }[key],
            "capabilities": a.capabilities.public(),
            "limitations": a.limitations,
            "verification": verified.get(
                key,
                {
                    "status": "Implemented; integration verification pending",
                    "hosted_provider": "Requires user credentials",
                },
            ),
        }
        for key, a in ADAPTERS.items()
    ]
