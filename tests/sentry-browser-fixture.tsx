// Served only by the development test server; not imported into production.
import {
  initMonitoring,
  captureHandled,
  monitoredFetch,
  clearMonitoringUser,
} from "../web/monitoring";
import * as Sentry from "@sentry/react";
import React from "react";
import { createRoot } from "react-dom/client";
import { MonitoringBoundary } from "../web/MonitoringBoundary";
import { LanguageProvider } from "../web/Language";
document.documentElement.lang =
  new URL(location.href).searchParams.get("lang") || "en";
initMonitoring();
const root = createRoot(document.getElementById("root")!, {
  onUncaughtError: Sentry.reactErrorHandler(),
});
function Broken() {
  throw new Error("synthetic-render-secret-PROMPT-SELECT-private_schema");
  return null;
}
const render = (broken: boolean) =>
  root.render(
    <LanguageProvider>
      <MonitoringBoundary>
        {broken ? <Broken /> : <p>Ready</p>}
      </MonitoringBoundary>
    </LanguageProvider>,
  );
render(false);
(window as any).smoke = {
  handled: () => {
    const error = new Error("synthetic-handled-secret-Groq-OAuth");
    captureHandled(error);
    captureHandled(error);
    Sentry.captureException(error);
  },
  uncaught: () =>
    setTimeout(() => {
      throw new Error("synthetic-uncaught-secret-password");
    }, 0),
  rejection: () => {
    void Promise.reject(new Error("synthetic-rejection-secret-model-output"));
  },
  request: (path: string) => monitoredFetch(path).catch(() => {}),
  renderBroken: () => render(true),
  clearUser: () => {
    Sentry.setUser({ id: "a".repeat(32), email: "synthetic-user-secret" });
    clearMonitoringUser();
    return Sentry.getCurrentScope().getUser();
  },
  flush: () => Sentry.flush(1500),
};
