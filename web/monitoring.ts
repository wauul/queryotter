import * as Sentry from "@sentry/react";
import {
  sanitizeEvent,
  sanitizeSpan,
  sampleRate,
  releaseName,
  environmentName,
  routeName,
} from "../shared/telemetry.js";

const env = import.meta.env;
const ignored = new WeakSet<object>();
const delivered = new WeakSet<object>();
export function initMonitoring() {
  if (!env.VITE_SENTRY_DSN) return;
  try {
    Sentry.init({
      dsn: env.VITE_SENTRY_DSN,
      release: releaseName(env.VITE_SENTRY_RELEASE),
      environment: environmentName(env.VITE_SENTRY_ENVIRONMENT),
      initialScope: { tags: { component: "frontend" } },
      sendDefaultPii: false,
      enableLogs: false,
      enableMetrics: false,
      traceLifecycle: "static",
      maxBreadcrumbs: 0,
      sendClientReports: false,
      // No replay, console, DOM breadcrumbs, linked error data or network bodies.
      integrations: [
        Sentry.globalHandlersIntegration(),
        Sentry.browserApiErrorsIntegration(),
        Sentry.dedupeIntegration(),
        Sentry.browserTracingIntegration({
          beforeStartSpan: (options) => ({
            ...options,
            name: routeName(options.name),
          }),
        }),
      ],
      defaultIntegrations: false,
      tracesSampleRate: sampleRate(env.VITE_SENTRY_TRACES_SAMPLE_RATE),
      tracePropagationTargets: [
        /^\/api\//,
        new RegExp(
          "^" +
            location.origin.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") +
            "/api/",
        ),
      ],
      beforeSend: (event, hint) => {
        const error = hint.originalException;
        if (typeof error === "object" && error !== null) {
          if (ignored.has(error) || delivered.has(error)) return null;
          delivered.add(error);
        }
        return sanitizeEvent(event, hint);
      },
      beforeSendTransaction: sanitizeEvent,
      beforeSendSpan: sanitizeSpan,
      beforeBreadcrumb: () => null,
    });
  } catch {
    /* Optional monitoring must not prevent rendering. */
  }
}
// Authentication state is deliberately not attached: clearing on every transition
// also clears accidental identity context introduced by other integrations.
export function clearMonitoringUser() {
  Sentry.setUser(null);
}
const seen = new WeakSet<object>();
export function captureHandled(error: unknown, operation = "request") {
  if (typeof error === "object" && error !== null) {
    if (seen.has(error)) return;
    seen.add(error);
  }
  try {
    Sentry.withScope((scope) => {
      scope.setTag("operation", operation);
      Sentry.captureException(error);
    });
  } catch {
    /* best effort */
  }
}
// Centralized handled capture: only network, malformed responses and 5xx errors
// alert. Expected user/validation/authentication failures retain their UI behavior.
export async function monitoredFetch(path: string, body?: unknown) {
  try {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Please check your input and try again.",
      );
      if (response.status >= 500) captureHandled(error);
      else ignored.add(error);
      // Mark expected and already captured errors before passing them to handlers.
      seen.add(error);
      throw error;
    }
    return data;
  } catch (error) {
    if (!(error instanceof DOMException && error.name === "AbortError"))
      captureHandled(error);
    throw error;
  }
}
export { routeName };
