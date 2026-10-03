// Independent disposable fixture: never reuse or modify the developer's DB.
import EmbeddedPostgres from "embedded-postgres";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { randomBytes } from "node:crypto";
import { spawn } from "node:child_process";
const directory = mkdtempSync(join(tmpdir(), "queryotter-verify-"));
const password = randomBytes(24).toString("hex");
const port = 55439;
const pg = new EmbeddedPostgres({
  databaseDir: directory,
  user: "queryotter",
  password,
  port,
  persistent: true,
  postgresFlags: ["-c", "listen_addresses=127.0.0.1"],
  onLog: () => {},
  onError: () => {},
});
try {
  await pg.initialise();
  await pg.start();
  await pg.createDatabase("queryotter");
  const url = `postgresql://queryotter:${password}@127.0.0.1:${port}/queryotter`;
  const env = {
    ...process.env,
    EXPERIMENT_DATABASE_URL: url,
    STORE_TEST_DATABASE_URL: url,
    SENTRY_PYTHON_DSN: "",
    SENTRY_PROXY_DSN: "",
  };
  delete env.JOB_DATABASE_URL;
  const python = process.env.QOT_TEST_PYTHON;
  const child = spawn(
    "uv",
    [
      "run",
      ...(python ? ["--isolated", "--python", python] : []),
      "pytest",
      "-q",
      "--tb=short",
      ...process.argv.slice(2),
    ],
    {
      env,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  for (const stream of [child.stdout, child.stderr])
    stream.on("data", (data) =>
      process.stdout.write(data.toString().replaceAll(password, "[redacted]")),
    );
  const exitCode = await new Promise((resolve, reject) => {
    child.on("exit", resolve);
    child.on("error", reject);
  });
  if (exitCode) process.exitCode = exitCode;
} finally {
  // embedded-postgres 18.4 waits for a future exit event even if its child has
  // already exited. Clear only that finished child to avoid a Windows hang and
  // prevent its exit hook from trying to terminate a potentially reused PID.
  if (
    pg.process &&
    (pg.process.exitCode !== null || pg.process.signalCode !== null)
  )
    pg.process = undefined;
  await pg.stop();
  const target = resolve(directory);
  const root = resolve(tmpdir());
  if (
    target.startsWith(root + (process.platform === "win32" ? "\\" : "/")) &&
    target.includes("queryotter-verify-")
  )
    rmSync(target, {
      recursive: true,
      force: true,
      maxRetries: 10,
      retryDelay: 500,
    });
}
