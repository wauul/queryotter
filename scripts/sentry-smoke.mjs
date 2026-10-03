import * as Sentry from "@sentry/node";
import { proxyOptions } from "../api/monitoring.js";
import { proxy } from "../api/proxy.js";
const send = process.argv.includes("--send");
if (send && !process.env.SENTRY_PROXY_DSN)
  throw new Error("SENTRY_PROXY_DSN is required for --send.");
const envelopes = [];
let eventId;
const options = proxyOptions(
  send
    ? process.env
    : {
        SENTRY_PROXY_DSN: "https://public@o0.ingest.sentry.io/1",
        SENTRY_ENVIRONMENT: "test",
        SENTRY_TRACES_SAMPLE_RATE: "1",
      },
);
Sentry.init({
  ...options,
  beforeSend: (event, hint) => {
    const sanitized = options.beforeSend(event, hint);
    eventId = sanitized.event_id;
    return sanitized;
  },
  ...(!send
    ? {
        transport: () => ({
          send: async (envelope) => {
            envelopes.push(envelope);
            return { statusCode: 200 };
          },
          flush: async () => true,
        }),
      }
    : {}),
});
const response = await proxy(
  new Request("https://queryotter.invalid/api/session"),
  {
    CONNECTOR_URL: "https://approved.invalid",
    SERVICE_TOKEN: "synthetic-service-token",
  },
  () => {
    throw new Error("QueryOtter synthetic proxy smoke");
  },
);
const delivered = await Sentry.flush(1500);
console.log(
  JSON.stringify({
    component: "proxy",
    status: response.status,
    event_id: eventId,
    local_envelopes: send ? undefined : envelopes.length,
    sdk_flushed: delivered,
    ingestion_verified: false,
  }),
);
await Sentry.close(100);
