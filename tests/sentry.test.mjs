import { test, after } from "node:test";
import assert from "node:assert/strict";
import * as Sentry from "@sentry/node";
import { proxyOptions } from "../api/monitoring.js";
import { proxy } from "../api/proxy.js";
import {
  sanitizeEvent,
  sanitizeSpan,
  traceHeaders,
  releaseName,
  sampleRate,
} from "../shared/telemetry.js";
import { buildSettings } from "../scripts/sentry-build.mjs";

const secret =
  "synthetic-secret-p@ss-Groq-OAuth-schema-PROMPT-SELECT-card-424242";
const trace = "a".repeat(32),
  parent = "b".repeat(16);
const env = {
  CONNECTOR_URL: "https://api-worker.example",
  SERVICE_TOKEN: secret,
};
const envelopes = [];
Sentry.init({
  ...proxyOptions({
    SENTRY_PROXY_DSN: "https://public@o0.ingest.sentry.io/1",
    SENTRY_ENVIRONMENT: "test",
    SENTRY_RELEASE: "c".repeat(40),
    SENTRY_TRACES_SAMPLE_RATE: "1",
  }),
  transport: () => ({
    send: async (envelope) => {
      envelopes.push(envelope);
      return { statusCode: 200 };
    },
    flush: async () => true,
  }),
});
after(async () => {
  await Sentry.close(100);
});
function payloads(type) {
  return envelopes.flatMap((e) =>
    e[1].filter((item) => item[0].type === type).map((item) => item[1]),
  );
}

test("privacy allowlist strips realistic content from errors, requests, breadcrumbs, frames, spans and debug metadata", () => {
  const event = sanitizeEvent({
    message: secret,
    logentry: { message: secret },
    request: {
      url: `https://host/${secret}?code=${secret}`,
      headers: { authorization: secret },
      data: secret,
    },
    user: { id: secret, email: secret },
    extra: { query: secret },
    tags: { operation: "generation", component: "proxy", secret },
    contexts: {
      trace: {
        trace_id: trace,
        span_id: parent,
        dynamic_sampling_context: { transaction: secret },
      },
      model: { prompt: secret },
    },
    exception: {
      values: [
        {
          type: secret,
          value: secret,
          stacktrace: {
            frames: [
              {
                filename: `https://${secret}/x.js`,
                function: secret,
                context_line: secret,
                vars: { password: secret },
                lineno: 4,
              },
              { filename: "C:/work/api/proxy.js", lineno: 80 },
            ],
          },
        },
      ],
    },
    breadcrumbs: [{ message: secret }],
  });
  assert.doesNotMatch(
    JSON.stringify(event),
    new RegExp(secret.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  );
  assert.equal(
    event.exception.values[0].stacktrace.frames[1].filename,
    "api/proxy.js",
  );
  assert.equal(
    sanitizeSpan({
      description: secret,
      data: { "db.statement": secret, prompt: secret },
    }).description,
    "/",
  );
});
test("minimal trace propagation rejects invalid IDs, oversized and foreign baggage", () => {
  assert.deepEqual(
    traceHeaders({ "sentry-trace": secret, baggage: secret }),
    {},
  );
  assert.deepEqual(
    traceHeaders({ "sentry-trace": `${"0".repeat(32)}-${parent}-1` }),
    {},
  );
  assert.deepEqual(
    traceHeaders({
      "sentry-trace": `${trace}-${parent}-1`,
      baggage: `sentry-trace_id=${trace},sentry-sampled=true,sentry-user_id=${secret},sentry-transaction=${secret},vendor=${secret}`,
    }),
    {
      "sentry-trace": `${trace}-${parent}-1`,
      baggage: `sentry-trace_id=${trace},sentry-sampled=true`,
    },
  );
});
test("proxy captures a swallowed failure once, flushes and preserves its response; traces continue to approved upstream only", async () => {
  const before = payloads("event").length;
  const response = await proxy(
    new Request("https://queryotter.example/api/session?code=" + secret, {
      headers: {
        "sentry-trace": `${trace}-${parent}-1`,
        baggage: `sentry-trace_id=${trace},sentry-user_id=${secret}`,
        cookie: secret,
      },
    }),
    env,
    async (url, options) => {
      assert.equal(url.origin, "https://api-worker.example");
      assert.match(
        options.headers.get("sentry-trace"),
        new RegExp(`^${trace}-[a-f0-9]{16}-1$`),
      );
      assert.doesNotMatch(
        options.headers.get("baggage") || "",
        /synthetic-secret/,
      );
      throw new Error(secret);
    },
  );
  assert.equal(response.status, 503);
  assert.equal(payloads("event").length - before, 1);
  assert.equal(payloads("event").at(-1).contexts.trace.trace_id, trace);
  assert.equal(payloads("transaction").at(-1).contexts.trace.trace_id, trace);
  assert.equal(
    payloads("event").at(-1).release,
    "queryotter@" + "c".repeat(40),
  );
  assert.equal(JSON.stringify(envelopes).includes(secret), false);
});
test("concurrent proxy requests keep traces and user scopes isolated", async () => {
  const ids = ["d".repeat(32), "e".repeat(32)];
  const before = payloads("event").length;
  await Promise.all(
    ids.map((id) =>
      proxy(
        new Request("https://queryotter.example/api/assistant/jobs", {
          headers: { "sentry-trace": `${id}-${parent}-1` },
        }),
        env,
        async () => {
          await new Promise((resolve) => setTimeout(resolve, 10));
          throw new TypeError(secret);
        },
      ),
    ),
  );
  assert.deepEqual(
    new Set(
      payloads("event")
        .slice(before)
        .map((e) => e.contexts.trace.trace_id),
    ),
    new Set(ids),
  );
  assert.ok(
    payloads("event")
      .slice(before)
      .every((e) => !e.user),
  );
});
test("proxy timeouts are reported while expected validation/auth failures do not alert", async () => {
  const before = payloads("event").length;
  assert.equal(
    (
      await proxy(
        new Request("https://queryotter.example/api/session"),
        env,
        async () => {
          throw new DOMException(secret, "TimeoutError");
        },
      )
    ).status,
    503,
  );
  assert.equal(payloads("event").length - before, 1);
  await proxy(new Request("https://queryotter.example/api/forbidden"), env);
  await proxy(
    new Request("https://queryotter.example/api/session"),
    env,
    async () => new Response("{}", { status: 401 }),
  );
  assert.equal(payloads("event").length - before, 1);
});
test("configured builds fail closed without upload credentials or exact CSP origin", () => {
  assert.equal(buildSettings({}, "build").enabled, false);
  assert.throws(
    () => buildSettings({ VITE_SENTRY_AUTH_TOKEN: secret }, "build"),
    /Build secrets/,
  );
  assert.throws(
    () =>
      buildSettings(
        { VITE_SENTRY_DSN: "https://key@o0.ingest.sentry.io/1" },
        "build",
      ),
    /require/,
  );
  assert.throws(
    () =>
      buildSettings(
        {
          VITE_SENTRY_DSN: "https://key@o0.ingest.sentry.io/1",
          SENTRY_RELEASE: "c".repeat(40),
          SENTRY_AUTH_TOKEN: secret,
          SENTRY_ORG: "test",
          SENTRY_PROJECT: "test",
        },
        "build",
      ),
    /exact browser DSN/,
  );
  assert.equal(releaseName(secret), undefined);
  assert.equal(sampleRate("NaN"), 0.1);
  assert.equal(sampleRate("0"), 0);
});
