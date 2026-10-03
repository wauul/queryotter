// Operator verification only. Adds trace metadata in one isolated browser page,
// runs a synthetic SQLite discovery job, then deletes only its own demo account.
import { chromium } from "@playwright/test";
import { randomBytes } from "node:crypto";
const origin = "https://queryotter.vercel.app";
const trace = randomBytes(16).toString("hex");
const parent = randomBytes(8).toString("hex");
const requests = [];
const browser = await chromium.launch({ headless: true });
let page,
  created = false;
try {
  page = await browser.newPage();
  page.on("request", (request) => {
    if (request.url().startsWith(origin + "/api/"))
      requests.push({
        path: new URL(request.url()).pathname.replace(/[a-f0-9]{32}/g, ":id"),
        trace: request.headers()["sentry-trace"],
      });
  });
  await page.route(origin + "/", async (route) => {
    const response = await route.fetch();
    const html = (await response.text()).replace(
      "<head>",
      `<head><meta name="sentry-trace" content="${trace}-${parent}-1"><meta name="baggage" content="sentry-trace_id=${trace},sentry-sampled=true,sentry-sample_rate=1">`,
    );
    await route.fulfill({ response, body: html });
  });
  await page.goto(origin, { waitUntil: "domcontentloaded" });
  await page.evaluate(async () => {
    const initial = await (await fetch("/api/assistant/session")).json();
    if (initial.user)
      throw new Error("Refusing to operate on an existing account");
    const response = await fetch("/api/assistant/demo/start", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    });
    if (!response.ok)
      throw new Error("Synthetic demo creation failed: " + response.status);
  });
  created = true;
  const result = await page.evaluate(async () => {
    async function api(path, body) {
      const response = await fetch("/api/assistant/" + path, {
        method: body === undefined ? "GET" : "POST",
        headers:
          body === undefined ? {} : { "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok)
        throw new Error("Synthetic request failed: " + response.status);
      return response.json();
    }
    const connection = await api("connections/demo", {});
    const job = await api("jobs", {
      connection_id: connection.id,
      action: "discover",
      request_key: crypto.randomUUID(),
    });
    return { job_id: job.id, connection_id: connection.id };
  });
  let job;
  for (let count = 0; count < 90; count++) {
    job = await page.evaluate(
      async (id) => (await fetch("/api/assistant/jobs/" + id)).json(),
      result.job_id,
    );
    if (!["queued", "running"].includes(job.state)) break;
    await page.waitForTimeout(1000);
  }
  if (job.state !== "completed")
    throw new Error("Synthetic discovery did not complete: " + job.state);
  await page.waitForTimeout(2000);
  console.log(
    JSON.stringify({
      trace_id: trace,
      job_id: result.job_id,
      state: job.state,
      browser_requests: requests,
      sentry_verified: false,
    }),
  );
} finally {
  try {
    if (created)
      await page.evaluate(async () => {
        const response = await fetch("/api/assistant/account/delete", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ confirmation: "DELETE" }),
        });
        if (!response.ok)
          throw new Error(
            "Synthetic account cleanup failed: " + response.status,
          );
      });
  } finally {
    await browser.close();
  }
}
