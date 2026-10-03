import * as Sentry from "@sentry/react";
import { useLanguage } from "./Language";
import type { ReactNode } from "react";
function Fallback() {
  const { t } = useLanguage();
  return (
    <main className="q-prose" role="alert">
      <h1>{t("Something went wrong")}</h1>
      <p>
        {t(
          "Reload QueryOtter to continue. Your saved workspace is still available. Unsaved edits may need to be entered again.",
        )}
      </p>
      <button className="q-button" onClick={() => location.reload()}>
        {t("Reload QueryOtter")}
      </button>
    </main>
  );
}
export function MonitoringBoundary({ children }: { children: ReactNode }) {
  return (
    <Sentry.ErrorBoundary fallback={<Fallback />}>
      {children}
    </Sentry.ErrorBoundary>
  );
}
