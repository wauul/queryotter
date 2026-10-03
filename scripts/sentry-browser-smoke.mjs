// Operator-only local check of the real production bundle. No crash hook ships.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { resolve, extname, sep } from "node:path";
import { chromium } from "@playwright/test";

if (!process.argv.includes("--send"))
  throw new Error(
    "Use --send to explicitly send synthetic telemetry from dist to Sentry.",
  );
const directory = resolve("dist");
const envelopes = [];
const receipts = [];
const server = createServer((request, response) => {
  try {
    const path = new URL(request.url, "http://localhost").pathname;
    const file = resolve(
      directory,
      "." + (path === "/" ? "/index.html" : path),
    );
    if (!file.startsWith(directory + sep)) throw new Error("Invalid path");
    const types = {
      ".js": "application/javascript",
      ".css": "text/css",
      ".html": "text/html",
    };
    response.setHeader(
      "content-type",
      types[extname(file)] || "application/octet-stream",
    );
    response.end(readFileSync(file));
  } catch {
    response.writeHead(404);
    response.end();
  }
});
let browser;
try {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on("response", (response) => {
    if (response.url().includes(".ingest.de.sentry.io/"))
      receipts.push(response.status());
  });
  page.on("requestfailed", (request) => {
    if (request.url().includes(".ingest.de.sentry.io/"))
      receipts.push(request.failure()?.errorText);
  });
  page.on("request", (request) => {
    if (request.url().includes(".ingest.de.sentry.io/") && request.postData())
      envelopes.push(request.postData());
  });
  // Only the synthetic local API is broken. Sentry requests use real transport.
  const urlIndex = process.argv.indexOf("--url");
  const origin =
    urlIndex >= 0
      ? new URL(process.argv[urlIndex + 1]).origin
      : `http://127.0.0.1:${server.address().port}`;
  await page.route(`${origin}/api/**`, (route) => route.abort("failed"));
  await page.goto(origin + "/");
  await page.getByText("Failed to fetch", { exact: true }).waitFor();
  // Receipt is independently verified in the authenticated Sentry UI.
  await page.waitForTimeout(5000);
  const events = envelopes
    .flatMap((envelope) =>
      envelope
        .split("\n")
        .slice(1)
        .filter((_, index) => index % 2 === 1)
        .map((payload) => JSON.parse(payload)),
    )
    .filter((event) => event.exception);
  if (!events.length)
    throw new Error(
      "No browser event emitted: build dist with the real browser DSN first.",
    );
  console.log(
    JSON.stringify({
      component: "frontend",
      transport_results: receipts,
      events: events.map((event) => ({
        event_id: event.event_id,
        release: event.release,
        environment: event.environment,
        debug_ids: event.debug_meta?.images?.map((image) => image.debug_id),
      })),
      ingestion_verified: false,
    }),
  );
} finally {
  await browser?.close();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
