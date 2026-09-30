import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../web/Language.tsx", import.meta.url),
  "utf8",
);
const french = JSON.parse(
  readFileSync(new URL("../web/locales/fr.json", import.meta.url), "utf8"),
);
const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    esModuleInterop: true,
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX,
  },
}).outputText;
const exports = {};
new Function("require", "exports", compiled)(
  (name) => (name === "./locales/fr.json" ? french : require(name)),
  exports,
);
const { translate } = exports;

test("French interpolation preserves query identifiers and user values verbatim", () => {
  const name = "orders.NULL {value1} <customer>  café";
  const key = "Delete saved query {value0}";
  assert.equal(
    translate(key, "fr", { value0: name }),
    french[key].replace("{value0}", name),
  );
  assert.equal(
    translate(key, "en", { value0: name }),
    "Delete saved query " + name,
  );
});
test("known labels translate, English recovers, and unknown technical output stays unchanged", () => {
  assert.equal(translate("Dark mode", "fr"), "Mode sombre");
  assert.equal(translate("Dark mode", "en"), "Dark mode");
  for (const raw of [
    "SELECT  id\nFROM orders",
    '{ "status": null }',
    "",
    "  ",
    "Unexpected error:  unknown field",
  ]) {
    assert.equal(translate(raw, "fr"), raw);
  }
  assert.equal(
    translate(" Read-only by default ", "fr"),
    " " + french["Read-only by default"] + " ",
  );
});
test("all literal interface translation calls have French copy", () => {
  const missing = new Set();
  for (const name of readdirSync(new URL("../web/", import.meta.url)).filter(
    (x) => x.endsWith(".tsx"),
  )) {
    const file = ts.createSourceFile(
      name,
      readFileSync(new URL("../web/" + name, import.meta.url), "utf8"),
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX,
    );
    function visit(node) {
      if (
        ts.isCallExpression(node) &&
        ts.isIdentifier(node.expression) &&
        ["tr", "t"].includes(node.expression.text) &&
        ts.isStringLiteral(node.arguments[0])
      ) {
        const key = node.arguments[0].text.trim().replace(/\s+/g, " ");
        if (key && !Object.hasOwn(french, key)) missing.add(key);
      }
      ts.forEachChild(node, visit);
    }
    visit(file);
  }
  assert.deepEqual([...missing], []);
});
test("French copy preserves the published privacy limits and DELETE confirmation token", () => {
  const key =
    "Ten connections and one active operation per workspace, 500 rows/2 MB per result, 15-minute result snapshots, bounded model tokens and one repair. Public demo model calls share a small daily budget.";
  assert.match(french[key], /500 lignes et 2 Mo/);
  assert.match(french[key], /15 minutes/);
  const entry = Object.entries(french).find(([key]) => key.includes("DELETE"));
  assert.ok(entry, "account deletion confirmation is translated");
  assert.match(entry[1], /DELETE/);
});
