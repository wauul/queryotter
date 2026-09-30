"""Check every actual DNS resolution while the single worker opens an adapter.

Private targets belong to a separately configured local connector, not the cloud.
"""

import ipaddress
import os
import socket
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlparse
from backend.adapters.base import AdapterError

_private_scope = ContextVar("qot_private_hosts", default=())


def public_address(address):
    try:
        return ipaddress.ip_address(address.split("%")[0]).is_global
    except ValueError:
        return False


def validate_host(host, port, *, private_hosts=None):
    private_hosts = _private_scope.get() if private_hosts is None else private_hosts
    if private_hosts and host not in private_hosts:
        raise AdapterError(
            "This host is outside the connector profile allowlist.", "private_network"
        )
    if (
        not host
        or len(host) > 253
        or (host.endswith(".railway.internal") and host not in private_hosts)
        or host in {"169.254.169.254", "metadata.google.internal"}
    ):
        raise AdapterError(
            "Use a public database address or the scoped local connector.",
            "private_network",
        )
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise AdapterError(
            "The database hostname could not be resolved. Check the hostname and DNS.",
            "dns",
        ) from None
    local_test = os.environ.get("QOT_TEST_NETWORKS") == "1"
    for result in addresses:
        address = result[4][0]
        if address in {
            "169.254.169.254",
            "100.100.100.200",
            "192.0.0.192",
            "fd00:ec2::254",
        }:
            raise AdapterError(
                "Cloud metadata endpoints are forbidden.", "private_network"
            )
        if not public_address(address):
            allowed = host in private_hosts or (
                local_test and ipaddress.ip_address(address).is_loopback
            )
            if not allowed:
                raise AdapterError(
                    "Private, loopback and cloud metadata addresses require the local connector.",
                    "private_network",
                )
    return addresses


@contextmanager
def network_scope(private_hosts=()):
    context_token = _private_scope.set(private_hosts)
    original = socket.getaddrinfo

    def guarded(host, port, *args, **kwargs):
        if private_hosts and host not in private_hosts:
            raise AdapterError(
                "This host is outside the connector profile allowlist.",
                "private_network",
            )
        results = original(host, port, *args, **kwargs)
        test = os.environ.get("QOT_TEST_NETWORKS") == "1"
        for result in results:
            address = result[4][0]
            if address in {
                "169.254.169.254",
                "100.100.100.200",
                "192.0.0.192",
                "fd00:ec2::254",
            }:
                raise AdapterError(
                    "Cloud metadata endpoints are forbidden.", "private_network"
                )
            if not public_address(address):
                allowed = host in private_hosts or (
                    test and ipaddress.ip_address(address.split("%")[0]).is_loopback
                )
                if not allowed:
                    raise AdapterError(
                        "Blocked a private network address during connection.",
                        "private_network",
                    )
        return results

    socket.getaddrinfo = guarded
    try:
        yield
    finally:
        socket.getaddrinfo = original
        _private_scope.reset(context_token)


def relational_config(config, schemes, default_port):
    url = urlparse(config.get("url", ""))
    if url.scheme not in schemes or not url.hostname or not url.path.strip("/"):
        raise AdapterError(
            "Paste a connection URL with a hostname and database name.",
            "connection_format",
        )
    if url.port is not None and not 1024 <= url.port <= 65535:
        raise AdapterError(
            "Database ports below 1024 are not permitted.", "connection_format"
        )
    host = url.hostname
    local = (
        os.environ.get("QOT_TEST_NETWORKS") == "1"
        and not config.get("force_tls")
        and host
        in {
            "localhost",
            "127.0.0.1",
        }
    )
    local = local or (host in _private_scope.get() and config.get("tls") == "disable")
    if config.get("tls", "verify-full") != "verify-full" and not local:
        raise AdapterError("Public database connections require verified TLS.", "tls")
    validate_host(host, url.port or default_port)
    return url, local


def private_plaintext(host, config):
    return host in _private_scope.get() and config.get("tls") == "disable"
