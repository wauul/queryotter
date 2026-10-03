import { readdirSync, readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
const map = {};
function collect(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "server" || e.name === ".openai" || e.name.endsWith('.map')) continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) collect(p);
    else {
      const ext = p.split(".").at(-1),
        type =
          {
            html: "text/html; charset=utf-8",
            js: "application/javascript; charset=utf-8",
            css: "text/css; charset=utf-8",
            json: "application/json",
          }[ext] || "text/plain";
      map["/" + relative("dist", p).replaceAll("\\", "/")] = {
        body: readFileSync(p, "utf8"),
        type,
      };
    }
  }
}
collect("dist");
mkdirSync("dist/server", { recursive: true });
mkdirSync("dist/.openai", { recursive: true });
writeFileSync(
  "dist/server/index.js",
  "globalThis.__QUERYOTTER_ASSETS=" +
    JSON.stringify(map) +
    ";\n" +
    readFileSync("hosting/worker.js", "utf8"),
);
writeFileSync(
  "dist/.openai/hosting.json",
  readFileSync(".openai/hosting.json"),
);
console.log(
  `Built self-contained Sites Worker with ${Object.keys(map).length} public assets; no credentials included.`,
);
