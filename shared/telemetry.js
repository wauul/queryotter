// Reconstruct telemetry from an allowlist. Redaction by secret-pattern is insufficient
// for prompts, identifiers, query text and arbitrary provider error messages.
export const operations = new Set([
  "request",
  "job",
  "generation",
  "discovery",
  "execution",
  "benchmark",
  "supervision",
  "smoke",
  "validation",
  "optimization",
  "connection",
]);
const components = new Set([
  "frontend",
  "proxy",
  "api",
  "worker",
  "supervisor",
]);
const errorTypes = new Set([
  "Error",
  "TypeError",
  "RangeError",
  "SyntaxError",
  "ReferenceError",
  "TimeoutError",
  "AbortError",
]);
const files = new Set([
  "web/main.tsx",
  "web/Studio.tsx",
  "web/StudioConnection.tsx",
  "web/LegacyOptimizer.tsx",
  "web/studio-api.ts",
  "web/monitoring.ts",
  "web/MonitoringBoundary.tsx",
  "api/proxy.js",
  "api/monitoring.js",
  "scripts/sentry-smoke.mjs",
]);
const hex = (value, size) =>
  typeof value === "string" && new RegExp(`^[a-f0-9]{${size}}$`).test(value);
export function sampleRate(value, fallback = 0.1) {
  if (value === undefined || value === "") return fallback;
  const rate = Number(value);
  return Number.isFinite(rate) && rate >= 0 && rate <= 1 ? rate : fallback;
}
export function releaseName(value) {
  return /^(?:queryotter@)?[a-f0-9]{40}$/.test(value || "")
    ? `queryotter@${value.replace("queryotter@", "")}`
    : undefined;
}
export function environmentName(value) {
  return ["production", "preview", "staging", "development", "test"].includes(
    value,
  )
    ? value
    : "development";
}
export function routeName(value) {
  try {
    const path = new URL(value, "https://queryotter.invalid").pathname;
    const normalized = path.replace(/[a-f0-9]{32}/g, ":id");
    const segments = new Set([
      "api",
      "assistant",
      "session",
      "health",
      "healthz",
      "login",
      "logout",
      "examples",
      "jobs",
      "cancel",
      "report",
      "connections",
      "reports",
      "catalog",
      "settings",
      "parse-connection",
      "demo",
      "start",
      "auth",
      "github",
      "google",
      "microsoft",
      "callback",
      "owner",
      "remove",
      "rotate",
      "prisma",
      "schema",
      "results",
      "export",
      "history",
      "clear",
      "saved",
      "account",
      "delete",
      "connectors",
      "poll",
      "complete",
      ":id",
    ]);
    return normalized.startsWith("/api/") &&
      normalized
        .split("/")
        .filter(Boolean)
        .every((s) => segments.has(s))
      ? normalized
      : "/";
  } catch {
    return "/";
  }
}
export function traceHeaders(headers) {
  const get = (key) => (headers?.get ? headers.get(key) : headers?.[key]);
  const trace = get("sentry-trace");
  if (
    typeof trace !== "string" ||
    !/^[a-f0-9]{32}-[a-f0-9]{16}(?:-[01])?$/.test(trace) ||
    /^0{32}-|^[a-f0-9]{32}-0{16}/.test(trace)
  )
    return {};
  // Never forward third-party baggage, release names, user IDs or arbitrary DSC.
  const baggage = get("baggage");
  const allowed = [];
  if (typeof baggage === "string" && baggage.length <= 2048) {
    const patterns = {
      "sentry-trace_id": /^[a-f0-9]{32}$/,
      "sentry-sampled": /^(true|false)$/,
      "sentry-sample_rate": /^(0(?:\.\d{1,8})?|1(?:\.0{1,8})?)$/,
    };
    for (const [key, pattern] of Object.entries(patterns)) {
      const entry = baggage
        .split(",")
        .map((x) => x.trim())
        .find((x) => x.startsWith(key + "="));
      const value = entry?.slice(key.length + 1);
      if (
        value &&
        pattern.test(value) &&
        (key !== "sentry-trace_id" || value === trace.slice(0, 32))
      )
        allowed.push(`${key}=${value}`);
    }
  }
  return {
    "sentry-trace": trace,
    ...(allowed.length ? { baggage: allowed.join(",") } : {}),
  };
}
function codeFile(value) {
  if (typeof value !== "string") return undefined;
  const path = value.split(/[?#]/)[0].replaceAll("\\", "/");
  for (const file of files)
    if (path === file || path.endsWith("/" + file)) return file;
  const asset = path.match(/(?:^|\/)assets\/(index-[a-zA-Z0-9_-]{8}\.js)$/);
  if (asset) {
    return "~/assets/" + asset[1];
  }
  return undefined;
}
function frames(stack) {
  return {
    frames: (stack?.frames || []).map((frame) => {
      const filename = codeFile(frame.filename || frame.abs_path);
      return {
        ...(filename ? { filename } : {}),
        ...(Number.isInteger(frame.lineno) ? { lineno: frame.lineno } : {}),
        ...(Number.isInteger(frame.colno) ? { colno: frame.colno } : {}),
        in_app: !!filename,
      };
    }),
  };
}
function traceContext(context) {
  const out = {};
  for (const key of ["trace_id", "span_id", "parent_span_id"])
    if (hex(context?.[key], key === "trace_id" ? 32 : 16))
      out[key] = context[key];
  if (
    [
      "ok",
      "internal_error",
      "cancelled",
      "deadline_exceeded",
      "unknown_error",
    ].includes(context?.status)
  )
    out.status = context.status;
  return out;
}
export function sanitizeSpan(span) {
  const out = traceContext(span);
  for (const key of ["start_timestamp", "timestamp"])
    if (Number.isFinite(span[key])) out[key] = span[key];
  out.op = [
    "http.server",
    "http.client",
    "pageload",
    "navigation",
    "queue.process",
    "queryotter.operation",
  ].includes(span.op)
    ? span.op
    : "queryotter.operation";
  out.description = operations.has(span.description)
    ? span.description
    : routeName(span.description);
  out.data = {};
  const data = span.data || {};
  if (
    Number.isInteger(data["http.response.status_code"]) &&
    data["http.response.status_code"] >= 100 &&
    data["http.response.status_code"] <= 599
  )
    out.data["http.response.status_code"] = data["http.response.status_code"];
  if (operations.has(data.operation)) out.data.operation = data.operation;
  if (
    [
      "postgresql",
      "sqlite",
      "mysql",
      "mariadb",
      "sqlserver",
      "cockroachdb",
      "mongodb",
      "firestore",
      "realtime",
      "libsql",
    ].includes(data.engine)
  )
    out.data.engine = data.engine;
  return out;
}
export function sanitizeEvent(event, hint) {
  if (hint) delete hint.attachments;
  const out = {};
  for (const key of [
    "event_id",
    "type",
    "platform",
    "level",
    "timestamp",
    "start_timestamp",
  ]) {
    if (
      key === "event_id"
        ? hex(event[key], 32)
        : ["type", "platform", "level"].includes(key)
          ? [
              "transaction",
              "javascript",
              "node",
              "error",
              "warning",
              "info",
            ].includes(event[key])
          : Number.isFinite(event[key])
    )
      out[key] = event[key];
  }
  const release = releaseName(event.release);
  if (release) out.release = release;
  out.environment = environmentName(event.environment);
  out.tags = {};
  if (components.has(event.tags?.component))
    out.tags.component = event.tags.component;
  if (operations.has(event.tags?.operation))
    out.tags.operation = event.tags.operation;
  if (hex(event.user?.id, 32)) out.user = { id: event.user.id };
  out.contexts = { trace: traceContext(event.contexts?.trace) };
  if (event.exception)
    out.exception = {
      values: (event.exception.values || []).map((value) => ({
        type: errorTypes.has(value.type) ? value.type : "Error",
        value: "[redacted]",
        stacktrace: frames(value.stacktrace),
        mechanism: {
          type: "generic",
          handled: value.mechanism?.handled !== false,
        },
      })),
    };
  if (event.type === "transaction") {
    out.transaction = operations.has(event.transaction)
      ? event.transaction
      : routeName(event.transaction);
    out.transaction_info = { source: "route" };
    out.spans = (event.spans || []).map(sanitizeSpan);
  }
  if (event.debug_meta?.images)
    out.debug_meta = {
      images: event.debug_meta.images.flatMap((image) => {
        const code_file = codeFile(image.code_file);
        return code_file && /^[a-f0-9-]{36}$/.test(image.debug_id || "")
          ? [{ type: "sourcemap", code_file, debug_id: image.debug_id }]
          : [];
      }),
    };
  return out;
}
