import { defineRailway, project, service } from "railway/iac";

export const partial = "api-worker";

export default defineRailway(() => {
  const api_worker = service("api-worker", {
    healthcheck: "/healthz",
    healthcheckTimeout: 90,
    replicas: 1,
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    deploy: {
      region: "europe-west4-drams3a",
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
