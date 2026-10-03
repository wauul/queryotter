// Explicit instrumentation needs no Node preload/ESM loader. We deliberately do
// not install automatic HTTP, DB, console or model integrations on this proxy.
import * as Sentry from "@sentry/node";
import {
  sanitizeEvent,
  sanitizeSpan,
  traceHeaders,
  routeName,
  sampleRate,
  releaseName,
  environmentName,
} from "./telemetry.js";

export function proxyOptions(env = process.env) {
  return {
    dsn: env.SENTRY_PROXY_DSN,
    release: releaseName(env.SENTRY_RELEASE || env.VERCEL_GIT_COMMIT_SHA),
    environment: environmentName(env.SENTRY_ENVIRONMENT || env.VERCEL_ENV),
    initialScope: { tags: { component: "proxy" } },
    sendDefaultPii: false,
    defaultIntegrations: false,
    integrations: [],
    enableLogs: false,
    enableMetrics: false,
    traceLifecycle: "static",
    maxBreadcrumbs: 0,
    sendClientReports: false,
    tracesSampleRate: sampleRate(env.SENTRY_TRACES_SAMPLE_RATE),
    beforeSend: sanitizeEvent,
    beforeSendTransaction: sanitizeEvent,
    beforeSendSpan: sanitizeSpan,
    beforeBreadcrumb: () => null,
  };
}
if (process.env.SENTRY_PROXY_DSN) {
  try {
    Sentry.init(proxyOptions());
  } catch {
    /* Monitoring cannot take the proxy offline. */
  }
}
export function captureProxy(error) {
  try {
    Sentry.captureException(error);
  } catch {
    /* best effort */
  }
}
export function upstreamTraceHeaders(incoming) {
  try {
    return traceHeaders(
      Sentry.isEnabled() ? Sentry.getTraceData() : traceHeaders(incoming),
    );
  } catch {
    return traceHeaders(incoming);
  }
}
export async function monitoredProxy(request, work) {
  if (!Sentry.isEnabled()) return work();
  let pending;
  const run = () => (pending ??= Promise.resolve().then(work));
  try {
    return await Sentry.withIsolationScope((scope) => {
      scope.setUser(null);
      scope.setTag("component", "proxy");
      const incoming = traceHeaders(request.headers);
      return Sentry.continueTrace(
        { sentryTrace: incoming["sentry-trace"], baggage: incoming.baggage },
        () =>
          Sentry.startSpan(
            { name: routeName(request.url), op: "http.server" },
            async (span) => {
              try {
                const response = await run();
                try {
                  Sentry.setHttpStatus(span, response.status);
                } catch {
                  /* best effort */
                }
                return response;
              } catch (error) {
                captureProxy(error);
                throw error;
              }
            },
          ),
      );
    });
  } catch {
    // SDK setup/span failures cannot skip or repeat the actual proxy operation.
    // A rejected work promise still preserves the application's original error.
    return pending ? await pending : work();
  } finally {
    try {
      await Sentry.flush(1500);
    } catch {
      /* bounded best effort */
    }
  }
}
