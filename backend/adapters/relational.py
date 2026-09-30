import base64
import os
import re
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import unquote
import certifi
from backend.adapters.base import Adapter, AdapterError, Capabilities
from backend.adapters.network import relational_config, validate_host
from backend.adapters.sql import validate_sql, bind_literals, bounded_query, bounded_result


class Relational(Adapter):
    capabilities = Capabilities(query_plans=True, profiling=True)

    def validate(self, query, schema):
        return validate_sql(query, self.dialect, schema)[0]

    def cursor(self, stream=False):
        adapter = self
        if stream and self.engine == "postgresql":
            raw = self.connection.cursor(name="qot_" + uuid.uuid4().hex)
        elif stream and self.engine in {"mysql", "mariadb"}:
            from pymysql.cursors import SSCursor
            raw = self.connection.cursor(SSCursor)
        else:
            raw = self.connection.cursor()

        class CountingCursor:
            def execute(self, *args, **kwargs):
                adapter.database_calls += 1
                return raw.execute(*args, **kwargs)

            def __getattr__(self, name):
                return getattr(raw, name)

        return CountingCursor()

    def execute(self, query, schema):
        _, tree = validate_sql(query, self.dialect, schema)
        sql, values = bind_literals(
            bounded_query(tree), self.dialect, "sqlite" if self.engine == "sqlite" else "format"
        )
        self.checkpoint()
        start = time.perf_counter()
        with_cursor = self.cursor(stream=True)
        try:
            with_cursor.execute(
                sql, values or None
            ) if self.engine != "sqlite" else with_cursor.execute(sql, values)
            columns = [d[0] for d in with_cursor.description]
            def rows():
                for _ in range(501):
                    self.checkpoint()
                    row = with_cursor.fetchone()
                    if row is None:
                        return
                    yield row

            result = bounded_result(columns, rows(), 0)
        except Exception:
            # SQLite reports progress-handler interruption as OperationalError.
            # Recheck the actual deadline/cancellation before classifying the driver.
            self.checkpoint()
            raise
        finally:
            with_cursor.close()
        self.checkpoint()
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        result["server_row_limit"] = 501
        return result

    def _rows(self, query, values=()):
        self.checkpoint()
        cursor = self.cursor()
        try:
            cursor.execute(query, values)
            return cursor.fetchmany(501)
        finally:
            cursor.close()

    def _metadata(self, rows, indexes, relations, version):
        tables = {}
        for schema, table, column, kind, nullable in rows:
            entry = tables.setdefault(
                table, {"name": table, "schema": schema, "columns": []}
            )
            entry["columns"].append(
                {"name": column, "type": kind, "nullable": nullable == "YES"}
            )
        if len(rows) > 500:
            raise AdapterError(
                "This schema exceeds 500 columns. Select a smaller schema.",
                "schema_limit",
            )
        return {
            "engine": self.engine,
            "version": str(version),
            "tables": list(tables.values()),
            "indexes": indexes,
            "relationships": relations,
            "complete": True,
            "scope": self.config.get("schema", "public"),
            "sample_records_sent_to_model": False,
            "timezone": "UTC",
            "limitations": self.limitations,
        }


