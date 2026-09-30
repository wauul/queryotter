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
  const [active, setActive] = useState(0);
  const example = examples[active];
  return (
    <main className="q-landing" id="q-main" tabIndex={-1}>
      <section className="q-hero">
        <div className="q-hero-copy">
          <h1>
            Your database, <em>understood</em>
          </h1>
          <p>
            Start with a question. Get a native query grounded in your schema.
            Then check the answer and the evidence behind a faster version.
          </p>
          <div className="q-hero-actions">
            <button
              className="q-button large"
              onClick={() => onDemo(example.prompt)}
              disabled={busy || loading}
            >
              Try the demo
            </button>
            <button className="q-button secondary large" onClick={onConnect}>
              Connect a database
            </button>
          </div>
          <div className="q-hero-facts">
            <span>
              <ShieldCheck size={15} /> Read-only by default
            </span>
            <span>
              <LockKeyhole size={15} /> Credentials stay out of the model
            </span>
          </div>
        </div>
        <article className="q-specimen" aria-label="Synthetic query examples">
          <header>
            <strong>A question becomes a query</strong>
            <span className="q-tag">SQLite demo schema</span>
          </header>
          <div
            className="q-example-tabs"
            role="group"
            aria-label="Choose an example"
          >
            {examples.map((item, i) => (
              <button
                key={item.label}
                aria-pressed={active === i}
                onClick={() => setActive(i)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="q-specimen-step">
            <span aria-hidden="true">01</span>
            <div>
              <h2>Ask in your own words</h2>
              <p>{example.question}</p>
            </div>
          </div>
          <div className="q-specimen-step">
            <span aria-hidden="true">02</span>
            <div>
              <h2>Review the native query</h2>
            </div>
          </div>
          <pre>
            <code>{example.sql}</code>
          </pre>
          <footer>
            <p>Illustrative SQL · {example.note}</p>
            <button
              onClick={() => onDemo(example.prompt)}
              disabled={busy || loading}
            >
              Open this question
            </button>
          </footer>
        </article>
      </section>
      <section className="q-method">
        <div>
          <h2>Keep the question connected to the evidence</h2>
          <p>
            Each step gives you something concrete to inspect. You decide when a
            query runs.
          </p>
          <a className="q-inline-link" href="#docs">
            Read the field guide
          </a>
        </div>
        <ol>
          <li>
            <div>
              <h3>Connect and see what’s there</h3>
              <p>
                Paste a connection string or follow a provider guide. Test
                credentials and TLS, then explore actual tables, fields and
                relationships.
              </p>
            </div>
          </li>
          <li>
            <div>
              <h3>Ask, refine and review</h3>
              <p>
                Get SQL in the right dialect or a supported native document
                query. Check joins, filters and date boundaries before selecting
                Run.
              </p>
            </div>
          </li>
          <li>
            <div>
              <h3>Measure a proposed change</h3>
              <p>
                Inspect plans and indexes where available. Supported
                disposable-copy benchmarks compare results, latency, variability
                and index costs.
              </p>
            </div>
          </li>
        </ol>
      </section>
      <section className="q-engine-section">
        <div>
          <h2>Nine engines, explicit limits</h2>
          <p>
            Providers host databases. Engines determine the query language and
            available evidence. See exactly what was tested locally, in
            emulators or on a hosted service.
          </p>
          <a href="#matrix" className="q-inline-link">
            View the support matrix
          </a>
        </div>
        <div className="q-engine-grid">
          {catalog?.engines.map((e) => (
            <a href="#matrix" key={e.id}>
              <Database size={18} />
              <strong>{e.name}</strong>
              <small>
                {e.verification.status.startsWith("Verified")
                  ? "Local / emulator checks passed"
                  : "Verification pending"}
              </small>
            </a>
          )) || <p role="status">Loading support evidence…</p>}
        </div>
      </section>
      <section className="q-benchmark-teaser">
        <FlaskConical size={27} />
        <div>
          <h2>A performance claim needs a method</h2>
          <p>
            Explore actual PostgreSQL reports, independent correctness fixtures
            and measured timing distributions. A recommendation becomes an
            improvement only when the comparison supports it.
          </p>
        </div>
        <a className="q-button secondary" href="#experiments">
          Open experiments
        </a>
      </section>
    </main>
  );
}
