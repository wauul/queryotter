import { useLanguage } from "./Language";
import React from "react";
import { BookOpen, ShieldCheck, ExternalLink, Database } from "lucide-react";
import type { Catalog } from "./studio-api";

export default function StudioDocs({
  page,
  catalog,
}: {
  page: string;
  catalog: Catalog | null;
}) {
  const { t: tr } = useLanguage();

  if (page === "support")
    return (
      <article className="q-prose" id="q-main" tabIndex={-1}>
        <h1>{tr("Help with your next step")}</h1>
        <p>
          {tr(
            "Start with the field guide for connection setup, query review and the limits of each engine. The support matrix records which configurations have actually been tested.",
          )}
        </p>
        <a className="q-button" href="#docs">
          {tr("Open the field guide")}
        </a>{" "}
        <a className="q-button secondary" href="#matrix">
          {tr("Check engine support")}
        </a>
        <h2>{tr("Connection not working?")}</h2>
        <p>
          {tr(
            "Check the selected engine, URL encoding, public network allowlist, TLS certificate and read-only permissions. A private or local database needs the authenticated outbound connector. Copy the error category, not the credentials.",
          )}
        </p>
        <h2>{tr("Query results look wrong?")}</h2>
        <p>
          {tr(
            "Review joins, date boundaries, NULLs, duplicates and ordering. Refresh metadata after schema changes. Successful execution does not prove that the query matches your business meaning.",
          )}
        </p>
        <h2>{tr("Report a defect")}</h2>
        <p>
          {tr(
            "Include the engine and version, the affected step and a synthetic example that reproduces the problem. Remove database URLs, passwords, tokens and private records before posting.",
          )}
        </p>
        <a
          href="https://github.com/wauul/queryotter/issues"
          target="_blank"
          rel="noreferrer"
        >
          {tr("Open the GitHub issue tracker ")}
          <ExternalLink size={14} />
        </a>
        <h2>{tr("Support availability")}</h2>
        <p>
          {tr(
            "QueryOtter is a portfolio application. Support uses the public repository issue tracker; no private support email or response-time guarantee is configured.",
          )}
        </p>
      </article>
    );
  if (page === "privacy")
    return (
      <article className="q-prose" id="q-main" tabIndex={-1}>
        <span className="q-doc-meta">
          {tr("Privacy · updated 3 October 2026")}
        </span>
        <h1>{tr("Privacy policy")}</h1>
        <p>
          {tr(
            "QueryOtter stores the account identifier, display name and email supplied by your sign-in provider, your workspace settings, encrypted connection configuration, discovered schema metadata, saved queries, query history and operation usage. It does not claim a certification or a legal guarantee.",
          )}
        </p>
        <h2>{tr("Credentials and model requests")}</h2>
        <p>
          {tr(
            "Connection secrets are encrypted with Fernet using an encryption key configured separately from application data. They are used by the worker to open your selected database and are never sent to Groq. Local connector credentials stay on your own machine. OAuth provider tokens are discarded after verifying your identity; opaque session tokens are stored only as hashes.",
          )}
        </p>
        <p>
          {tr(
            "Natural-language prompts, scoped schema names, field types, relationships, indexes, the current query and available plans are sent to Groq for generation or recommendations. Metadata and query literals can themselves contain sensitive information: review what you enter. Raw result records are not sent to the model. Optional document-field inference reads up to 20 records per collection locally to infer names and types; these values are not shared with the model.",
          )}
        </p>
        <h2>{tr("Results and retention")}</h2>
        <p>
          {tr(
            "Execution returns at most 500 rows and 2 MB. Results are encrypted in the application database and expire after 15 minutes; subsequent pages use the same bounded snapshot. Query history is kept for your selected 1–90 days. Saved queries remain until removed. Expired results are refused immediately; physical deletion of expired data happens during account activity and service maintenance. Inactive demo accounts are eligible for deletion after one day.",
          )}
        </p>
        <p>
          {tr(
            "Removing a connection removes its cached schema, saved queries, history, results and associated jobs. Clearing history removes completed operation history and result snapshots. Account deletion revokes sessions and connectors and removes active application account data, connections, schema caches, saved queries, jobs, history and results. Hosting backups may persist until they expire under the hosting provider's own policy. The application cannot delete copies you exported or data held by your connected database or identity provider.",
          )}
        </p>
        <h2>{tr("Third-party services")}</h2>
        <p>
          {tr(
            "The deployed application uses Vercel for the web application, Neon for durable application and disposable experiment databases, Railway for the Python API and worker, and Groq for model inference. Your chosen database provider and GitHub, Google or Microsoft also process their respective requests. See the visible deployment and support status for what is currently active. Standard operational logs record job IDs, stages, timings and error categories; provider response bodies and database credentials are excluded.",
          )}
        </p>
        <h2>{tr("Error and performance monitoring")}</h2>
        <p>
          {tr(
            "When configured, QueryOtter uses Sentry to receive sanitized error stack locations and sampled operation timings from the browser, proxy, API and worker. Telemetry includes component, operation, release, deployment environment and random trace identifiers. Request bodies, cookies, authorization, credentials, OAuth codes, prompts, queries, schema names, model output and record values are excluded. Error messages and breadcrumbs are removed. Session Replay, telemetry logs and profiling are disabled. Sentry receives ingestion network information as the service provider; application telemetry does not attach account identity or IP addresses. Sentry retention follows the operator's project settings and is separate from query-history retention.",
          )}
        </p>
        <h2>{tr("Choices and support")}</h2>
        <p>
          {tr(
            "You can export account data, queries and unexpired results, set history retention, disable document inference, rotate or remove connections, revoke connectors, log out, or delete your account. Support is available through the",
          )}{" "}
          <a
            href="https://github.com/wauul/queryotter/issues"
            target="_blank"
            rel="noreferrer"
          >
            {tr("QueryOtter repository issue tracker")}
          </a>
          {tr(". Never include secrets or private records in a public issue.")}
        </p>
      </article>
    );
  if (page === "terms")
    return (
      <article className="q-prose" id="q-main" tabIndex={-1}>
        <span className="q-doc-meta">
          {tr("Terms · updated 30 September 2026")}
        </span>
        <h1>{tr("Terms of use")}</h1>
        <p>
          {tr(
            "QueryOtter is a portfolio database assistant. Use it only with databases and data you are authorized to access. Keep credentials restricted to read-only permissions and follow your database, identity and model providers' terms. These terms do not invent a legal entity, certification, service-level commitment or support guarantee.",
          )}
        </p>
        <h2>{tr("Review every query")}</h2>
        <p>
          {tr(
            "Generated queries and recommendations may be wrong or incomplete. Syntax validation and successful execution do not prove business meaning. Review joins, dates, NULLs, duplicates, missing fields and ordering before selecting Run. QueryOtter never runs a draft merely because you submitted a natural-language request. Bounded results may omit rows beyond the limit.",
          )}
        </p>
        <h2>{tr("Optimization evidence")}</h2>
        <p>
          {tr(
            "Non-executing plans are estimates. Suggestions are unmeasured until a supported controlled benchmark verifies result semantics and timings on its stated dataset. SQLite experiments use disposable copies; the PostgreSQL experiment workspace uses synthetic disposable schemas. QueryOtter does not automatically apply indexes to your connected production database. Indexes can increase storage and slow writes. Results on one dataset do not guarantee performance elsewhere.",
          )}
        </p>
        <h2>{tr("Availability and limits")}</h2>
        <p>
          {tr(
            "Adapters expose different capabilities. Hosted-provider access can require your own credentials, network access or human setup. The support matrix distinguishes local/emulator tests from hosted verification. Free plans, budgets, timeouts and provider quotas can restrict usage or cause cold starts. Do not use this portfolio application as the sole control for a critical production operation.",
          )}
        </p>
        <h2>{tr("Deletion and privacy")}</h2>
        <p>
          {tr(
            "You control connection removal, history retention, export and account deletion as described in the ",
          )}
          <a href="#privacy">{tr("privacy policy")}</a>
          {tr(
            ". You are responsible for protecting local connector profiles, tokens and exported records. Do not attempt to bypass authentication, access other workspaces, probe internal infrastructure or overwhelm public demo resources.",
          )}
        </p>
        <h2>{tr("Support")}</h2>
        <p>
          {tr("Report defects through")}{" "}
          <a
            href="https://github.com/wauul/queryotter/issues"
            target="_blank"
            rel="noreferrer"
          >
            {tr("GitHub issues")}
          </a>
          {tr(
            ", without sharing credentials or private data. Provider services have their own terms and retention policies.",
          )}
        </p>
      </article>
    );
  return (
    <article className="q-prose" id="q-main" tabIndex={-1}>
      <h1>{tr("The QueryOtter field guide")}</h1>
      <p>
        {tr(
          "Start with a safe synthetic demo or connect a read-only database. Explore what is actually there, ask in plain language, review the native query, then run it. Optimize only when the evidence supports a change.",
        )}
      </p>
      <div className="q-doc-steps">
        <div>
          <Database />
          <h3>{tr("1. Connect and discover")}</h3>
          <p>
            {tr(
              "Select a provider and its real engine. Paste a URL or use the guided form. Use verified TLS, a dedicated read-only login, and the right schema. Test connection and inspect the discovered fields.",
            )}
          </p>
        </div>
        <div>
          <BookOpen />
          <h3>{tr("2. Ask, review, run")}</h3>
          <p>
            {tr(
              "Try “Show the five customers with the highest total paid orders last month.” Define paid status and your time zone. A draft can ask for clarification. Refine it conversationally; Run is always explicit.",
            )}
          </p>
        </div>
        <div>
          <ShieldCheck />
          <h3>{tr("3. Investigate a change")}</h3>
          <p>
            {tr(
              "Review the actual plan and indexes where supported. Candidates are recommendations. Benchmark supported copies to see typed-result checks, median latency, variability and index tradeoffs.",
            )}
          </p>
        </div>
      </div>
      <h2>{tr("Provider connection guides")}</h2>
      {catalog?.providers.map((p) => (
        <details key={p.id}>
          <summary>
            {tr(p.name)}
            <span>{p.engines.join(" · ")}</span>
          </summary>
          <p>{tr(p.instructions)}</p>
          <p>
            <strong>{tr("Authentication:")}</strong> {tr(p.authentication)}
            <br />
            <strong>{tr("TLS:")}</strong> {tr(p.tls)}
          </p>
          {p.limitation && <p className="q-note">{tr(p.limitation)}</p>}
          <a href={p.docs} target="_blank" rel="noreferrer">
            {tr("Official connection documentation ")}
            <ExternalLink size={14} />
          </a>
        </details>
      ))}
      <h2>{tr("Read-only credential setup")}</h2>
      <p>
        {tr(
          "PostgreSQL/CockroachDB: a dedicated login with CONNECT, schema USAGE and SELECT, without schema CREATE or elevated roles. MySQL/MariaDB: SELECT on one database without FILE, EXECUTE or write grants. SQL Server: a restricted SQL login with SELECT and optionally VIEW DEFINITION/SHOWPLAN. MongoDB: the read role on one database. Firestore: a dedicated service account with datastore viewer permissions; IAM bypasses Security Rules. Realtime Database: a dedicated IAM viewer account and reviewed rules/indexes. Turso: a read-only database token. SQLite: upload a copy of at most 2 MiB.",
        )}
      </p>
      <h2>{tr("Local and private networks")}</h2>
      <p>
        {tr(
          "Install the outbound connector on a machine that can reach your database. Enroll it in account settings and configure an exact profile and host allowlist. Passwords stay on that machine; removing the connector revokes its token. Cloud applications cannot reach your localhost automatically.",
        )}
      </p>
      <a
        href="https://github.com/wauul/queryotter/blob/main/docs/local-connector.md"
        target="_blank"
        rel="noreferrer"
      >
        {tr("Connector installation instructions ")}
        <ExternalLink size={14} />
      </a>
      <h2>{tr("Frequently asked questions")}</h2>
      {[
        [
          "Does generating a query run it?",
          "No. Generation sends scoped metadata to Groq, validates the draft and presents it for review. Only selecting Run executes it.",
        ],
        [
          "Does QueryOtter see or store my password?",
          "Direct connection secrets are encrypted on the server and never returned or sent to Groq. With the local connector, database credentials stay on your machine.",
        ],
        [
          "Why is a field missing?",
          "Relational discovery is scoped to the selected schema. Document inference is optional and sampled, so sparse fields or new schema changes may be absent. Refresh metadata and review its uncertainty.",
        ],
        [
          "Are all nine engines equally optimizable?",
          "No. Plans and profiling vary. Firebase native queries do not offer equivalent SQL plans or experimental indexes through these adapters. The support matrix exposes the difference.",
        ],
        [
          "Does a passing query prove the answer is right?",
          "No. Syntax, execution and business meaning are separate claims. Published evaluation cases compare independently specified expected results; arbitrary user questions require review.",
        ],
        [
          "Can I import Prisma?",
          "Yes, as optional model context after database discovery. Imported table and field mappings are checked against actual metadata. Prisma is an ORM integration and does not replace your database connection.",
        ],
        [
          "Why did the connection fail?",
          "Check the exact database URL, public network allowlist, password encoding, verified TLS and CA certificate, selected schema, engine/version, and read-only grants. Private hosts need the connector.",
        ],
        [
          "What are the limits?",
          "Ten connections and one active operation per workspace, 500 rows/2 MB per result, 15-minute result snapshots, bounded model tokens and one repair. Public demo model calls share a small daily budget.",
        ],
      ].map(([q, a]) => (
        <details key={q}>
          <summary>{tr(q)}</summary>
          <p>{tr(a)}</p>
        </details>
      ))}
      <h2>{tr("Support and source")}</h2>
      <p>
        {tr("Use")}{" "}
        <a
          href="https://github.com/wauul/queryotter/issues"
          target="_blank"
          rel="noreferrer"
        >
          {tr("GitHub issues")}
        </a>{" "}
        {tr("for support and")}{" "}
        <a
          href="https://github.com/wauul/queryotter"
          target="_blank"
          rel="noreferrer"
        >
          {tr("the repository")}
        </a>{" "}
        {tr(
          "for setup, fixture data, deployment instructions, evaluation results and limitations. No private support email is configured. Remove credentials and private records before reporting a problem.",
        )}
      </p>
    </article>
  );
}