class PostgreSQL(Relational):
    engine = "postgresql"
    dialect = "postgres"
    limitations = [
        "Connected databases receive non-executing EXPLAIN only; no indexes are applied.",
        "Measured benchmark recommendations require a disposable copy or the separate seeded PostgreSQL experiment workspace.",
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        import psycopg
        from psycopg import sql

        default_port = 26257 if self.engine == "cockroachdb" else 5432
        url, local = relational_config(config, {"postgres", "postgresql"}, default_port)
        self.connection = psycopg.connect(
            host=url.hostname,
            hostaddr=validate_host(url.hostname, url.port or default_port)[0][4][0],
            port=url.port or default_port,
            dbname=unquote(url.path.strip("/")),
            user=unquote(url.username or ""),
            password=unquote(url.password or ""),
            connect_timeout=5,
            sslmode="disable" if local else "verify-full",
            sslrootcert=None if local else self.ca_file(),
            options="-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=500",
        )
        selected = config.get("schema", "public")
        if not re.fullmatch(r"[\w-]{1,63}", selected):
            raise AdapterError("Choose one valid schema name.")
        self.connection.execute(
            sql.SQL("SET search_path TO pg_catalog,{}").format(sql.Identifier(selected))
        )
        self.database_calls += 1
        if self.engine == "postgresql":
            self.database_calls += 2
            role = self.connection.execute(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            if any(role):
                self.close()
                raise AdapterError(
                    "Use a restricted read-only login without superuser, CREATE DATABASE/ROLE, replication or RLS bypass privileges.",
                    "permissions",
                )
            writes = self.connection.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_type='BASE TABLE' AND (has_table_privilege(table_schema||'.'||quote_ident(table_name),'INSERT') OR has_table_privilege(table_schema||'.'||quote_ident(table_name),'UPDATE') OR has_table_privilege(table_schema||'.'||quote_ident(table_name),'DELETE'))) OR has_schema_privilege(%s,'CREATE')",
                (selected, selected),
            ).fetchone()[0]
            if writes:
                self.close()
                raise AdapterError(
                    "This login has write or schema CREATE privileges. Use SELECT-only grants on the selected schema.",
                    "permissions",
                )

    def discover(self):
        schema = self.config.get("schema", "public")
        rows = self._rows(
            "SELECT c.table_schema,c.table_name,c.column_name,c.data_type,c.is_nullable FROM information_schema.columns c JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name WHERE c.table_schema=%s AND t.table_type='BASE TABLE' ORDER BY c.table_name,c.ordinal_position LIMIT 501",
            (schema,),
        )
        indexes = self._rows(
            "SELECT tablename,indexdef FROM pg_indexes WHERE schemaname=%s ORDER BY tablename,indexname LIMIT 100",
            (schema,),
        )
        relations = self._rows(
            "SELECT src.relname,sa.attname,dst.relname,da.attname FROM pg_constraint con JOIN pg_class src ON src.oid=con.conrelid JOIN pg_namespace ns ON ns.oid=src.relnamespace JOIN pg_class dst ON dst.oid=con.confrelid CROSS JOIN LATERAL unnest(con.conkey,con.confkey) AS keys(srcnum,dstnum) JOIN pg_attribute sa ON sa.attrelid=src.oid AND sa.attnum=keys.srcnum JOIN pg_attribute da ON da.attrelid=dst.oid AND da.attnum=keys.dstnum WHERE con.contype='f' AND ns.nspname=%s AND has_table_privilege(src.oid,'SELECT') AND has_table_privilege(dst.oid,'SELECT') LIMIT 100",
            (schema,),
        )
        return self._metadata(
            rows, indexes, relations, self._rows("SELECT version()")[0][0]
        )

    def plan(self, query, schema):
        _, tree = validate_sql(query, self.dialect, schema)
        statement, values = bind_literals(tree, self.dialect, "format")
        self.checkpoint()
        return {
            "kind": "PostgreSQL non-executing EXPLAIN",
            "executed": False,
            "plan": self._rows("EXPLAIN (FORMAT JSON) " + statement, values or None)[0][
                0
            ],
        }


