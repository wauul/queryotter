# Private and local database access

Cloud deployments cannot reach your localhost. This optional connector polls QueryOtter over outbound HTTPS and opens only explicitly configured database profiles. It exposes no inbound port and provides no general HTTP proxy.

1. Clone this repository on a trusted machine that can reach the database. Install Python 3.12+ and uv; run `uv sync --locked --no-dev`.
2. Create a dedicated read-only database login using the engine connection guide.
3. Create a connector in workspace settings. Store its token, shown once, outside source control on this machine.
4. Create a private profile JSON file:

```json
{
  "local-shop": {
    "engine": "postgresql",
    "allowed_hosts": ["127.0.0.1"],
    "config": {
      "url": "postgresql://shop_reader:YOUR_PASSWORD@127.0.0.1:5432/shop",
      "schema": "public",
      "tls": "verify-full",
      "ca_certificate": "YOUR_PEM_CA_CERTIFICATE"
    }
  }
}
```

5. Set `QOT_CONNECTOR_ORIGIN=https://queryotter.vercel.app`, `QOT_CONNECTOR_ID` and `QOT_CONNECTOR_TOKEN` in this machine's environment. Run `uv run python scripts/local-connector.py --profiles /absolute/path/profiles.json`.
6. Add a QueryOtter connection using this connector and the exact profile name. Credentials remain on the connector machine. Test discovery, generate a query, review it, and select Run.

Tokens are hashed, workspace-scoped, and revoked by removing the connector. Task requests and responses are encrypted in the queue, expire after 20 seconds, and are removed after delivery or cancellation. Database operations retain engine timeouts and bounded results. Cancellation rejects late responses; local work ends at its next checkpoint or engine timeout, normally within 8 seconds. Experimental indexes are never created through this connector.

Use verified TLS on networks you do not fully trust. A private profile can explicitly select `tls: "disable"` for a development database on its trusted network. This exception works only inside an explicit connector host allowlist; direct cloud connections require verified TLS. Cloud metadata endpoints are forbidden even in an allowlist. Protect the profile file and environment, run as a low-privilege OS user, and keep the connector updated. Every cluster member or redirected database host must be explicitly allowed. SQLite uploads do not require a connector.
