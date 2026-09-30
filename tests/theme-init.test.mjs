import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const boot = readFileSync(new URL("../public/theme-init.js", import.meta.url), "utf8");
function firstPaint(saved, darkSystem, storageBlocked = false) {
  const root = { dataset: {}, style: {} };
  runInNewContext(boot, {
    document: { documentElement: root },
    window: { matchMedia: () => ({ matches: darkSystem }) },
    localStorage: { getItem: () => { if (storageBlocked) throw Error("storage blocked"); return saved; } },
  });
  return root;
}
for (const [name, saved, darkSystem, expected] of [
  ["first visit follows a light system", null, false, "light"],
  ["first visit follows a dark system", null, true, "dark"],
  ["saved light overrides a dark system before rendering", "light", true, "light"],
  ["saved dark overrides a light system before rendering", "dark", false, "dark"],
  ["system mode follows the current system", "system", true, "dark"],
  ["invalid saved values fall back to the system", "unexpected", false, "light"],
]) {
  test(name, () => {
    const root = firstPaint(saved, darkSystem);
    assert.equal(root.dataset.theme, expected);
    assert.equal(root.style.colorScheme, expected);
  });
}
test("blocked browser storage still renders in the system theme", () => {
  assert.equal(firstPaint(null, true, true).dataset.theme, "dark");
});
test("theme initialization is a blocking same-origin script allowed by the production CSP", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.match(html, /<script src="\/theme-init\.js"><\/script>/);
  assert.ok(html.indexOf("theme-init.js") < html.indexOf('id="root"'));
  const config = JSON.parse(readFileSync(new URL("../vercel.json", import.meta.url), "utf8"));
  const csp = config.headers[0].headers.find(h => h.key === "Content-Security-Policy").value;
  assert.match(csp, /script-src 'self';/);
});
