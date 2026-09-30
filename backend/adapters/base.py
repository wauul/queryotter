from dataclasses import dataclass, asdict
import time


class AdapterError(ValueError):
    def __init__(self, message, code="invalid_query"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Capabilities:
    connection_testing: bool = True
    discovery: bool = True
    generation: bool = True
    validation: bool = True
    read_only_execution: bool = True
    query_plans: bool = False
    profiling: bool = False
    candidate_optimization: bool = True
    controlled_benchmarking: bool = False
    cancellation: bool = True
    timeouts: bool = True

    def public(self):
        return asdict(self)


class Adapter:
    engine = ""
    dialect = None
    capabilities = Capabilities()
    limitations = []

    def __init__(self, config, check=lambda: None):
        self.config = config
        self.check = check
        self.deadline = time.monotonic() + 8
        self.connection = None
        self.temporary_files = []
        self.database_calls = 0

    def ca_file(self):
        import ssl
        import tempfile
        import certifi

        pem = self.config.get("ca_certificate")
        if not pem:
            return certifi.where()
        if (
            not isinstance(pem, str)
            or len(pem) > 32000
            or "PRIVATE KEY" in pem
            or "-----BEGIN CERTIFICATE-----" not in pem
        ):
            raise AdapterError(
                "Use a PEM CA certificate bundle without private keys, up to 32,000 characters.",
                "tls",
            )
        try:
            ssl.create_default_context(cadata=pem)
        except ssl.SSLError:
            raise AdapterError(
                "The CA certificate bundle could not be validated.", "tls"
            ) from None
        file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
        file.write(pem.encode())
        file.close()
        self.temporary_files.append(file.name)
        return file.name

    def checkpoint(self):
        self.check()
        if time.monotonic() > self.deadline:
            raise AdapterError("Database operation exceeded its time limit.", "timeout")

    def validate(self, query, schema):
        raise NotImplementedError

    def discover(self):
        raise NotImplementedError

    def execute(self, query, schema):
        raise NotImplementedError

    def plan(self, query, schema):
        raise AdapterError(
            "This adapter does not expose a non-executing plan.", "unsupported"
        )

    def close(self):
        from pathlib import Path

        try:
            if self.connection:
                self.connection.close()
        finally:
            for file in self.temporary_files:
                Path(file).unlink(missing_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
