import { defineRailway, preserve, project, service } from "railway/iac";

export const partial = "api-worker";

export default defineRailway(() => {
  const api_worker = service("api-worker", {
    healthcheck: "/healthz",
    healthcheckTimeout: 90,
    replicas: 1,
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    env: Object.fromEntries([
      "ADMIN_PASSWORD", "DEMO_DAILY_LIMIT", "ENCRYPTION_KEY",
      "EXPERIMENT_DATABASE_URL", "JOB_DATABASE_URL", "JOB_SECONDS",
      "MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME", "MODEL_PROVIDER",
      "PORT", "SERVICE_TOKEN", "SESSION_SECRET",
      "SENTRY_PYTHON_DSN", "SENTRY_RELEASE", "SENTRY_ENVIRONMENT", "SENTRY_TRACES_SAMPLE_RATE",
      "QOT_LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
      "LANGFUSE_BASE_URL", "LANGFUSE_TRACING_ENVIRONMENT",
    ].map((key) => [key, preserve()])),
    deploy: {
      region: "europe-west4-drams3a",
      multiRegionConfig: { "europe-west4-drams3a": { numReplicas: 1 } },
      sleepApplication: true,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
      limitOverride: { containers: { cpu: 0.5, memoryBytes: 536870912 } },
    },
  });
  return project("queryotter", {
    resources: [api_worker],
  });
});
