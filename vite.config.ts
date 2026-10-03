import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { sentryVitePlugin } from "@sentry/vite-plugin";
import { buildSettings, removeMaps } from "./scripts/sentry-build.mjs";
export default defineConfig(({ mode, command }) => {
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env };
  const token = env.SERVICE_TOKEN;
  const monitoring = buildSettings(env, command);
  return {
    define: {
      "import.meta.env.VITE_SENTRY_RELEASE": JSON.stringify(
        monitoring.release || "",
      ),
      "import.meta.env.VITE_SENTRY_ENVIRONMENT": JSON.stringify(
        env.SENTRY_ENVIRONMENT || env.VERCEL_ENV || "development",
      ),
    },
    build: { sourcemap: monitoring.enabled ? "hidden" : false },
    plugins: [
      react(),
      ...(monitoring.enabled && command === "build"
        ? [
            sentryVitePlugin({
              org: env.SENTRY_ORG,
              project: env.SENTRY_PROJECT,
              authToken: env.SENTRY_AUTH_TOKEN,
              telemetry: false,
              release: {
                name: monitoring.release,
                create: true,
                finalize: true,
              },
              sourcemaps: {
                assets: "./dist/**",
                filesToDeleteAfterUpload: ["./dist/**/*.map"],
              },
              // No errorHandler: SDK plugin upload failures fail the release build.
            }),
            {
              name: "queryotter-private-maps",
              enforce: "post" as const,
              closeBundle: {
                order: "post" as const,
                handler: () => removeMaps(),
              },
            },
          ]
        : []),
    ],
    server: {
      proxy: {
        "/api": {
          target: process.env.QOT_DEV_API_URL || "http://127.0.0.1:8000",
          headers: {
            "x-service-token": token || "",
            "x-app-origin":
              process.env.QOT_DEV_ORIGIN || "http://127.0.0.1:5173",
          },
        },
      },
    },
  };
});
