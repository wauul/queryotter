import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Code2,
  Database,
  Download,
  FileText,
  FlaskConical,
  Gauge,
  GitBranch,
  History,
  Layers,
  LockKeyhole,
  Menu,
  Play,
  Plus,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Terminal,
  Unplug,
  X,
  ExternalLink,
} from "lucide-react";
import type { Example, Report, Job, Latency, PlanNode } from "./types";
import { SQLDiff } from "./SQLDiff";
import "./style.css";

async function api<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch("/api" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let d = await r.json();
  if (!r.ok)
    throw new Error(
      typeof d.detail === "string"
        ? d.detail
        : "Please check your input and try again.",
    );
  return d;
}
const ms = (v?: number | null) =>
  v === undefined || v === null
    ? "Not measured"
    : v < 1
      ? v.toFixed(3) + " ms"
      : v.toFixed(2) + " ms";
function Otter({ small = false }: { small?: boolean }) {
  return (
    <svg
      width={small ? 34 : 58}
      height={small ? 34 : 58}
      viewBox="0 0 64 64"
      fill="none"
      aria-label="QueryOtter mascot"
    >
      <rect width="64" height="64" rx="18" fill="#d9eee7" />
      <ellipse cx="32" cy="42" rx="19" ry="16" fill="#9b7558" />
      <circle cx="17" cy="21" r="8" fill="#9b7558" />
      <circle cx="47" cy="21" r="8" fill="#9b7558" />
      <ellipse cx="32" cy="31" rx="22" ry="19" fill="#b9916c" />
      <ellipse cx="32" cy="37" rx="15" ry="10" fill="#ead5bb" />
      <circle cx="24" cy="27" r="2.5" fill="#20342c" />
      <circle cx="40" cy="27" r="2.5" fill="#20342c" />
      <path d="M28 33Q32 30 36 33L32 37Z" fill="#20342c" />
      <path
        d="M25 39q7 7 14 0M15 34l8 2m-8 4 8-1m26-5-8 2m8 4-8-1"
        stroke="#614a37"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="m30 48-7 6m11-6 7 6"
        stroke="#7b583f"
        strokeWidth="5"
        strokeLinecap="round"
      />
    </svg>
  );
}
function Badge({
  children,
  kind = "green",
}: {
  children: React.ReactNode;
  kind?: string;
}) {
  return <span className={"badge " + kind}>{children}</span>;
}
function Plan({ nodes }: { nodes: PlanNode[] }) {
  return (
    <div className="plan-tree">
      {nodes.map((n, i) => (
        <div key={i} className="plan-node" style={{ marginLeft: n.depth * 18 }}>
          <GitBranch size={15} />
          <div>
            <strong>{n["Node Type"]}</strong>
            <span>
              {n["Relation Name"] || n["Index Name"] || "PostgreSQL plan node"}
            </span>
          </div>
          <div className="node-number">
            {n["Actual Total Time"] !== undefined
              ? ms(n["Actual Total Time"])
              : "cost " + n["Total Cost"]}
            <span>{n["Actual Rows"] ?? n["Plan Rows"]} rows</span>
          </div>
        </div>
      ))}
    </div>
  );
}
function Distribution({ a, b }: { a: Latency; b?: Latency }) {
  const max = Math.max(...a.samples_ms, ...(b?.samples_ms || [])) || 1;
  return (
    <div className="distribution">
      {[
        { label: "Original", data: a, color: "#a0acaa" },
        { label: "Optimized", data: b, color: "#218575" },
      ].map(
        (s, i) =>
          s.data && (
            <div className="distribution-row" key={s.label}>
              <span>{s.label}</span>
              <div className="dot-track">
                {s.data.samples_ms.map((n, j) => (
                  <i
                    key={j}
                    style={{
                      left: `${(n / max) * 91 + 3}%`,
                      top: 8 + (j % 3) * 6,
                      background: s.color,
                    }}
                    title={ms(n)}
                  />
                ))}
                <b
                  style={{
                    left: `${(s.data.median_ms / max) * 91 + 3}%`,
                    borderColor: s.color,
                  }}
                />
              </div>
              <strong>{ms(s.data.median_ms)}</strong>
            </div>
          ),
      )}
      <div className="distribution-axis">
        <span>0 ms</span>
        <span>{max.toFixed(2)} ms</span>
      </div>
      <small>Each dot is a measured run. Vertical marks show medians.</small>
    </div>
  );
}
function App() {
  const [examples, setExamples] = useState<Example[]>([]),
    [selected, setSelected] = useState("customer-orders"),
    [sql, setSql] = useState(""),
    [report, setReport] = useState<Report | null>(null),
    [job, setJob] = useState<Job | null>(null),
    [history, setHistory] = useState<Job[]>([]),
    [error, setError] = useState(""),
    [tab, setTab] = useState("Overview"),
    [page, setPage] = useState("Investigate"),
    [connectionOpen, setConnectionOpen] = useState(false),
    [authenticated, setAuthenticated] = useState(false),
    [online, setOnline] = useState(false),
    [password, setPassword] = useState(""),
    [connLabel, setConnLabel] = useState(""),
    [connUrl, setConnUrl] = useState(""),
    [connections, setConnections] = useState<{ id: string; label: string }[]>(
      [],
    ),
    [connectionId, setConnectionId] = useState(""),
    [busy, setBusy] = useState(false),
    [evaluation, setEvaluation] = useState<any>(null),
    [mobile, setMobile] = useState(false);
  const schemaNames = connectionId
    ? report?.conditions.mode === "live plan-only"
      ? [...new Set(report.schema.columns.map((c) => c[0]))]
      : []
    : ["customers", "orders", "items"];
  const current = examples.find((e) => e.id === selected),
    active = job && ["queued", "running"].includes(job.state);
  const reportRef = useRef(0);
  useEffect(() => {
    fetch("/examples.json")
      .then((r) => r.json())
      .then(setExamples);
    fetch("/evaluation.json")
      .then((r) => (r.ok ? r.json() : null))
      .then(setEvaluation)
      .catch(() => {});
    api<{ authenticated: boolean }>("/session")
      .then((s) => {
        setOnline(true);
        setAuthenticated(s.authenticated);
        return api<Job[]>("/jobs");
      })
      .then(setHistory)
      .catch(() => setOnline(false));
  }, []);
  useEffect(() => {
    if (!current) return;
    setSql(current.sql);
    setReport(null);
    setError("");
    const n = ++reportRef.current;
    if (connectionId) return;
    fetch("/reports/" + current.id + ".json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (n === reportRef.current) setReport(d);
      })
      .catch(() => {});
  }, [selected, examples, connectionId]);
  useEffect(() => {
    if (!active || !job) return;
    const id = job.id;
    const interval = setInterval(() => {
      api<Job>("/jobs/" + id)
        .then((j) => {
          setJob(j);
          if (j.report) {
            setReport(j.report);
            setSql(j.report.query);
          }
          if (!["queued", "running"].includes(j.state)) {
            if (j.error) setError(j.error);
            api<Job[]>("/jobs").then(setHistory);
          }
        })
        .catch((e) => setError(e.message));
    }, 800);
    return () => clearInterval(interval);
  }, [job?.id, active]);
  useEffect(() => {
    if (authenticated)
      api<{ id: string; label: string }[]>("/connections")
        .then(setConnections)
        .catch(() => {});
  }, [authenticated]);
  async function investigate() {
    setError("");
    setBusy(true);
    try {
      if (!online)
        throw new Error(
          "The investigation worker is offline. Published reports are available below.",
        );
      const custom = sql.trim() !== current?.sql.trim();
      const j = await api<Job>("/jobs", {
        case_id: custom ? null : selected,
        query: custom ? sql : null,
        connection_id: connectionId || null,
        request_key: crypto.randomUUID(),
      });
      setJob(j);
      setReport(null);
      setTab("Overview");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function login() {
    setError("");
    try {
      await api("/login", { password });
      setPassword("");
      setAuthenticated(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function addConnection() {
    setError("");
    setBusy(true);
    try {
      const c = await api<{ id: string; label: string }>("/connections", {
        label: connLabel,
        url: connUrl,
      });
      setConnections([...connections, c]);
      setConnUrl("");
      setConnLabel("");
      setConnectionId(c.id);
      setConnectionOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function download() {
    if (!report) return;
    const a = document.createElement("a");
    a.href =
      job?.report === report
        ? `/api/jobs/${job.id}/report`
        : `/reports/${selected}.json?download=1`;
    a.download = `queryotter-${selected}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  const best = report?.best;
  const stages = [
    "inspect",
    "explain",
    "hypothesize",
    "experiment",
    "validate",
    "benchmark",
    "recommend",
  ];
  const last = job?.events.at(-1)?.stage;
  const stageIndex = stages.indexOf(last || "");
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <a className="brand" href="/" onClick={(e) => e.preventDefault()}>
          <Otter small />
          <span>
            Query<span className="brand-otter">Otter</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">Q</span>
          <div>
            QueryOtter workspace<small>Personal workspace</small>
          </div>
          <ChevronDown size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {[
            { name: "Investigate", icon: FlaskConical },
            { name: "Run history", icon: History },
            { name: "Evaluation", icon: Gauge },
          ].map((n) => (
            <button
              key={n.name}
              className={page === n.name ? "selected" : ""}
              onClick={() => {
                setPage(n.name);
                setMobile(false);
              }}
            >
              <n.icon size={18} />
              {n.name}
              {n.name === "Investigate" && (
                <span className="nav-pill">⌘ K</span>
              )}
            </button>
          ))}
        </nav>
        <div className="nav-label database-label">
          DATABASES{" "}
          <button
            aria-label="Add database"
            onClick={() => setConnectionOpen(true)}
          >
            <Plus size={15} />
          </button>
        </div>
        <button
          className="database-nav"
          onClick={() => {
            setConnectionId("");
            setPage("Investigate");
          }}
        >
          <span className="status-dot" />
          <div>
            OtterMart<small>Synthetic PostgreSQL</small>
          </div>
          <Badge kind="neutral">DEMO</Badge>
        </button>
        {connections.map((c) => (
          <button
            className="database-nav"
            key={c.id}
            onClick={() => {
              setConnectionId(c.id);
              setPage("Investigate");
            }}
          >
            <Database size={16} />
            <div>
              {c.label}
              <small>Live · plans only</small>
            </div>
          </button>
        ))}
        <div className="sidebar-bottom">
          <div className="safety-note">
            <ShieldCheck size={20} />
            <strong>A safe place to experiment</strong>
            <p>
              Every index is tested in a disposable database. Your production
              stays yours.
            </p>
            <button onClick={() => setPage("Evaluation")}>
              Explore our methodology <ArrowUpRight size={14} />
            </button>
          </div>
          <button className="profile" onClick={() => setConnectionOpen(true)}>
            <span className="avatar">{authenticated ? "W" : "G"}</span>
            <div>
              {authenticated ? "Workspace owner" : "Demo explorer"}
              <small>
                {authenticated ? "Authenticated session" : "No sign-in needed"}
              </small>
            </div>
            <Settings2 size={17} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(!mobile)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div>
            <span className={"worker-status " + (online ? "" : "offline")}>
              <i />
              {online ? "Worker connected" : "Published reports available"}
            </span>
            <a
              href="https://github.com/wauul/queryotter"
              target="_blank"
              rel="noreferrer"
            >
              Source <ExternalLink size={13} />
            </a>
          </div>
        </header>
        <main>
          {page === "Investigate" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    <span /> POSTGRESQL QUERY INVESTIGATOR
                  </div>
                  <h1>A little curiosity. A faster query.</h1>
                  <p>
                    Find the bottleneck. Test the possibilities. Follow the
                    evidence.
                  </p>
                </div>
                <button
                  className="outline"
                  onClick={() => setConnectionOpen(true)}
                >
                  <Database size={16} />
                  {authenticated ? "Connect database" : "Connect your database"}
                  <ArrowUpRight size={15} />
                </button>
              </div>
              <div className="demo-banner">
                <div className="demo-symbol">
                  <FlaskConical size={19} />
                </div>
                <div>
                  <strong>
                    {connectionId
                      ? "Live connection · estimates only"
                      : "You're in the OtterMart sandbox"}
                  </strong>
                  <span>
                    {connectionId
                      ? "Metadata and non-executing EXPLAIN. No measurements or indexes."
                      : "370,000 synthetic records. Real PostgreSQL. Real measurements."}
                  </span>
                </div>
                <Badge kind="teal">
                  {connectionId ? "Read-only" : "Safe to explore"}
                </Badge>
              </div>
              <div className="editor-grid">
                <section className="panel editor-panel">
                  <div className="panel-heading">
                    <div>
                      <Code2 size={18} />
                      <h2>Query workspace</h2>
                    </div>
                    <span className="tiny-label">PostgreSQL</span>
                  </div>
                  <div className="editor-toolbar">
                    <span>Try an example</span>
                    <select
                      aria-label="Slow query example"
                      disabled={!!active}
                      value={selected}
                      onChange={(e) => setSelected(e.target.value)}
                    >
                      {examples.map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.title}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="sql-editor">
                    <div className="line-numbers">
                      {sql.split("\n").map((_, i) => (
                        <span key={i}>{i + 1}</span>
                      ))}
                    </div>
                    <textarea
                      aria-label="SQL editor"
                      spellCheck={false}
                      value={sql}
                      onChange={(e) => setSql(e.target.value)}
                      onKeyDown={(e) => {
                        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                          e.preventDefault();
                          investigate();
                        }
                      }}
                    />
                  </div>
                  <div className="editor-footer">
                    <span>
                      <ShieldCheck size={14} />{" "}
                      {connectionId
                        ? "Live · non-executing EXPLAIN"
                        : "SELECT only · disposable experiments"}
                    </span>
                    <div>
                      {!!active ? (
                        <button
                          className="outline small"
                          onClick={() =>
                            api<Job>("/jobs/" + job!.id + "/cancel", {}).then(
                              setJob,
                            )
                          }
                        >
                          <Square size={13} />
                          Cancel
                        </button>
                      ) : (
                        <button
                          className="primary"
                          onClick={investigate}
                          disabled={busy || !sql}
                        >
                          <Sparkles size={16} />
                          {busy ? "Starting…" : "Investigate query"}
                          <span>⌘ ↵</span>
                        </button>
                      )}
                    </div>
                  </div>
                </section>
                <section className="panel schema-panel">
                  <div className="panel-heading">
                    <div>
                      <Database size={17} />
                      <h2>
                        {connectionId
                          ? connections.find((c) => c.id === connectionId)
                              ?.label
                          : "OtterMart"}
                      </h2>
                    </div>
                    <span className="status-dot" />
                  </div>
                  <div className="db-meta">
                    <span>
                      PostgreSQL{" "}
                      {report?.schema.version ||
                        (connectionId ? "Not inspected" : "18")}
                    </span>
                    <Badge kind="neutral">
                      {connectionId ? "LIVE" : "SEEDED"}
                    </Badge>
                  </div>
                  {schemaNames.map((name, i) => (
                    <details key={name} open={name === "orders"}>
                      <summary>
                        <ChevronRight size={13} />
                        <Layers size={14} />
                        <strong>{name}</strong>
                        <span>
                          {connectionId
                            ? "Size not measured"
                            : ["10k", "120k", "240k"][i] + " rows"}
                        </span>
                      </summary>
                      <div className="schema-columns">
                        {(
                          report?.schema.columns.filter(
                            (c) => c[0] === name,
                          ) || [
                            [name, "id", "integer"],
                            [name, "customer_id", "integer"],
                            [name, "status", "text"],
                            [name, "total", "numeric"],
                            [name, "created_at", "timestamp"],
                          ]
                        ).map((c) => (
                          <div key={c[1]}>
                            <span>
                              {c[1] === "id" ? "⌑" : "·"} {c[1]}
                            </span>
                            <small>{c[2]}</small>
                          </div>
                        ))}
                      </div>
                    </details>
                  ))}
                  <div className="schema-foot">
                    <LockKeyhole size={13} />
                    {connectionId
                      ? "No execution or schema changes"
                      : "Seed 17 · isolated per investigation"}
                  </div>
                </section>
              </div>
              {error && (
                <div className="error" role="alert">
                  <Unplug size={18} />
                  <span>{error}</span>
                  <button
                    aria-label="Dismiss error"
                    onClick={() => setError("")}
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
              {!!active && (
                <section className="panel running-panel">
                  <div>
                    <span className="spinner" />
                    <h2>Following the evidence…</h2>
                    <Badge kind="teal">{job?.state}</Badge>
                  </div>
                  <div className="stages">
                    {stages.map((s, i) => (
                      <span key={s} className={i <= stageIndex ? "done" : ""}>
                        {i < stageIndex ? (
                          <Check size={13} />
                        ) : (
                          <span className="stage-dot" />
                        )}
                        {s}
                      </span>
                    ))}
                  </div>
                  <p>
                    {job?.events.at(-1)?.message ||
                      "Queued for the single-concurrency investigation worker."}
                  </p>
                </section>
              )}
              {report ? (
                <>
                  <div className="results-heading">
                    <div>
                      <h2>Investigation results</h2>
                      <Badge kind={best ? "green" : "amber"}>
                        {best ? (
                          <>
                            <CheckCircle2 size={12} />
                            Verified improvement
                          </>
                        ) : (
                          "No verified improvement"
                        )}
                      </Badge>
                    </div>
                    <div>
                      <span className="report-origin">
                        {job?.report === report
                          ? "Fresh investigation"
                          : "Published measured report"}
                      </span>
                      <button className="outline small" onClick={download}>
                        <Download size={14} />
                        Export report
                      </button>
                    </div>
                  </div>
                  <div className="metric-grid">
                    <div className="metric-card">
                      <span>
                        <Clock3 size={15} />
                        Original latency
                      </span>
                      <strong>{ms(report.original?.median_ms)}</strong>
                      <small>Median PostgreSQL execution time</small>
                    </div>
                    <div className="metric-card optimized">
                      <span>
                        <Sparkles size={15} />
                        Optimized latency
                      </span>
                      <strong>{ms(best?.optimized?.median_ms)}</strong>
                      <small>
                        {best
                          ? "Warm cache · 7 measured repetitions"
                          : "No candidate selected"}
                      </small>
                    </div>
                    <div className="metric-card">
                      <span>
                        <Gauge size={15} />
                        Measured speedup
                      </span>
                      <strong>
                        {best?.speedup ? (
                          <>
                            {best.speedup}
                            <em>×</em>
                            <Badge>
                              <ArrowDown size={12} />
                              {(
                                (1 -
                                  best.optimized!.median_ms /
                                    report.original!.median_ms) *
                                100
                              ).toFixed(1)}
                              %
                            </Badge>
                          </>
                        ) : (
                          "—"
                        )}
                      </strong>
                      <small>
                        {best
                          ? `${ms(report.original!.median_ms - best.optimized!.median_ms)} saved per execution`
                          : "No reliable gain established"}
                      </small>
                    </div>
                    <div className="metric-card">
                      <span>
                        <ShieldCheck size={15} />
                        Correctness checks
                      </span>
                      <strong>
                        {best ? (
                          <>
                            {best.correctness.datasets.length}
                            <em> / {best.correctness.datasets.length}</em>
                            <CheckCircle2 size={20} />
                          </>
                        ) : (
                          "—"
                        )}
                      </strong>
                      <small>
                        {best
                          ? "Seeded & edge fixtures passed"
                          : "See candidate validation details"}
                      </small>
                    </div>
                  </div>
                  <section className="panel report-panel">
                    <div className="tabs" role="tablist">
                      {[
                        "Overview",
                        "Query plans",
                        "SQL & indexes",
                        "Correctness",
                        "Run details",
                      ].map((t) => (
                        <button
                          role="tab"
                          aria-selected={t === tab}
                          key={t}
                          onClick={() => setTab(t)}
                          className={tab === t ? "active" : ""}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                    <div className="tab-content">
                      {tab === "Overview" && (
                        <div className="overview-grid">
                          <div>
                            <div className="section-title">
                              <span className="icon-box">
                                <Sparkles size={18} />
                              </span>
                              <div>
                                <h3>
                                  {best
                                    ? "A better path through your data"
                                    : "What the investigation found"}
                                </h3>
                                <span>
                                  Model hypothesis, tested by PostgreSQL
                                </span>
                              </div>
                            </div>
                            <p className="diagnosis">{report.diagnosis}</p>
                            {best && (
                              <div className="finding">
                                <CheckCircle2 size={18} />
                                <div>
                                  <strong>{best.name}</strong>
                                  <p>{best.hypothesis}</p>
                                </div>
                              </div>
                            )}
                            <div className="candidate-list">
                              <h4>Candidates tested</h4>
                              {report.candidates.length ? (
                                report.candidates.map((c) => (
                                  <div key={c.name}>
                                    <span>{c.name}</span>
                                    <Badge
                                      kind={
                                        c.status === "verified improvement"
                                          ? "green"
                                          : c.status === "rejected"
                                            ? "red"
                                            : "amber"
                                      }
                                    >
                                      {c.status}
                                    </Badge>
                                  </div>
                                ))
                              ) : (
                                <p>
                                  The agent proposed no justified improvement.
                                  Retain the original query.
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="benchmark-box">
                            <h3>Latency, with the spread</h3>
                            <p>Execution time · milliseconds · warm cache</p>
                            {report.original && (
                              <Distribution
                                a={report.original}
                                b={best?.optimized}
                              />
                            )}
                            <div className="benchmark-facts">
                              <span>
                                Measured runs
                                <strong>
                                  {String(
                                    report.conditions.repetitions ||
                                      "Not measured",
                                  )}
                                </strong>
                              </span>
                              <span>
                                Original MAD
                                <strong>{ms(report.original?.mad_ms)}</strong>
                              </span>
                              <span>
                                Optimized MAD
                                <strong>{ms(best?.optimized?.mad_ms)}</strong>
                              </span>
                            </div>
                            <div className="quiet-note">
                              <Activity size={15} />
                              <span>
                                End-to-end investigation:{" "}
                                {report.usage.runtime_seconds}s. SQL latency
                                excludes model and network time.
                              </span>
                            </div>
                          </div>
                        </div>
                      )}
                      {tab === "Query plans" && (
                        <div className="plans-grid">
                          <div>
                            <h3>
                              Before <Badge kind="neutral">Original</Badge>
                            </h3>
                            <Plan nodes={report.plan_before} />
                          </div>
                          <div>
                            <h3>
                              After{" "}
                              <Badge>
                                {best ? "Selected candidate" : "Not available"}
                              </Badge>
                            </h3>
                            {best?.plan ? (
                              <Plan nodes={best.plan} />
                            ) : (
                              <p>No verified candidate plan to display.</p>
                            )}
                          </div>
                        </div>
                      )}
                      {tab === "SQL & indexes" && (
                        <>
                          <SQLDiff
                            original={report.query}
                            candidate={best?.query || report.query}
                            verified={!!best}
                          />
                          <h3 className="migration-title">
                            Reviewable index migration
                          </h3>
                          {best?.indexes.length ? (
                            <>
                              <pre className="index-code">
                                {best.indexes.map((s) => s + ";").join("\n")}
                              </pre>
                              <div className="index-tradeoffs">
                                <span>
                                  <strong>
                                    {(best.index_bytes! / 1024 / 1024).toFixed(
                                      2,
                                    )}{" "}
                                    MB
                                  </strong>
                                  Additional index storage
                                </span>
                                <span>
                                  <strong>{ms(best.index_build_ms)}</strong>
                                  Index construction time
                                </span>
                                <p>
                                  {best.tradeoff} Review names and deployment
                                  locks. For production, schedule separately and
                                  consider CREATE INDEX CONCURRENTLY outside a
                                  transaction.
                                </p>
                              </div>
                            </>
                          ) : (
                            <p>
                              No verified index migration. Unverified
                              suggestions are available in the report export.
                            </p>
                          )}
                        </>
                      )}
                      {tab === "Correctness" && (
                        <>
                          <div className="section-title">
                            <ShieldCheck size={22} />
                            <div>
                              <h3>Test the meaning, then test the speed</h3>
                              <span>
                                Types, values, NULLs, duplicates and ordered
                                output
                              </span>
                            </div>
                          </div>
                          {report.candidates.map((c) => (
                            <div className="correctness-group" key={c.name}>
                              <h4>
                                {c.name}{" "}
                                <Badge
                                  kind={
                                    c.correctness.passed ? "green" : "amber"
                                  }
                                >
                                  {c.correctness.passed
                                    ? "Passed"
                                    : "Not verified"}
                                </Badge>
                              </h4>
                              {c.correctness.datasets.map((d, i) => (
                                <div key={i}>
                                  <span>
                                    {d.size === 0
                                      ? "Empty tables"
                                      : d.edges
                                        ? "NULLs, duplicates, skew & boundary values"
                                        : "Benchmark dataset"}
                                  </span>
                                  <span>
                                    Seed {d.seed} · {d.size.toLocaleString()}{" "}
                                    orders
                                  </span>
                                  <Badge kind={d.passed ? "green" : "red"}>
                                    {d.passed ? "Passed" : "Failed"}
                                  </Badge>
                                </div>
                              ))}
                              {c.reason && <p>{c.reason}</p>}
                            </div>
                          ))}
                          <div className="empirical-note">
                            <ShieldCheck size={17} />
                            <p>
                              {String(report.conditions.equivalence)} Equality
                              on these fixtures is evidence, not a proof over
                              all possible databases.
                            </p>
                          </div>
                        </>
                      )}
                      {tab === "Run details" && (
                        <>
                          <div className="run-facts">
                            {Object.entries(report.usage).map(
                              ([key, value]) => (
                                <div key={key}>
                                  <span>{key.replaceAll("_", " ")}</span>
                                  <strong>
                                    {value === null
                                      ? "Unavailable"
                                      : String(value)}
                                  </strong>
                                </div>
                              ),
                            )}
                          </div>
                          <div className="timeline">
                            {(job?.report === report ? job.events : []).map(
                              (e, i) => (
                                <div key={i}>
                                  <CheckCircle2 size={15} />
                                  <span>{e.stage}</span>
                                  <p>{e.message}</p>
                                </div>
                              ),
                            )}
                          </div>
                          <h3>Experiment conditions</h3>
                          <div className="conditions">
                            {Object.entries(report.conditions).map(
                              ([key, value]) => (
                                <div key={key}>
                                  <strong>{key.replaceAll("_", " ")}</strong>
                                  <span>
                                    {typeof value === "object"
                                      ? JSON.stringify(value)
                                      : String(value)}
                                  </span>
                                </div>
                              ),
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  </section>
                  <div className="results-footer">
                    <ShieldCheck size={15} />
                    <span>
                      Measured on synthetic data. Empirical checks are not a
                      proof of SQL equivalence.
                    </span>
                    <span>
                      {report.usage.provider} · {report.usage.model}
                    </span>
                  </div>
                </>
              ) : (
                !active && (
                  <div className="empty-state">
                    <Otter />
                    <h3>Good questions lead to better queries.</h3>
                    <p>
                      Choose a slow-query example and let QueryOtter
                      investigate.
                      <br />
                      Findings appear here as measured evidence.
                    </p>
                  </div>
                )
              )}
            </>
          ) : page === "Run history" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">YOUR INVESTIGATIONS</div>
                  <h1>Every experiment leaves a trail.</h1>
                  <p>
                    Reports and events persist in the worker's durable job
                    store.
                  </p>
                </div>
              </div>
              <section className="panel history-list">
                {history.length ? (
                  history.map((j) => (
                    <button
                      key={j.id}
                      onClick={() => {
                        setJob(j);
                        if (j.report) {
                          setReport(j.report);
                          setSql(j.report.query);
                        }
                        setPage("Investigate");
                      }}
                    >
                      <span className="icon-box">
                        <FileText size={20} />
                      </span>
                      <div>
                        <strong>
                          {examples.find((e) => e.id === j.case_id)?.title ||
                            "Custom investigation"}
                        </strong>
                        <small>
                          {new Date(j.created * 1000).toLocaleString()} ·{" "}
                          {j.id.slice(0, 8)}
                        </small>
                      </div>
                      <Badge kind={j.state === "completed" ? "green" : "amber"}>
                        {j.state}
                      </Badge>
                      <ChevronRight size={18} />
                    </button>
                  ))
                ) : (
                  <div className="empty-state">
                    <History size={36} />
                    <h3>Your investigation trail starts here.</h3>
                    <p>Run an example to create a persisted report.</p>
                    <button
                      className="primary"
                      onClick={() => setPage("Investigate")}
                    >
                      Investigate a query <ArrowRight size={15} />
                    </button>
                  </div>
                )}
              </section>
            </>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">REPRODUCIBLE BY DESIGN</div>
                  <h1>Evidence. Including the awkward bits.</h1>
                  <p>
                    All cases are published, including regressions, rejections
                    and inconclusive runs.
                  </p>
                </div>
                <a className="outline" href="/evaluation.json" download>
                  <Download size={15} />
                  Evaluation data
                </a>
              </div>
              <div className="evaluation-intro">
                <div>
                  <ShieldCheck size={24} />
                  <h3>Independent semantic checks</h3>
                  <p>
                    Result types, multisets and ordered sequences are compared
                    by deterministic code on four fixtures.
                  </p>
                </div>
                <div>
                  <Gauge size={24} />
                  <h3>Comparable measurements</h3>
                  <p>
                    Two warm-up rounds, seven measured repetitions, alternating
                    execution order, medians and MAD.
                  </p>
                </div>
                <div>
                  <Code2 size={24} />
                  <h3>Two honest baselines</h3>
                  <p>
                    The original SELECT and a fixed, deterministic index
                    recommendation defined in the case manifest.
                  </p>
                </div>
              </div>
              {evaluation ? (
                <>
                  <div className="evaluation-metrics">
                    {Object.entries(evaluation.summary).map(([k, v]) => (
                      <div key={k}>
                        <strong>
                          {typeof v === "number"
                            ? v.toLocaleString()
                            : String(v)}
                        </strong>
                        <span>{k.replaceAll("_", " ")}</span>
                      </div>
                    ))}
                  </div>
                  <section className="panel evaluation-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Benchmark case</th>
                          <th>Outcome</th>
                          <th>Original</th>
                          <th>Selected</th>
                          <th>Baseline</th>
                          <th>Correctness</th>
                        </tr>
                      </thead>
                      <tbody>
                        {evaluation.cases.map((c: any) => (
                          <tr key={c.id}>
                            <td>
                              <strong>{c.title}</strong>
                              <small>{c.category}</small>
                            </td>
                            <td>
                              <Badge
                                kind={
                                  c.outcome === "verified improvement"
                                    ? "green"
                                    : c.outcome === "rejected"
                                      ? "neutral"
                                      : "amber"
                                }
                              >
                                {c.outcome}
                              </Badge>
                            </td>
                            <td>{ms(c.original_ms)}</td>
                            <td>{ms(c.best_ms)}</td>
                            <td>{ms(c.baseline_ms)}</td>
                            <td>
                              {c.correctness === null
                                ? "Not executed"
                                : c.correctness
                                  ? "Passed"
                                  : "Failed"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </section>
                  <div className="empirical-note">
                    <p>{evaluation.methodology}</p>
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <p>Evaluation data has not been published yet.</p>
                </div>
              )}
            </>
          )}
          <footer className="app-footer">
            <span>
              QueryOtter <span>·</span> Curiosity, with receipts.
            </span>
            <span>
              Built for PostgreSQL <span>·</span> Never changes production
            </span>
          </footer>
        </main>
      </div>
      {connectionOpen && (
        <div
          className="modal-backdrop"
          onClick={() => setConnectionOpen(false)}
        >
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Database connection setup"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label="Close setup"
              onClick={() => setConnectionOpen(false)}
            >
              <X size={20} />
            </button>
            <span className="icon-box">
              <Database size={25} />
            </span>
            <h2>
              {authenticated
                ? "Connect a read-only database"
                : "Your database. Your workspace."}
            </h2>
            <p>
              {authenticated
                ? "Live connections inspect metadata and non-executing plans. For measured experiments, use sanitized data in the disposable worker."
                : "The public sandbox needs no account. Owner sign-in unlocks private queries and encrypted connections."}
            </p>
            {!authenticated ? (
              <>
                <label>
                  Owner password
                  <input
                    aria-label="Owner password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && login()}
                  />
                </label>
                <button className="primary full" onClick={login}>
                  Sign in <ArrowRight size={16} />
                </button>
                <small className="modal-help">
                  Self-hosted owner password is configured in the worker's
                  private environment. Public registration is not enabled.
                </small>
              </>
            ) : (
              <>
                <label>
                  Connection name
                  <input
                    value={connLabel}
                    onChange={(e) => setConnLabel(e.target.value)}
                    placeholder="Analytics replica"
                  />
                </label>
                <label>
                  PostgreSQL connection URL
                  <input
                    type="password"
                    autoComplete="off"
                    value={connUrl}
                    onChange={(e) => setConnUrl(e.target.value)}
                    placeholder="postgresql://readonly:…@host/db?sslmode=verify-full"
                  />
                </label>
                <div className="quiet-note">
                  <LockKeyhole size={18} />
                  <span>
                    Encrypted at rest. Read-only role required. Remote
                    connections must verify TLS certificates.
                  </span>
                </div>
                <button
                  className="primary full"
                  onClick={addConnection}
                  disabled={busy || !connUrl || !connLabel}
                >
                  {busy ? "Checking connection…" : "Validate & save connection"}
                  <ArrowRight size={16} />
                </button>
                <button
                  className="text-button"
                  onClick={() =>
                    api("/logout", {}).then(() => {
                      setAuthenticated(false);
                      setConnections([]);
                      setConnectionId("");
                    })
                  }
                >
                  Sign out
                </button>
              </>
            )}
            {error && (
              <p className="modal-error" role="alert">
                {error}
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
