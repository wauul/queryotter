import "./instrument";
import React from "react";
import { reactErrorHandler } from "@sentry/react";
import { createRoot } from "react-dom/client";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/react";
import Studio from "./Studio";
import { ThemeProvider } from "./Theme";
import { LanguageProvider } from "./Language";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "./style.css";
import "./studio.css";
import { MonitoringBoundary } from "./MonitoringBoundary";

// Page URLs must not include OAuth parameters or other private URL state.
function sanitizePageUrl<T extends { url: string }>(event: T): T | null {
  try {
    const url = new URL(event.url);
    return { ...event, url: url.origin + url.pathname };
  } catch {
    return null;
  }
}

createRoot(document.getElementById("root")!, {
  onUncaughtError: reactErrorHandler(),
  onRecoverableError: reactErrorHandler(),
  // Caught render errors are reported once by MonitoringBoundary.
}).render(
  <React.StrictMode>
    <LanguageProvider>
      <ThemeProvider>
        <MonitoringBoundary>
          <Studio />
        </MonitoringBoundary>
      </ThemeProvider>
    </LanguageProvider>
    <Analytics beforeSend={sanitizePageUrl} />
    <SpeedInsights beforeSend={sanitizePageUrl} />
  </React.StrictMode>,
);
