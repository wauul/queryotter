import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { createServer } from "node:http";
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { chromium } from "@playwright/test";

test(
  "real browser SDK captures automatic errors, handled failures once, private traces and translated React fallback",
  { timeout: 300000 },
  async () => {
    process.env.VITE_SENTRY_DSN = "https://public@o0.ingest.sentry.io/1";
    process.env.VITE_SENTRY_TRACES_SAMPLE_RATE = "1";
    process.env.SENTRY_ENVIRONMENT = "test";
    const directory = mkdtempSync(join(tmpdir(), "queryotter-browser-"));
    await build({
      configFile: false,
      root: resolve("tests"),
      plugins: [react()],
      logLevel: "error",
      define: {
        "import.meta.env.VITE_SENTRY_DSN": JSON.stringify(
          process.env.VITE_SENTRY_DSN,
        ),
        "import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE": '"1"',
        "import.meta.env.VITE_SENTRY_ENVIRONMENT": '"test"',
        "import.meta.env.VITE_SENTRY_RELEASE": JSON.stringify("c".repeat(40)),
      },
      build: {
        outDir: directory,
        emptyOutDir: true,
        rollupOptions: { input: resolve("tests/sentry-browser-fixture.html") },
      },
    });
    const server = createServer((request, response) => {
      const path = new URL(request.url, "http://localhost").pathname;
      try {
        const file = resolve(directory, "." + path);
        if (!file.startsWith(resolve(directory)))
          throw new Error("Invalid fixture path");
        const content = readFileSync(file);
        response.setHeader(
          "content-type",
          file.endsWith(".js")
            ? "application/javascript"
            : file.endsWith(".css")
              ? "text/css"
              : "text/html",
        );
        response.end(content);
      } catch {
        response.writeHead(404);
        response.end();
      }
    });
    let browser;
    try {
      await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
      console.log("Telemetry fixture server listening");
      const edge =
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
      browser = await chromium.launch({
        headless: true,
        ...(!existsSync(chromium.executablePath()) && existsSync(edge)
          ? { executablePath: edge }
          : {}),
      });
      console.log("Headless browser launched");
      const origin = `http://127.0.0.1:${server.address().port}`;
      for (const language of ["en", "fr"]) {
        const context = await browser.newContext();
        console.log(`Browser context ready: ${language}`);
        const page = await context.newPage();
        console.log(`Browser page ready: ${language}`);
        page.setDefaultTimeout(30000);
        const envelopes = [];
        await page.route("https://o0.ingest.sentry.io/**", async (route) => {
          envelopes.push(route.request().postData());
          await route.fulfill({
            status: 200,
            body: "{}",
            headers: { "access-control-allow-origin": "*" },
          });
        });
        const requests = [];
        await page.route("**/api/assistant/**", async (route) => {
          requests.push(route.request());
          await route.fulfill({
            status: route.request().url().endsWith("/session") ? 401 : 503,
            json: { detail: "synthetic-server-secret" },
          });
        });
        await page.goto(
          `${origin}/sentry-browser-fixture.html?lang=${language}&code=synthetic-oauth-secret`,
        );
        console.log(`Fixture page loaded: ${language}`);
        await page.waitForFunction(() => window.smoke !== undefined);
        console.log(`Telemetry fixture ready: ${language}`);
        const events = () =>
          envelopes
            .flatMap((envelope) =>
              envelope
                .split("\n")
                .slice(1)
                .filter((_, index) => index % 2 === 1)
                .map((payload) => JSON.parse(payload)),
            )
            .filter((payload) => payload.exception);
        assert.deepEqual(
          await page.evaluate(() => window.smoke.clearUser()),
          {},
        );
        await page.evaluate(() => window.smoke.handled());
        await page.evaluate(() => window.smoke.flush());
        assert.equal(
          events().length,
          1,
          "explicit + automatic recapture is deduplicated",
        );
        await page.evaluate(() => window.smoke.uncaught());
        await page.waitForFunction(() => true); // yield to the browser event loop
        await page.evaluate(() => window.smoke.flush());
        assert.equal(events().length, 2, "uncaught error captured");
        await page.evaluate(() => window.smoke.rejection());
        await page.waitForFunction(() => true);
        await page.evaluate(() => window.smoke.flush());
        assert.equal(events().length, 3, "unhandled rejection captured");
        await page.evaluate(() =>
          window.smoke.request("/api/assistant/session"),
        );
        await page.evaluate(() => window.smoke.flush());
        assert.equal(
          events().length,
          3,
          "ordinary authentication failure excluded",
        );
        await page.evaluate(() => window.smoke.request("/api/assistant/jobs"));
        await page.evaluate(() => window.smoke.flush());
        assert.equal(
          events().length,
          4,
          "handled server failure captured once",
        );
        assert.match(
          requests.at(-1).headers()["sentry-trace"],
          /^[a-f0-9]{32}-[a-f0-9]{16}-1$/,
        );
        assert.equal(
          (requests.at(-1).headers().baggage || "").includes("synthetic-"),
          false,
        );
        await page.evaluate(() => window.smoke.renderBroken());
        await page.getByRole("alert").waitFor();
        await page.evaluate(() => window.smoke.flush());
        assert.equal(events().length, 5, "React boundary reports once");
        assert.match(
          await page.getByRole("alert").innerText(),
          language === "fr" ? /Recharger QueryOtter/ : /Reload QueryOtter/,
        );
        assert.equal(
          envelopes.join("").includes("synthetic-"),
          false,
          "no secrets enter any envelope or span",
        );
        assert.ok(
          events().every(
            (event) =>
              event.tags.component === "frontend" &&
              event.environment === "test" &&
              !event.user,
          ),
        );
        assert.ok(!envelopes.join("").includes("replay_event"));
        await context.close();
        console.log(
          `Browser capture, privacy and boundary checks passed: ${language}`,
        );
      }
    } finally {
      await browser?.close();
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
      if (
        resolve(directory).startsWith(
          resolve(tmpdir()) + (process.platform === "win32" ? "\\" : "/"),
        ) &&
        directory.includes("queryotter-browser-")
      )
        rmSync(directory, { recursive: true, force: true });
      delete process.env.VITE_SENTRY_DSN;
      delete process.env.VITE_SENTRY_TRACES_SAMPLE_RATE;
      delete process.env.SENTRY_ENVIRONMENT;
    }
  },
);
