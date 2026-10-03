import { execFileSync } from "node:child_process";
import { readdirSync, rmSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { releaseName } from "../shared/telemetry.js";

export function buildSettings(env, command) {
  if (
    Object.keys(env).some(
      (key) => /^VITE_.*(?:AUTH_TOKEN|SECRET|PASSWORD)/.test(key) && env[key],
    )
  )
    throw new Error("Build secrets must not use VITE_ variables.");
  const enabled = !!env.VITE_SENTRY_DSN;
  let sha =
    env.SENTRY_RELEASE ||
    env.VERCEL_GIT_COMMIT_SHA ||
    env.RAILWAY_GIT_COMMIT_SHA;
  if (!sha) {
    try {
      sha = execFileSync("git", ["rev-parse", "HEAD"], {
        encoding: "utf8",
      }).trim();
    } catch {
      /* no checkout */
    }
  }
  const release = releaseName(sha);
  if (enabled && command === "build") {
    if (
      !release ||
      !env.SENTRY_AUTH_TOKEN ||
      !env.SENTRY_ORG ||
      !env.SENTRY_PROJECT
    )
      throw new Error(
        "Monitored builds require a Git release, SENTRY_AUTH_TOKEN, SENTRY_ORG and SENTRY_PROJECT. Uploads cannot be skipped.",
      );
    const dsn = new URL(env.VITE_SENTRY_DSN);
    if (
      dsn.protocol !== "https:" ||
      !dsn.username ||
      dsn.password ||
      !/^\/\d+$/.test(dsn.pathname)
    )
      throw new Error("Invalid browser Sentry DSN.");
    // Fail before publishing if the exact ingestion origin has not been approved.
    const config = JSON.parse(readFileSync("vercel.json", "utf8"));
    const csp = config.headers
      .flatMap((item) => item.headers)
      .find((header) => header.key === "Content-Security-Policy").value;
    const origins = csp
      .split(";")
      .find((directive) => directive.trim().startsWith("connect-src "))
      .trim()
      .split(/\s+/)
      .slice(1);
    if (!origins.includes(dsn.origin))
      throw new Error(
        "Add the exact browser DSN ingestion origin to vercel.json connect-src before building.",
      );
  }
  return { enabled, release };
}
export function removeMaps(directory = "dist") {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) removeMaps(path);
    else if (entry.name.endsWith(".map")) rmSync(path);
  }
}
