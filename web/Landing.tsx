import { useLanguage } from "./Language";
import React, { useState } from "react";
import { Database, FlaskConical, LockKeyhole, ShieldCheck } from "lucide-react";
import type { Catalog } from "./studio-api";

const examples = [
  {
    label: "Paid customers",
    question: "Who were our five highest-paying customers last month?",
    prompt:
      "Show the five customers with the highest total paid orders last month. Paid means status = 'paid'. Use UTC calendar months and break ties by customer id.",
    sql: "SELECT c.name, SUM(o.total) AS paid_total\nFROM customers c\nJOIN orders o ON o.customer_id = c.id\nWHERE o.status = 'paid'\n  AND o.created_at >= :month_start\n  AND o.created_at < :month_end\nGROUP BY c.id, c.name\nORDER BY paid_total DESC, c.id\nLIMIT 5;",
    note: "UTC calendar month · paid orders · stable ties",
  },
  {
    label: "Recent orders",
    question: "Show the ten most recent paid orders",
    prompt:
      "Show the ten most recent orders with status = 'paid'. Return id, customer_id, total and created_at. Break timestamp ties by id descending.",
    sql: "SELECT id, customer_id, total, created_at\nFROM orders\nWHERE status = 'paid'\nORDER BY created_at DESC, id DESC\nLIMIT 10;",
    note: "Explicit paid status · newest first · ten rows",
  },
  {
    label: "Order counts",
    question: "How many orders are in each status?",
    prompt:
      "Count orders grouped by status, including NULL status as its own group. Order by count descending and status ascending.",
    sql: "SELECT status, COUNT(*) AS order_count\nFROM orders\nGROUP BY status\nORDER BY order_count DESC, status ASC;",
    note: "Includes NULL status · counts rows, not values",
  },
];

export default function Landing({
  catalog,
  busy,
  loading,
  onDemo,
  onConnect,
}: {
  catalog: Catalog | null;
  busy: boolean;
  loading: boolean;
  onDemo: (prompt?: string) => void;
  onConnect: () => void;
}) {
  const { t: tr } = useLanguage();

  const [active, setActive] = useState(0);
  const example = examples[active];
  return (
    <main className="q-landing" id="q-main" tabIndex={-1}>
      <section className="q-hero">
        <div className="q-hero-copy">
          <h1>
            {tr("Your database, ")}
            <em>{tr("understood")}</em>
          </h1>
          <p>
            {tr(
              "Start with a question. Get a native query grounded in your schema. Then check the answer and the evidence behind a faster version.",
            )}
          </p>
          <div className="q-hero-actions">
            <button
              className="q-button large"
              onClick={() => onDemo(tr(example.prompt))}
              disabled={busy || loading}
            >
              {tr("Try the demo")}
            </button>
            <button className="q-button secondary large" onClick={onConnect}>
              {tr("Connect a database")}
            </button>
          </div>
          <div className="q-hero-facts">
            <span>
              <ShieldCheck size={15} />
              {tr(" Read-only by default")}
            </span>
            <span>
              <LockKeyhole size={15} />
              {tr(" Credentials stay out of the model")}
            </span>
          </div>
        </div>
        <article
          className="q-specimen"
          aria-label={tr("Synthetic query examples")}
        >
          <header>
            <strong>{tr("A question becomes a query")}</strong>
            <span className="q-tag">{tr("SQLite demo schema")}</span>
          </header>
          <div
            className="q-example-tabs"
            role="group"
            aria-label={tr("Choose an example")}
          >
            {examples.map((item, i) => (
              <button
                key={tr(item.label)}
                aria-pressed={active === i}
                onClick={() => setActive(i)}
              >
                {tr(item.label)}
              </button>
            ))}
          </div>
          <div className="q-specimen-step">
            <span aria-hidden="true">01</span>
            <div>
              <h2>{tr("Ask in your own words")}</h2>
              <p>{tr(example.question)}</p>
            </div>
          </div>
          <div className="q-specimen-step">
            <span aria-hidden="true">02</span>
            <div>
              <h2>{tr("Review the native query")}</h2>
            </div>
          </div>
          <pre>
            <code>{example.sql}</code>
          </pre>
          <footer>
            <p>
              {tr("Illustrative SQL · ")}
              {tr(example.note)}
            </p>
            <button
              onClick={() => onDemo(tr(example.prompt))}
              disabled={busy || loading}
            >
              {tr("Open this question")}
            </button>
          </footer>
        </article>
      </section>
      <section className="q-method">
        <div>
          <h2>{tr("Keep the question connected to the evidence")}</h2>
          <p>
            {tr(
              "Each step gives you something concrete to inspect. You decide when a query runs.",
            )}
          </p>
          <a className="q-inline-link" href="#docs">
            {tr("Read the field guide")}
          </a>
        </div>
        <ol>
          <li>
            <div>
              <h3>{tr("Connect and see what’s there")}</h3>
              <p>
                {tr(
                  "Paste a connection string or follow a provider guide. Test credentials and TLS, then explore actual tables, fields and relationships.",
                )}
              </p>
            </div>
          </li>
          <li>
            <div>
              <h3>{tr("Ask, refine and review")}</h3>
              <p>
                {tr(
                  "Get SQL in the right dialect or a supported native document query. Check joins, filters and date boundaries before selecting Run.",
                )}
              </p>
            </div>
          </li>
          <li>
            <div>
              <h3>{tr("Measure a proposed change")}</h3>
              <p>
                {tr(
                  "Inspect plans and indexes where available. Supported disposable-copy benchmarks compare results, latency, variability and index costs.",
                )}
              </p>
            </div>
          </li>
        </ol>
      </section>
      <section className="q-engine-section">
        <div>
          <h2>{tr("Nine engines, explicit limits")}</h2>
          <p>
            {tr(
              "Providers host databases. Engines determine the query language and available evidence. See exactly what was tested locally, in emulators or on a hosted service.",
            )}
          </p>
          <a href="#matrix" className="q-inline-link">
            {tr("View the support matrix")}
          </a>
        </div>
        <div className="q-engine-grid">
          {catalog?.engines.map((e) => (
            <a href="#matrix" key={e.id}>
              <Database size={18} />
              <strong>{e.name}</strong>
              <small>
                {e.verification.status.startsWith("Verified")
                  ? tr("Local / emulator checks passed")
                  : tr("Verification pending")}
              </small>
            </a>
          )) || <p role="status">{tr("Loading support evidence…")}</p>}
        </div>
      </section>
      <section className="q-benchmark-teaser">
        <FlaskConical size={27} />
        <div>
          <h2>{tr("A performance claim needs a method")}</h2>
          <p>
            {tr(
              "Explore actual PostgreSQL reports, independent correctness fixtures and measured timing distributions. A recommendation becomes an improvement only when the comparison supports it.",
            )}
          </p>
        </div>
        <a className="q-button secondary" href="#experiments">
          {tr("Open experiments")}
        </a>
      </section>
    </main>
  );
}
