import { useLanguage } from "./Language";
import React, { useState, useEffect, useRef } from "react";
import {
  Activity,
  ArrowDown,
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
  Square,
  Terminal,
  Unplug,
  X,
  ExternalLink,
} from "lucide-react";
import type { Example, Report, Job, Latency, PlanNode } from "./types";
import { SQLDiff } from "./SQLDiff";
import "./style.css";
import { Otter } from "./Otter";
import { monitoredFetch } from "./monitoring";

async function api<T>(path: string, body?: unknown): Promise<T> {
  return monitoredFetch("/api" + path, body) as Promise<T>;
}
const ms = (v?: number | null) =>
  v === undefined || v === null
    ? "Not measured"
    : v < 1
      ? v.toFixed(3) + " ms"
      : v.toFixed(2) + " ms";
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
  const { t: tr } = useLanguage();

  return (
    <div className="plan-tree">
      {nodes.map((n, i) => (
        <div key={i} className="plan-node" style={{ marginLeft: n.depth * 18 }}>
          <GitBranch size={15} />
          <div>
            <strong>{n["Node Type"]}</strong>
            <span>
              {n["Relation Name"] ||
                n["Index Name"] ||
                tr("PostgreSQL plan node")}
            </span>
          </div>
          <div className="node-number">
            {n["Actual Total Time"] !== undefined
              ? ms(n["Actual Total Time"])
              : "cost " + n["Total Cost"]}
            <span>
              {n["Actual Rows"] ?? n["Plan Rows"]}
              {tr(" rows")}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
function Distribution({ a, b }: { a: Latency; b?: Latency }) {
  const { t: tr } = useLanguage();

  const max = Math.max(...a.samples_ms, ...(b?.samples_ms || [])) || 1;
  return (
    <div className="distribution">
      {[
        { label: "Original", data: a, color: "var(--muted)" },
        { label: "Optimized", data: b, color: "var(--accent)" },
      ].map(
        (s, i) =>
          s.data && (
            <div className="distribution-row" key={tr(s.label)}>
              <span>{tr(s.label)}</span>
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
        <span>{tr("0 ms")}</span>
        <span>
          {max.toFixed(2)}
          {tr(" ms")}
        </span>
      </div>
      <small>
        {tr("Each dot is a measured run. Vertical marks show medians.")}
      </small>
    </div>
  );
}
export default function LegacyOptimizer({
  portfolioOnly = false,
}: {
  portfolioOnly?: boolean;
}) {
  const { t: tr, language } = useLanguage();
  const locale = language === "fr" ? "fr-FR" : "en-GB";

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
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!mobile) return;
    document
      .getElementById("q-experiment-navigation")
      ?.querySelector<HTMLButtonElement>("nav button")
      ?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobile(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [mobile]);
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
        setAuthenticated(!portfolioOnly && s.authenticated);
        return api<Job[]>("/jobs");
      })
      .then(setHistory)
      .catch(() => setOnline(false));
  }, [portfolioOnly]);
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
      <aside
        id="q-experiment-navigation"
        aria-label={tr("Experiment navigation")}
        className={"sidebar " + (mobile ? "open" : "")}
      >
        <a className="brand" href="#home">
          <Otter small />
          <span>
            Query<span className="brand-otter">Otter</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">Q</span>
          <div>
            {tr("QueryOtter experiments")}
            <small>{tr("Synthetic benchmark portfolio")}</small>
          </div>
          <ChevronDown size={15} />
        </div>
        <div className="nav-label">{tr("Experiments")}</div>
        <nav>
          {[
            { name: "Investigate", icon: FlaskConical },
            { name: "Run history", icon: History },
            { name: "Evaluation", icon: Gauge },
          ].map((n) => (
            <button
              key={tr(n.name)}
              className={page === n.name ? "selected" : ""}
              onClick={() => {
                setPage(n.name);
                setMobile(false);
              }}
            >
              <n.icon size={18} />
              {tr(n.name)}
              {n.name === "Investigate" && (
                <span className="nav-pill">{tr("⌘ K")}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="nav-label database-label">
          {tr("Databases")}{" "}
          {!portfolioOnly && (
            <button
              aria-label={tr("Add database")}
              onClick={() => setConnectionOpen(true)}
            >
              <Plus size={15} />
            </button>
          )}
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
            {tr("OtterMart")}
            <small>{tr("Synthetic PostgreSQL")}</small>
          </div>
          <Badge kind="neutral">{tr("DEMO")}</Badge>
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
              <small>{tr("Live · plans only")}</small>
            </div>
          </button>
        ))}
        <div className="sidebar-bottom">
          <div className="safety-note">
            <ShieldCheck size={20} />
            <strong>{tr("A safe place to experiment")}</strong>
            <p>
              {tr(
                "Every index is tested in a disposable database. Your production stays yours.",
              )}
            </p>
            <button onClick={() => setPage("Evaluation")}>
              {tr("Explore our methodology")}
            </button>
          </div>
          <button
            className="profile"
            disabled={portfolioOnly}
            onClick={() => setConnectionOpen(true)}
          >
            <span className="avatar">{authenticated ? "W" : tr("G")}</span>
            <div>
              {authenticated ? tr("Workspace owner") : tr("Demo explorer")}
              <small>
                {authenticated
                  ? tr("Authenticated session")
                  : tr("No sign-in needed")}
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
              ref={menuButton}
              className="mobile-menu"
              aria-expanded={mobile}
              aria-controls="q-experiment-navigation"
              aria-label={tr("Open navigation")}
              onClick={() => setMobile(!mobile)}
            >
              <Menu size={20} />
            </button>
            <span>{tr("Workspace")}</span>
            <ChevronRight size={14} />
            <strong>{tr(page)}</strong>
          </div>
          <div>
            <span className={"worker-status " + (online ? "" : "offline")}>
              <i />
              {online
                ? tr("Worker connected")
                : tr("Published reports available")}
            </span>
            <a
              href="https://github.com/wauul/queryotter"
              target="_blank"
              rel="noreferrer"
            >
              {tr("Source ")}
              <ExternalLink size={13} />
            </a>
          </div>
        </header>
        <main>
          {page === "Investigate" ? (
            <>
              <div className="page-heading">
                <div>
                  <h1>{tr("PostgreSQL experiments")}</h1>
                  <p>
                    {tr(
                      "Compare query plans, measured latency and result checks on disposable PostgreSQL data.",
                    )}
                  </p>
                </div>
                {!portfolioOnly && (
                  <button
                    className="outline"
                    onClick={() => setConnectionOpen(true)}
                  >
                    <Database size={16} />
                    {authenticated
                      ? tr("Connect database")
                      : tr("Connect your database")}
                    <ArrowUpRight size={15} />
                  </button>
                )}
              </div>
              <div className="demo-banner">
                <div className="demo-symbol">
                  <FlaskConical size={19} />
                </div>
                <div>
                  <strong>
                    {connectionId
                      ? tr("Live connection · estimates only")
                      : tr("You're in the OtterMart sandbox")}
                  </strong>
                  <span>
                    {connectionId
                      ? tr(
                          "Metadata and non-executing EXPLAIN. No measurements or indexes.",
                        )
                      : tr(
                          "370,000 synthetic records. Real PostgreSQL. Real measurements.",
                        )}
                  </span>
                </div>
                <Badge kind="teal">
                  {connectionId ? tr("Read-only") : tr("Safe to explore")}
                </Badge>
              </div>
              <div className="editor-grid">
                <section className="panel editor-panel">
                  <div className="panel-heading">
                    <div>
                      <Code2 size={18} />
                      <h2>{tr("Query workspace")}</h2>
                    </div>
                    <span className="tiny-label">{tr("PostgreSQL")}</span>
                  </div>
                  <div className="editor-toolbar">
                    <span>{tr("Try an example")}</span>
                    <select
                      aria-label={tr("Slow query example")}
                      disabled={!!active}
                      value={selected}
                      onChange={(e) => setSelected(e.target.value)}
                    >
                      {examples.map((e) => (
                        <option key={e.id} value={e.id}>
                          {tr(e.title)}
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
                      aria-label={tr("SQL editor")}
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
                        ? tr("Live · non-executing EXPLAIN")
                        : tr("SELECT only · disposable experiments")}
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
                          {tr("Cancel")}
                        </button>
                      ) : (
                        <button
                          className="primary"
                          onClick={investigate}
                          disabled={busy || !sql}
                        >
                          <Activity size={16} />
                          {busy ? tr("Starting…") : tr("Investigate query")}
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
                          : tr("OtterMart")}
                      </h2>
                    </div>
                    <span className="status-dot" />
                  </div>
                  <div className="db-meta">
                    <span>
                      {tr("PostgreSQL")}{" "}
                      {report?.schema.version ||
                        (connectionId ? tr("Not inspected") : "18")}
                    </span>
                    <Badge kind="neutral">
                      {connectionId ? tr("LIVE") : tr("SEEDED")}
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
                            ? tr("Size not measured")
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
                              {c[1]}{" "}
                              {c[1] === "id" && <small>{tr("PK")}</small>}
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
                      ? tr("No execution or schema changes")
                      : tr("Seed 17 · isolated per investigation")}
                  </div>
                </section>
              </div>
              {error && (
                <div className="error" role="alert">
                  <Unplug size={18} />
                  <span>{tr(error)}</span>
                  <button
                    aria-label={tr("Dismiss error")}
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
                    <h2>{tr("Running the experiment")}</h2>
                    <Badge kind="teal">{tr(job?.state || "")}</Badge>
                  </div>
                  <div className="stages">
                    {stages.map((s, i) => (
                      <span key={s} className={i <= stageIndex ? "done" : ""}>
                        {i < stageIndex ? (
                          <Check size={13} />
                        ) : (
                          <span className="stage-dot" />
                        )}
                        {tr(s)}
                      </span>
                    ))}
                  </div>
                  <p>
                    {tr(
                      job?.events.at(-1)?.message ||
                        "Queued for the single-concurrency investigation worker.",
                    )}
                  </p>
                </section>
              )}
              {report ? (
                <>
                  <div className="results-heading">
                    <div>
                      <h2>{tr("Investigation results")}</h2>
                      <Badge kind={best ? "green" : "amber"}>
                        {best ? (
                          <>
                            <CheckCircle2 size={12} />
                            {tr("Verified improvement")}
                          </>
                        ) : (
                          tr("No verified improvement")
                        )}
                      </Badge>
                    </div>
                    <div>
                      <span className="report-origin">
                        {job?.report === report
                          ? tr("Fresh investigation")
                          : tr("Published measured report")}
                      </span>
                      <button className="outline small" onClick={download}>
                        <Download size={14} />
                        {tr("Export report")}
                      </button>
                    </div>
                  </div>
                  <div className="metric-grid">
                    <div className="metric-card">
                      <span>
                        <Clock3 size={15} />
                        {tr("Original latency")}
                      </span>
                      <strong>{tr(ms(report.original?.median_ms))}</strong>
                      <small>{tr("Median PostgreSQL execution time")}</small>
                    </div>
                    <div className="metric-card optimized">
                      <span>
                        <Activity size={15} />
                        {tr("Optimized latency")}
                      </span>
                      <strong>{tr(ms(best?.optimized?.median_ms))}</strong>
                      <small>
                        {best
                          ? tr("Warm cache · 7 measured repetitions")
                          : tr("No candidate selected")}
                      </small>
                    </div>
                    <div className="metric-card">
                      <span>
                        <Gauge size={15} />
                        {tr("Measured speedup")}
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
                          ? tr("{value0} saved per execution", {
                              value0: ms(
                                report.original!.median_ms -
                                  best.optimized!.median_ms,
                              ),
                            })
                          : tr("No reliable gain established")}
                      </small>
                    </div>
                    <div className="metric-card">
                      <span>
                        <ShieldCheck size={15} />
                        {tr("Correctness checks")}
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
                          ? tr("Seeded & edge fixtures passed")
                          : tr("See candidate validation details")}
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
                          key={tr(t)}
                          onClick={() => setTab(t)}
                          className={tab === t ? "active" : ""}
                        >
                          {tr(t)}
                        </button>
                      ))}
                    </div>
                    <div className="tab-content">
                      {tab === "Overview" && (
                        <div className="overview-grid">
                          <div>
                            <div className="section-title">
                              <span className="icon-box">
                                <Activity size={18} />
                              </span>
                              <div>
                                <h3>
                                  {best
                                    ? tr("A better path through your data")
                                    : tr("What the investigation found")}
                                </h3>
                                <span>
                                  {tr("Model hypothesis, tested by PostgreSQL")}
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
                              <h4>{tr("Candidates tested")}</h4>
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
                                  {tr(
                                    "The agent proposed no justified improvement. Retain the original query.",
                                  )}
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="benchmark-box">
                            <h3>{tr("Latency, with the spread")}</h3>
                            <p>
                              {tr("Execution time · milliseconds · warm cache")}
                            </p>
                            {report.original && (
                              <Distribution
                                a={report.original}
                                b={best?.optimized}
                              />
                            )}
                            <div className="benchmark-facts">
                              <span>
                                {tr("Measured runs")}
                                <strong>
                                  {String(
                                    report.conditions.repetitions ||
                                      "Not measured",
                                  )}
                                </strong>
                              </span>
                              <span>
                                {tr("Original MAD")}
                                <strong>{ms(report.original?.mad_ms)}</strong>
                              </span>
                              <span>
                                {tr("Optimized MAD")}
                                <strong>{ms(best?.optimized?.mad_ms)}</strong>
                              </span>
                            </div>
                            <div className="quiet-note">
                              <Activity size={15} />
                              <span>
                                {tr("End-to-end investigation:")}{" "}
                                {report.usage.runtime_seconds}
                                {tr(
                                  "s. SQL latency excludes model and network time.",
                                )}
                              </span>
                            </div>
                          </div>
                        </div>
                      )}
                      {tab === "Query plans" && (
                        <div className="plans-grid">
                          <div>
                            <h3>
                              {tr("Before ")}
                              <Badge kind="neutral">{tr("Original")}</Badge>
                            </h3>
                            <Plan nodes={report.plan_before} />
                          </div>
                          <div>
                            <h3>
                              {tr("After")}{" "}
                              <Badge>
                                {best
                                  ? tr("Selected candidate")
                                  : tr("Not available")}
                              </Badge>
                            </h3>
                            {best?.plan ? (
                              <Plan nodes={best.plan} />
                            ) : (
                              <p>
                                {tr("No verified candidate plan to display.")}
                              </p>
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
                            {tr("Reviewable index migration")}
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
                                    {tr("MB")}
                                  </strong>
                                  {tr("Additional index storage")}
                                </span>
                                <span>
                                  <strong>{ms(best.index_build_ms)}</strong>
                                  {tr("Index construction time")}
                                </span>
                                <p>
                                  {best.tradeoff}
                                  {tr(
                                    " Review names and deployment locks. For production, schedule separately and consider CREATE INDEX CONCURRENTLY outside a transaction.",
                                  )}
                                </p>
                              </div>
                            </>
                          ) : (
                            <p>
                              {tr(
                                "No verified index migration. Unverified suggestions are available in the report export.",
                              )}
                            </p>
                          )}
                        </>
                      )}
                      {tab === "Correctness" && (
                        <>
                          <div className="section-title">
                            <ShieldCheck size={22} />
                            <div>
                              <h3>
                                {tr("Test the meaning, then test the speed")}
                              </h3>
                              <span>
                                {tr(
                                  "Types, values, NULLs, duplicates and ordered output",
                                )}
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
                                    ? tr("Passed")
                                    : tr("Not verified")}
                                </Badge>
                              </h4>
                              {c.correctness.datasets.map((d, i) => (
                                <div key={i}>
                                  <span>
                                    {d.size === 0
                                      ? tr("Empty tables")
                                      : d.edges
                                        ? tr(
                                            "NULLs, duplicates, skew & boundary values",
                                          )
                                        : tr("Benchmark dataset")}
                                  </span>
                                  <span>
                                    {tr("Seed ")}
                                    {d.seed} · {d.size.toLocaleString(locale)}{" "}
                                    {tr("orders")}
                                  </span>
                                  <Badge kind={d.passed ? "green" : "red"}>
                                    {d.passed ? tr("Passed") : tr("Failed")}
                                  </Badge>
                                </div>
                              ))}
                              {c.reason && <p>{c.reason}</p>}
                            </div>
                          ))}
                          <div className="empirical-note">
                            <ShieldCheck size={17} />
                            <p>
                              {String(report.conditions.equivalence)}
                              {tr(
                                " Equality on these fixtures is evidence, not a proof over all possible databases.",
                              )}
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
                                  <span>{tr(key.replaceAll("_", " "))}</span>
                                  <strong>
                                    {value === null
                                      ? tr("Unavailable")
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
                                  <span>{tr(e.stage)}</span>
                                  <p>{tr(e.message)}</p>
                                </div>
                              ),
                            )}
                          </div>
                          <h3>{tr("Experiment conditions")}</h3>
                          <div className="conditions">
                            {Object.entries(report.conditions).map(
                              ([key, value]) => (
                                <div key={key}>
                                  <strong>
                                    {tr(key.replaceAll("_", " "))}
                                  </strong>
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
                      {tr(
                        "Measured on synthetic data. Empirical checks are not a proof of SQL equivalence.",
                      )}
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
                    <h3>{tr("Choose a query to investigate")}</h3>
                    <p>
                      {tr(
                        "Choose a slow-query example and let QueryOtter investigate.",
                      )}
                      <br />
                      {tr("Findings appear here as measured evidence.")}
                    </p>
                  </div>
                )
              )}
            </>
          ) : page === "Run history" ? (
            <>
              <div className="page-heading">
                <div>
                  <h1>{tr("Experiment history")}</h1>
                  <p>
                    {tr(
                      "Reports and events persist in the worker's durable job store.",
                    )}
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
                          {tr(
                            examples.find((e) => e.id === j.case_id)?.title ||
                              "Custom investigation",
                          )}
                        </strong>
                        <small>
                          {new Date(j.created * 1000).toLocaleString(locale)} ·{" "}
                          {j.id.slice(0, 8)}
                        </small>
                      </div>
                      <Badge kind={j.state === "completed" ? "green" : "amber"}>
                        {tr(j.state)}
                      </Badge>
                      <ChevronRight size={18} />
                    </button>
                  ))
                ) : (
                  <div className="empty-state">
                    <History size={36} />
                    <h3>{tr("No experiments yet")}</h3>
                    <p>{tr("Run an example to create a persisted report.")}</p>
                    <button
                      className="primary"
                      onClick={() => setPage("Investigate")}
                    >
                      {tr("Investigate a query")}
                    </button>
                  </div>
                )}
              </section>
            </>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <h1>{tr("Evaluation methodology")}</h1>
                  <p>
                    {tr(
                      "All cases are published, including regressions, rejections and inconclusive runs.",
                    )}
                  </p>
                </div>
                <a className="outline" href="/evaluation.json" download>
                  <Download size={15} />
                  {tr("Evaluation data")}
                </a>
              </div>
              <div className="evaluation-intro">
                <div>
                  <ShieldCheck size={24} />
                  <h3>{tr("Independent semantic checks")}</h3>
                  <p>
                    {tr(
                      "Result types, multisets and ordered sequences are compared by deterministic code on four fixtures.",
                    )}
                  </p>
                </div>
                <div>
                  <Gauge size={24} />
                  <h3>{tr("Comparable measurements")}</h3>
                  <p>
                    {tr(
                      "Two warm-up rounds, seven measured repetitions, alternating execution order, medians and MAD.",
                    )}
                  </p>
                </div>
                <div>
                  <Code2 size={24} />
                  <h3>{tr("Two defined baselines")}</h3>
                  <p>
                    {tr(
                      "The original SELECT and a fixed, deterministic index recommendation defined in the case manifest.",
                    )}
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
                            ? v.toLocaleString(locale)
                            : String(v)}
                        </strong>
                        <span>{tr(k.replaceAll("_", " "))}</span>
                      </div>
                    ))}
                  </div>
                  <section className="panel evaluation-table">
                    <table>
                      <thead>
                        <tr>
                          <th>{tr("Benchmark case")}</th>
                          <th>{tr("Outcome")}</th>
                          <th>{tr("Original")}</th>
                          <th>{tr("Selected")}</th>
                          <th>{tr("Baseline")}</th>
                          <th>{tr("Correctness")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {evaluation.cases.map((c: any) => (
                          <tr key={c.id}>
                            <td>
                              <strong>{tr(c.title)}</strong>
                              <small>{tr(c.category)}</small>
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
                                {tr(c.outcome)}
                              </Badge>
                            </td>
                            <td>{ms(c.original_ms)}</td>
                            <td>{ms(c.best_ms)}</td>
                            <td>{ms(c.baseline_ms)}</td>
                            <td>
                              {c.correctness === null
                                ? tr("Not executed")
                                : c.correctness
                                  ? tr("Passed")
                                  : tr("Failed")}
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
                  <p>{tr("Evaluation data has not been published yet.")}</p>
                </div>
              )}
            </>
          )}
          <footer className="app-footer">
            <span>
              QueryOtter <span>·</span>
              {tr(" Reviewed queries, measured changes")}
            </span>
            <span>
              {tr("Built for PostgreSQL ")}
              <span>·</span>
              {tr(" Never changes production")}
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
            aria-label={tr("Database connection setup")}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label={tr("Close setup")}
              onClick={() => setConnectionOpen(false)}
            >
              <X size={20} />
            </button>
            <span className="icon-box">
              <Database size={25} />
            </span>
            <h2>
              {authenticated
                ? tr("Connect a read-only database")
                : tr("Owner sign-in")}
            </h2>
            <p>
              {authenticated
                ? tr(
                    "Live connections inspect metadata and non-executing plans. For measured experiments, use sanitized data in the disposable worker.",
                  )
                : tr(
                    "The public sandbox needs no account. Owner sign-in unlocks private queries and encrypted connections.",
                  )}
            </p>
            {!authenticated ? (
              <>
                <label>
                  {tr("Owner password")}
                  <input
                    aria-label={tr("Owner password")}
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && login()}
                  />
                </label>
                <button className="primary full" onClick={login}>
                  {tr("Sign in")}
                </button>
                <small className="modal-help">
                  {tr(
                    "Self-hosted owner password is configured in the worker's private environment. Public registration is not enabled.",
                  )}
                </small>
              </>
            ) : (
              <>
                <label>
                  {tr("Connection name")}
                  <input
                    value={connLabel}
                    onChange={(e) => setConnLabel(e.target.value)}
                    placeholder={tr("Analytics replica")}
                  />
                </label>
                <label>
                  {tr("PostgreSQL connection URL")}
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
                    {tr(
                      "Encrypted at rest. Read-only role required. Remote connections must verify TLS certificates.",
                    )}
                  </span>
                </div>
                <button
                  className="primary full"
                  onClick={addConnection}
                  disabled={busy || !connUrl || !connLabel}
                >
                  {busy
                    ? tr("Checking connection…")
                    : tr("Validate & save connection")}
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
                  {tr("Sign out")}
                </button>
              </>
            )}
            {error && (
              <p className="modal-error" role="alert">
                {tr(error)}
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
