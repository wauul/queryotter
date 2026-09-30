"""Actionable categories without exposing driver messages, records or credentials."""
from backend.adapters.base import AdapterError


def sanitized(error):
    # Inspect only for fixed driver categories; never return the provider message.
    message = str(error).lower()
    state = getattr(error, "sqlstate", None)
    number = getattr(error, "code", None)
    if not isinstance(number, int) and getattr(error, "args", ()) and isinstance(error.args[0], int):
        number = error.args[0]
    name = type(error).__name__
    if state in {"28P01", "28000"} or number in {1045, 18, 18456} or name in {"RefreshError", "DefaultCredentialsError"} or "password authentication failed" in message or "login failed for user" in message:
        return AdapterError("Authentication failed. Rotate the dedicated database credential and check its database/project and expiry.", "credentials")
    if state == "42501" or number in {13, 1142, 229}:
        return AdapterError("Read permissions were denied. Check SELECT/viewer grants on the selected database and schema; privileged credentials are not accepted.", "permissions")
    if state in {"42703", "42P01"} or number in {1054, 1146, 207, 208}:
        return AdapterError("The database schema differs from the cached metadata. Refresh the schema, review the actual fields and validate again.", "schema_drift")
    if state == "57014" or number in {50, 3024, 1969, 1222} or "Timeout" in name:
        return AdapterError("The database operation exceeded its time limit. Narrow the query or inspect a non-executing plan.", "timeout")
    if "SSL" in name or name in {"Error", "SSLCertVerificationError"} and type(error).__module__.startswith("OpenSSL") or number == 2026 or "certificate verify failed" in message or "certificate verification failed" in message:
        return AdapterError("TLS verification failed. Check the provider hostname and CA bundle. Certificate verification cannot be disabled for a cloud connection.", "tls")
    if state == "42601" or number == 1064:
        return AdapterError("The database rejected the native syntax for this engine/version. Review its dialect and metadata; parser validation alone does not establish executability.", "syntax")
    return AdapterError(f"The database operation failed ({name}). Check credentials, verified TLS, the provider network allowlist and read-only grants. No provider response body is exposed.", "connection")