class CockroachDB(PostgreSQL):
    engine = "cockroachdb"
    limitations = [
        "CockroachDB uses PostgreSQL wire protocol but its optimizer and distributed execution differ.",
        "Non-executing distributed plans are available; connected databases are never benchmarked with experimental indexes.",
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        roles = self._rows("SHOW GRANTS FOR CURRENT_USER")
        if any(
            any(
                str(v).upper()
                in {"ADMIN", "ALL", "CREATE", "UPDATE", "INSERT", "DELETE", "DROP"}
                for v in row
            )
            for row in roles
        ):
            self.close()
            raise AdapterError(
                "Use a SELECT-only CockroachDB role without admin or write grants.",
                "permissions",
            )

    def discover(self):
        schema = self.config.get("schema", "public")
        rows = self._rows(
            "SELECT c.table_schema,c.table_name,c.column_name,c.data_type,c.is_nullable FROM information_schema.columns c JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name WHERE c.table_schema=%s AND t.table_type='BASE TABLE' ORDER BY c.table_name,c.ordinal_position LIMIT 501",
            (schema,),
        )
        return self._metadata(
            rows,
            self._rows(
                "SELECT tablename,indexdef FROM pg_indexes WHERE schemaname=%s LIMIT 100",
                (schema,),
            ),
            self._rows(
                "SELECT src.relname,sa.attname,dst.relname,da.attname FROM pg_constraint con JOIN pg_class src ON src.oid=con.conrelid JOIN pg_namespace ns ON ns.oid=src.relnamespace JOIN pg_class dst ON dst.oid=con.confrelid CROSS JOIN LATERAL unnest(con.conkey,con.confkey) AS keys(srcnum,dstnum) JOIN pg_attribute sa ON sa.attrelid=src.oid AND sa.attnum=keys.srcnum JOIN pg_attribute da ON da.attrelid=dst.oid AND da.attnum=keys.dstnum WHERE con.contype='f' AND ns.nspname=%s LIMIT 100",
                (schema,),
            ),
            self._rows("SELECT version()")[0][0],
        )

    def plan(self, query, schema):
        _, tree = validate_sql(query, self.dialect, schema)
        statement, values = bind_literals(tree, self.dialect, "format")
        return {
            "kind": "CockroachDB non-executing EXPLAIN",
            "executed": False,
            "plan": self._rows("EXPLAIN (OPT, VERBOSE) " + statement, values or None),
        }


class MySQL(Relational):
    engine = "mysql"
    dialect = "mysql"
    limitations = [
        "Non-executing JSON plans and observed client latency are available; indexes are never changed on connected databases."
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        import pymysql

        url, local = relational_config(config, {"mysql", "mariadb"}, 3306)
        self.database = unquote(url.path.strip("/"))

        class VerifiedConnection(pymysql.connections.Connection):
            def _request_authentication(client):
                from pymysql.constants import CLIENT

                if not local and not client.server_capabilities & CLIENT.SSL:
                    raise AdapterError(
                        "The server did not offer TLS. Use a verified TLS endpoint or the local connector.",
                        "tls",
                    )
                return super()._request_authentication()

        self.connection = VerifiedConnection(
            host=url.hostname,
            port=url.port or 3306,
            user=unquote(url.username or ""),
            password=unquote(url.password or ""),
            database=self.database,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            autocommit=False,
            ssl_disabled=local,
            ssl_ca=None if local else self.ca_file(),
            ssl_verify_cert=not local,
            ssl_verify_identity=not local,
        )
        cursor = self.cursor()
        try:
            cursor.execute("SET time_zone='+00:00'")
            cursor.execute(
                "SET SESSION max_statement_time=3"
                if self.engine == "mariadb"
                else "SET SESSION MAX_EXECUTION_TIME=3000"
            )
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("SHOW GRANTS FOR CURRENT_USER")
            grants = cursor.fetchall()
        finally:
            cursor.close()
        for row in grants:
            granted = str(row[0]).split(" ON ")[0].upper()
            if not granted.startswith("GRANT ") or any(
                word in granted
                for word in [
                    "ALL PRIVILEGES",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "CREATE",
                    "DROP",
                    "ALTER",
                    "EXECUTE",
                    "FILE",
                    "SUPER",
                    "PROXY",
                ]
            ):
                self.close()
                raise AdapterError(
                    "Use SELECT-only MySQL/MariaDB credentials without write, FILE, EXECUTE, SUPER or role grants.",
                    "permissions",
                )
            if not set(granted.removeprefix("GRANT ").split(", ")).issubset(
                {"SELECT", "SHOW VIEW", "USAGE"}
            ):
                self.close()
                raise AdapterError(
                    "Role or administrative grants are not accepted. Create a dedicated SELECT-only login.",
                    "permissions",
                )

    def discover(self):
        rows = self._rows(
            "SELECT c.table_schema,c.table_name,c.column_name,c.column_type,c.is_nullable FROM information_schema.columns c JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name WHERE c.table_schema=%s AND t.table_type='BASE TABLE' ORDER BY c.table_name,c.ordinal_position LIMIT 501",
            (self.database,),
        )
        indexes = self._rows(
            "SELECT table_name,index_name,column_name,seq_in_index,non_unique FROM information_schema.statistics WHERE table_schema=%s ORDER BY table_name,index_name,seq_in_index LIMIT 100",
            (self.database,),
        )
        relationships = self._rows(
            "SELECT table_name,column_name,referenced_table_name,referenced_column_name FROM information_schema.key_column_usage WHERE table_schema=%s AND referenced_table_name IS NOT NULL LIMIT 100",
            (self.database,),
        )
        return self._metadata(
            rows, indexes, relationships, self._rows("SELECT VERSION()")[0][0]
        )

    def plan(self, query, schema):
        import json

        _, tree = validate_sql(query, self.dialect, schema)
        statement, values = bind_literals(tree, self.dialect, "format")
        return {
            "kind": self.engine + " non-executing JSON EXPLAIN",
            "executed": False,
            "plan": json.loads(
                self._rows("EXPLAIN FORMAT=JSON " + statement, values or None)[0][0]
            ),
        }


class MariaDB(MySQL):
    engine = "mariadb"


class SQLServer(Relational):
    engine = "sqlserver"
    dialect = "tsql"
    limitations = [
        "Estimated XML plans need SHOWPLAN grants; availability is checked for each connection.",
        "Read-only routing is not an authorization boundary. Database permissions are checked and SQL is separately validated.",
        "Integrated Windows authentication is not supported; use a restricted SQL login over TLS or the local connector.",
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        import pytds

        url, local = relational_config(config, {"mssql", "sqlserver"}, 1433)
        self.connection = pytds.connect(
            server=url.hostname,
            port=url.port or 1433,
            database=unquote(url.path.strip("/")),
            user=unquote(url.username or ""),
            password=unquote(url.password or ""),
            timeout=3,
            login_timeout=5,
            cafile=None if local else self.ca_file(),
            validate_host=True,
            enc_login_only=False,
            autocommit=False,
            readonly=True,
            disable_connect_retry=True,
        )
        self._rows("SET LOCK_TIMEOUT 500")
        permissions = self._rows(
            "SELECT permission_name FROM fn_my_permissions(NULL,'DATABASE')"
        )
        forbidden = {
            "CONTROL",
            "ALTER",
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE TABLE",
            "CREATE PROCEDURE",
            "EXECUTE",
            "TAKE OWNERSHIP",
        }
        if any(
            row[0] in forbidden or row[0].startswith("ALTER ") for row in permissions
        ):
            self.close()
            raise AdapterError(
                "Use a restricted SQL Server login with SELECT and optional SHOWPLAN only.",
                "permissions",
            )
        unsafe = self._rows(
            "SELECT TOP (1) 1 FROM sys.tables WHERE HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(schema_id))+'.'+QUOTENAME(name),'OBJECT','INSERT')=1 OR HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(schema_id))+'.'+QUOTENAME(name),'OBJECT','UPDATE')=1 OR HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(schema_id))+'.'+QUOTENAME(name),'OBJECT','DELETE')=1"
        )
        if unsafe:
            self.close()
            raise AdapterError(
                "The login has write permissions on a table. Use a separate read-only login.",
                "permissions",
            )
        plan = (
            self._rows("SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','SHOWPLAN')")[0][
                0
            ]
            == 1
        )
        self.capabilities = Capabilities(query_plans=plan, profiling=True)

    def _rows(self, query, values=()):
        self.checkpoint()
        cursor = self.cursor()
        try:
            cursor.execute(query, values or None)
            return cursor.fetchmany(501) if cursor.description else []
        finally:
            cursor.close()

    def discover(self):
        schema = self.config.get("schema", "dbo")
        rows = self._rows(
            "SELECT TOP (501) c.TABLE_SCHEMA,c.TABLE_NAME,c.COLUMN_NAME,c.DATA_TYPE,c.IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS c JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA=c.TABLE_SCHEMA AND t.TABLE_NAME=c.TABLE_NAME WHERE c.TABLE_SCHEMA=%s AND t.TABLE_TYPE='BASE TABLE' ORDER BY c.TABLE_NAME,c.ORDINAL_POSITION",
            (schema,),
        )
        indexes = self._rows(
            "SELECT TOP (100) t.name,i.name,c.name,ic.key_ordinal FROM sys.indexes i JOIN sys.tables t ON t.object_id=i.object_id JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id WHERE SCHEMA_NAME(t.schema_id)=%s ORDER BY t.name,i.name,ic.key_ordinal",
            (schema,),
        )
        relations = self._rows(
            "SELECT TOP (100) OBJECT_NAME(parent_object_id),COL_NAME(parent_object_id,parent_column_id),OBJECT_NAME(referenced_object_id),COL_NAME(referenced_object_id,referenced_column_id) FROM sys.foreign_key_columns"
        )
        return self._metadata(
            rows,
            indexes,
            relations,
            self._rows("SELECT CAST(SERVERPROPERTY('ProductVersion') AS VARCHAR(100))")[
                0
            ][0],
        )

    def plan(self, query, schema):
        if not self.capabilities.query_plans:
            return Adapter.plan(self, query, schema)
        _, tree = validate_sql(query, self.dialect, schema)
        cursor = self.cursor()
        try:
            cursor.execute("SET SHOWPLAN_XML ON")
            cursor.execute(tree.sql(dialect=self.dialect))
            plan = cursor.fetchmany(10)
        finally:
            cursor.execute("SET SHOWPLAN_XML OFF")
            cursor.close()
        return {
            "kind": "SQL Server estimated XML plan",
            "executed": False,
            "plan": plan,
        }


class SQLite(Relational):
    engine = "sqlite"
    dialect = "sqlite"
    capabilities = Capabilities(
        query_plans=True, profiling=True, controlled_benchmarking=True
    )
    limitations = [
        "Execution and benchmarks use a copy of the uploaded database, never its original file.",
        "EXPLAIN QUERY PLAN is an estimate; observed client timing includes result decoding.",
        "Read-only uploads are limited to 2 MiB; virtual tables, extension loading and cross-file access are blocked.",
    ]

    def __init__(self, config, check=lambda: None):
        super().__init__(config, check)
        try:
            data = base64.b64decode(config["data"], validate=True)
        except (KeyError, ValueError):
            raise AdapterError("Upload a SQLite database copy.", "upload") from None
        if not data.startswith(b"SQLite format 3\x00") or len(data) > 2_097_152:
            raise AdapterError("Use a SQLite database file of at most 2 MiB.", "upload")
        self.file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.file.write(data)
        self.file.close()
        self.connection = sqlite3.connect(
            Path(self.file.name).as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1
        )
        self.connection.enable_load_extension(False)
        self.connection.execute("PRAGMA trusted_schema=OFF")
        self.connection.execute("PRAGMA query_only=ON")
        self.connection.execute("PRAGMA temp_store=MEMORY")
        self.connection.execute("PRAGMA cache_size=-2048")
        if hasattr(self.connection, "setconfig"):
            self.connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        for category, limit in [
            (sqlite3.SQLITE_LIMIT_LENGTH, 2_000_000),
            (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 16000),
            (sqlite3.SQLITE_LIMIT_COLUMN, 100),
            (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 10),
            (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 50),
            (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
        ]:
            self.connection.setlimit(category, limit)
        self.connection.set_progress_handler(self._progress, 1000)
        if self.connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            self.close()
            raise AdapterError(
                "The uploaded database failed its integrity check.", "upload"
            )
        self.connection.set_authorizer(self._authorize)

    def _progress(self):
        try:
            self.checkpoint()
            return 0
        except Exception:
            return 1

    @staticmethod
    def _authorize(action, arg1, arg2, db, trigger):
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
        }
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() in {
            "load_extension",
            "readfile",
            "writefile",
            "fts3_tokenizer",
        }:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    def discover(self):
        self.connection.set_authorizer(None)
        try:
            tables = []
            names = self._rows(
                "SELECT name,sql FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT 31"
            )
            if len(names) > 30:
                raise AdapterError(
                    "Select a copy with no more than 30 tables.", "schema_limit"
                )
            for name, ddl in names:
                if "VIRTUAL TABLE" in (ddl or "").upper():
                    raise AdapterError(
                        "SQLite virtual tables are not permitted in uploads.", "upload"
                    )
                quoted = '"' + name.replace('"', '""') + '"'
                fields = self._rows("PRAGMA table_info(" + quoted + ")")
                tables.append(
                    {
                        "name": name,
                        "schema": "",
                        "columns": [
                            {
                                "name": r[1],
                                "type": r[2] or "TEXT",
                                "nullable": not bool(r[3]),
                                "primary_key": bool(r[5]),
                            }
                            for r in fields
                        ],
                    }
                )
            indexes = self._rows(
                "SELECT tbl_name,sql FROM sqlite_schema WHERE type='index' AND sql IS NOT NULL LIMIT 100"
            )
            relationships = []
            for table in tables:
                quoted = '"' + table["name"].replace('"', '""') + '"'
                for row in self._rows("PRAGMA foreign_key_list(" + quoted + ")"):
                    relationships.append([table["name"], row[3], row[2], row[4]])
            return {
                "engine": self.engine,
                "version": sqlite3.sqlite_version,
                "tables": tables,
                "indexes": indexes,
                "relationships": relationships,
                "complete": True,
                "scope": "uploaded copy",
                "timezone": "UTC",
                "sample_records_sent_to_model": False,
                "limitations": self.limitations,
            }
        finally:
            self.connection.set_authorizer(self._authorize)

    def plan(self, query, schema):
        _, tree = validate_sql(query, self.dialect, schema)
        statement, values = bind_literals(tree, self.dialect, "sqlite")
        return {
            "kind": "SQLite EXPLAIN QUERY PLAN on uploaded copy",
            "executed": False,
            "plan": self._rows("EXPLAIN QUERY PLAN " + statement, values),
        }

    def close(self):
        super().close()
        if hasattr(self, "file"):
            Path(self.file.name).unlink(missing_ok=True)
