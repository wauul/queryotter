"""Portable certificate verification for hosted PostgreSQL connections."""

from urllib.parse import urlparse, parse_qs
import certifi


def tls_options(url):
    parsed = urlparse(url)
    root = parse_qs(parsed.query).get("sslrootcert", [None])[0]
    if parsed.hostname not in {"localhost", "127.0.0.1"} and root in {None, "system"}:
        return {"sslrootcert": certifi.where()}
    return {}
