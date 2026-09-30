import { test } from "node:test";
import assert from "node:assert/strict";
import { proxy } from "../api/proxy.js";

const env = {
  CONNECTOR_URL: "https://connector.example",
  SERVICE_TOKEN: "server-secret",
};
const base = "https://queryotter.example";

test("preserves session and export while replacing caller service headers", async () => {
  let forwarded;
  const request = new Request(`${base}/api/jobs/${"a".repeat(32)}/report`, {
    headers: {
      cookie: "qot_session=signed",
      "x-service-token": "attacker",
      "x-app-origin": "https://attacker.example",
      authorization: "untrusted",
    },
  });
  const response = await proxy(request, env, async (url, options) => {
    forwarded = { url, ...options };
    return new Response('{"ok":true}', {
      headers: {
        "content-type": "application/json",
        "set-cookie": "qot_session=renewed; Secure; HttpOnly",
        "content-disposition": "attachment; filename=report.json",
        server: "private",
      },
    });
  });
  assert.equal(
    forwarded.url.href,
    `https://connector.example/api/jobs/${"a".repeat(32)}/report`,
  );
  assert.equal(forwarded.headers.get("x-service-token"), "server-secret");
  assert.equal(forwarded.headers.get("x-app-origin"), base);
  assert.equal(forwarded.headers.get("x-forwarded-proto"), "https");
  assert.equal(forwarded.headers.get("cookie"), "qot_session=signed");
  assert.equal(forwarded.headers.has("authorization"), false);
  assert.equal(response.headers.has("server"), false);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.match(response.headers.get("set-cookie"), /Secure; HttpOnly/);
  assert.match(response.headers.get("content-disposition"), /attachment/);
  assert.deepEqual(await response.json(), { ok: true });
});

test("blocks cross-origin writes, unknown routes, methods and oversized streamed bodies", async () => {
  const never = () => {
    throw new Error("Must not forward");
  };
  assert.equal(
    (
      await proxy(
        new Request(`${base}/api/jobs`, {
          method: "POST",
          headers: { origin: "https://attacker.example" },
        }),
        env,
        never,
      )
    ).status,
    403,
  );
  assert.equal(
    (await proxy(new Request(`${base}/api/jobs/../../admin`), env, never))
      .status,
    404,
  );
  assert.equal(
    (
      await proxy(
        new Request(`${base}/api/jobs`, { method: "DELETE" }),
        env,
        never,
      )
    ).status,
    405,
  );
  assert.equal(
    (
      await proxy(
        new Request(`${base}/api/jobs`, {
          method: "POST",
          body: "é".repeat(9001),
        }),
        env,
        never,
      )
    ).status,
    413,
  );
});

test("forwards same-origin JSON without following redirects or leaking failures", async () => {
  const response = await proxy(
    new Request(`${base}/api/jobs`, {
      method: "POST",
      headers: { origin: base, "content-type": "application/json" },
      body: '{"case_id":"customer-orders"}',
    }),
    env,
    async (_, options) => {
      assert.equal(
        new TextDecoder().decode(options.body),
        '{"case_id":"customer-orders"}',
      );
      assert.equal(options.redirect, "manual");
      return new Response(null, {
        status: 302,
        headers: { location: "https://attacker.example" },
      });
    },
  );
  assert.equal(response.status, 502);
  assert.equal(response.headers.has("location"), false);
  const failed = await proxy(new Request(`${base}/api/session`), env, () => {
    throw new Error("server-secret");
  });
  assert.equal(failed.status, 503);
  assert.doesNotMatch(await failed.text(), /server-secret/);
  assert.equal(
    (await proxy(new Request(`${base}/api/session`), {})).status,
    503,
  );
});

test("OAuth callbacks preserve code/state and both session cookies", async () => {
  const response = await proxy(new Request(`${base}/api/assistant/auth/github/callback?code=code&state=state`), env, async (url) => {
    assert.equal(url.search, "?code=code&state=state");
    const headers = new Headers({"content-type": "text/html", "referrer-policy": "no-referrer"});
    headers.append("set-cookie", "qot_auth=session; HttpOnly; Secure; SameSite=Lax");
    headers.append("set-cookie", "qot_oauth_browser=; Max-Age=0; HttpOnly; Secure");
    return new Response("Signing in", {headers});
  });
  assert.equal(response.headers.getSetCookie().length, 2);
  assert.equal(response.headers.get("referrer-policy"), "no-referrer");
});
