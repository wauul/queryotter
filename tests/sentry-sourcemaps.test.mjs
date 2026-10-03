import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  readFileSync,
  readdirSync,
  mkdirSync,
  writeFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { TraceMap, originalPositionFor } from "@jridgewell/trace-mapping";
import { removeMaps } from "../scripts/sentry-build.mjs";

function cleanup(directory) {
  const target = resolve(directory),
    root = resolve(tmpdir());
  if (
    target.startsWith(root + (process.platform === "win32" ? "\\" : "/")) &&
    target.includes("queryotter-maps-")
  )
    rmSync(target, { recursive: true, force: true });
}
test(
  "hidden build maps resolve generated application stack positions to original TypeScript",
  { timeout: 300000 },
  async () => {
    const directory = mkdtempSync(join(tmpdir(), "queryotter-maps-"));
    try {
      await build({
        configFile: false,
        plugins: [react()],
        logLevel: "error",
        build: { sourcemap: "hidden", outDir: directory, emptyOutDir: true },
      });
      const asset = readdirSync(join(directory, "assets")).find((name) =>
        /^index-.*\.js$/.test(name),
      );
      const code = readFileSync(join(directory, "assets", asset), "utf8");
      assert.ok(!code.includes("sourceMappingURL="));
      const map = new TraceMap(
        JSON.parse(
          readFileSync(join(directory, "assets", asset + ".map"), "utf8"),
        ),
      );
      const phrase = "Please check your input and try again.";
      let found = false;
      for (
        let offset = code.indexOf(phrase);
        offset >= 0;
        offset = code.indexOf(phrase, offset + phrase.length)
      ) {
        const prefix = code.slice(0, offset),
          line = prefix.split("\n").length;
        const column = offset - (prefix.lastIndexOf("\n") + 1);
        const original = originalPositionFor(map, { line, column });
        if (original.source?.endsWith("/web/monitoring.ts")) {
          assert.ok(original.line > 0);
          found = true;
          break;
        }
      }
      assert.ok(
        found,
        "generated monitoring stack location maps to web/monitoring.ts",
      );
      removeMaps(directory);
      assert.ok(
        !readdirSync(join(directory, "assets")).some((name) =>
          name.endsWith(".map"),
        ),
      );
    } finally {
      cleanup(directory);
    }
  },
);
test("Sites packager independently excludes maps and preserves ordinary assets", () => {
  const directory = mkdtempSync(join(tmpdir(), "queryotter-maps-"));
  try {
    for (const folder of ["dist/assets", "hosting", ".openai"])
      mkdirSync(join(directory, folder), { recursive: true });
    writeFileSync(join(directory, "dist/index.html"), "<p>safe</p>");
    writeFileSync(join(directory, "dist/assets/index-test.js"), "safe();");
    writeFileSync(
      join(directory, "dist/assets/index-test.js.map"),
      "synthetic-source-map-secret",
    );
    writeFileSync(join(directory, "hosting/worker.js"), "export default {};");
    writeFileSync(join(directory, ".openai/hosting.json"), "{}");
    execFileSync(process.execPath, [resolve("scripts/build-hosting.mjs")], {
      cwd: directory,
      stdio: "pipe",
    });
    const worker = readFileSync(
      join(directory, "dist/server/index.js"),
      "utf8",
    );
    assert.ok(worker.includes("index-test.js"));
    assert.ok(!worker.includes("synthetic-source-map-secret"));
    assert.ok(!worker.includes(".map"));
  } finally {
    cleanup(directory);
  }
});
