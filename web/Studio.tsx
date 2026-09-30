import React, { useState, useEffect, useRef } from "react";
import {
  ArrowUpRight,
  Database,
  MessageSquare,
  Play,
  Square,
  Plus,
  ChevronRight,
  ChevronLeft,
  Check,
  CheckCircle2,
  ShieldCheck,
  LockKeyhole,
  BookOpen,
  History,
  Settings2,
  LogOut,
  Save,
  Download,
  RefreshCw,
  Search,
  Code2,
  FlaskConical,
  Activity,
  GitBranch,
  Menu,
  X,
  ExternalLink,
  Trash2,
  AlertCircle,
  LoaderCircle,
  FolderOpen,
} from "lucide-react";
import { Otter } from "./Otter";
import Landing from "./Landing";
import { ThemeControl } from "./Theme";
import {
  api,
  queryText,
  when,
  type Catalog,
  type Session,
  type Connection,
  type Metadata,
  type Job,
  type AssistantReport,
  type Result,
  type HistoryEntry,
  type Saved,
  type Candidate,
} from "./studio-api";
import StudioConnection from "./StudioConnection";
import StudioDocs from "./StudioDocs";
import { useModal } from "./useModal";
import Legacy from "./LegacyOptimizer";
const SAMPLE =
  "Show the five customers with the highest total paid orders last month. Paid means status = 'paid'. Use UTC calendar months and break ties by customer id.";
const links = [
  { id: "workspace", name: "Query workspace", icon: MessageSquare },
  { id: "connections", name: "Connections", icon: Database },
  { id: "optimization", name: "Optimization", icon: FlaskConical },
  { id: "saved", name: "Saved queries", icon: FolderOpen },
  { id: "history", name: "History", icon: History },
];
const documentPages = ["docs", "support", "privacy", "terms", "matrix"];
function Brand() {
  return (
    <a className="q-brand" href="#home">
      <Otter small />
      <span>QueryOtter</span>
    </a>
  );
}
function Empty({
  title,
  children,
  icon: Icon = Database,
}: {
  title: string;
  children: React.ReactNode;
  icon?: typeof Database;
}) {
  return (
    <div className="q-empty">
      <div>
        <Icon size={25} />
      </div>
      <h3>{title}</h3>
      {children}
    </div>
  );
}
function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
}) {
  return (
    <div className="q-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export default function Studio() {
  const [page, setPage] = useState(location.hash.slice(1) || "home");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connections, setConnections] = useState<Connection[]>([]);
  const [selected, setSelected] = useState("");
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [schemaSearch, setSchemaSearch] = useState("");
  const [auth, setAuth] = useState(false);
  const [ownerPass, setOwnerPass] = useState("");
  const [connectionDialog, setConnectionDialog] = useState(false);
  const [rotation, setRotation] = useState<Connection | undefined>();
  const [mobileMenu, setMobileMenu] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [prompt, setPrompt] = useState(SAMPLE);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<AssistantReport | null>(null);
  const [previous, setPrevious] = useState<string | null>(null);
  const [conversation, setConversation] = useState<
    { question: string; response: string }[]
  >([]);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [resultId, setResultId] = useState("");
  const [optimization, setOptimization] = useState<AssistantReport | null>(
    null,
  );
  const [benchmark, setBenchmark] = useState<AssistantReport | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveDialog, setSaveDialog] = useState(false);
  const [savingQuery, setSavingQuery] = useState(false);
  const [confirm, setConfirm] = useState<{
    title: string;
    body: string;
    action: () => Promise<void>;
  } | null>(null);
  const [deleteText, setDeleteText] = useState("");
  const [workspaceName, setWorkspaceName] = useState("My workspace");
  const [timezone, setTimezone] = useState("UTC");
  const [retention, setRetention] = useState(30);
  const [connectorLabel, setConnectorLabel] = useState("My local connector");
  const [connectors, setConnectors] = useState<
    { id: string; label: string; last_seen?: number }[]
  >([]);
  const [enrollment, setEnrollment] = useState<{
    id: string;
    token: string;
  } | null>(null);
  const [prisma, setPrisma] = useState("");
  const [manualCandidate, setManualCandidate] = useState("");
  const [manualIndexes, setManualIndexes] = useState("");
  useModal(auth || saveDialog || !!confirm, () => {
    setAuth(false);
    setSaveDialog(false);
    setConfirm(null);
  });
  const mounted = useRef(true);
  const sessionRevision = useRef(0);
  const connection = connections.find((c) => c.id === selected);
  const engine = catalog?.engines.find((e) => e.id === connection?.engine);
  useEffect(() => {
    if (!mobileMenu) return;
    const navigation = document.getElementById("q-workspace-navigation");
    navigation?.querySelector<HTMLAnchorElement>("nav a")?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileMenu(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [mobileMenu]);
  useEffect(() => {
    mounted.current = true;
    const change = () => {
      setPage(location.hash.slice(1) || "home");
      setMobileMenu(false);
      setAuth(false);
      window.scrollTo(0, 0);
    };
    addEventListener("hashchange", change);
    void refresh();
    return () => {
      mounted.current = false;
      removeEventListener("hashchange", change);
    };
  }, []);
  async function refresh() {
    setLoading(true);
    try {
      const [c, s] = await Promise.all([
        api<Catalog>("/catalog"),
        api<Session>("/session"),
      ]);
      setCatalog(c);
      setSession(s);
      if (s.workspace) {
        setWorkspaceName(s.workspace.name);
        setTimezone(s.workspace.timezone);
        setRetention(s.workspace.retention_days);
      }
      if (s.user) {
        const cs = await api<Connection[]>("/connections");
        setConnections(cs);
        setSelected((old) =>
          old && cs.some((c) => c.id === old) ? old : cs[0]?.id || "",
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  async function refreshData() {
    if (!session?.user) return;
    const [cs, s] = await Promise.all([
      api<Connection[]>("/connections"),
      api<Session>("/session"),
    ]);
    setConnections(cs);
    setSession(s);
  }
  useEffect(() => {
    let active = true;
    setMetadata(null);
    if (selected && session?.user)
      api<{ metadata: Metadata | null }>(`/connections/${selected}/schema`)
        .then((r) => {
          if (active) setMetadata(r.metadata);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [selected, connection?.configuration_revision, session?.user?.id]);
  useEffect(() => {
    if (!session?.user) return;
    let active = true;
    async function load() {
      setListLoading(true);
      try {
        if (page === "history") {
          const entries = await api<HistoryEntry[]>("/history");
          if (active) setHistory(entries);
        } else if (page === "saved") {
          const entries = await api<Saved[]>("/saved");
          if (active) setSaved(entries);
        } else if (page === "settings") {
          const entries = await api<typeof connectors>("/connectors");
          if (active) setConnectors(entries);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        if (active) setListLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [page, session?.user?.id]);
  function choose(cid: string) {
    setSelected(cid);
    setDraft(null);
    setQuery("");
    setResult(null);
    setResultId("");
    setPrevious(null);
    setConversation([]);
    setOptimization(null);
    setBenchmark(null);
    setManualCandidate("");
    setManualIndexes("");
    setError("");
  }
  function clearWorkspace() {
    sessionRevision.current += 1;
    choose("");
    setSession(null);
    setConnections([]);
    setMetadata(null);
    setSaved([]);
    setHistory([]);
    setConnectors([]);
    setEnrollment(null);
    setJob(null);
    setPrompt(SAMPLE);
    setBusy(false);
    setDeleteText("");
  }
  async function safely(fn: () => Promise<void>) {
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function signIn(provider: string) {
    await safely(async () => {
      const r = await api<{ url: string }>(`/auth/${provider}/start`, {});
      location.assign(r.url);
    });
  }
  async function startDemo(example = SAMPLE) {
    setBusy(true);
    await safely(async () => {
      await api("/demo/start", {});
      const s = await api<Session>("/session");
      setSession(s);
      if (s.workspace) {
        setWorkspaceName(s.workspace.name);
        setTimezone(s.workspace.timezone);
        setRetention(s.workspace.retention_days);
      }
      const cs = await api<Connection[]>("/connections");
      const c = cs[0] || (await api<Connection>("/connections/demo", {}));
      setConnections(cs.length ? cs : [c]);
      choose(c.id);
      setPrompt(example);
      setAuth(false);
      location.hash = "workspace";
      setNotice(
        "Synthetic demo ready. Generate prepares a draft; Run executes it.",
      );
    });
    setBusy(false);
  }
  async function run(action: string, extra: Record<string, unknown> = {}) {
    if (!selected) {
      setError("Choose a connection first.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    setJob(null);
    const revision = sessionRevision.current;
    const current = () =>
      mounted.current && revision === sessionRevision.current;
    try {
      let j = await api<Job>("/jobs", {
        connection_id: selected,
        action,
        request_key: crypto.randomUUID(),
        ...(action === "generate"
          ? { prompt, previous_run: previous }
          : { query }),
        ...extra,
      });
      if (!current()) return;
      setJob(j);
      while (["queued", "running"].includes(j.state)) {
        await new Promise((resolve) => setTimeout(resolve, 700));
        if (!current()) return;
        j = await api<Job>("/jobs/" + j.id);
        if (!current()) return;
        setJob(j);
      }
      if (j.state === "cancelled") {
        setNotice("Operation cancelled. No production indexes were changed.");
        return;
      }
      if (j.state !== "completed" || !j.report)
        throw new Error(j.error || "The operation could not be completed.");
      const r = j.report;
      if (action === "test" || action === "discover") {
        setMetadata(r.metadata || null);
        setNotice(
          "Connection and discovery verified. Generation and execution are separate checks.",
        );
      }
      if (action === "generate") {
        setDraft(r);
        if (r.query) {
          setQuery(queryText(r.query));
          setPrevious(r.run_id);
        }
        setConversation((old) =>
          [
            ...old,
            {
              question: prompt,
              response:
                r.clarification ||
                r.explanation ||
                r.validation_error ||
                "Draft ready",
            },
          ].slice(-8),
        );
        setResult(null);
        setResultId("");
      }
      if (action === "validate") {
        setDraft(r);
        setNotice(
          "Syntax and metadata validation passed. The query has not been executed.",
        );
      }
      if (action === "run") {
        const rows = await api<Result>(`/results/${r.run_id}`);
        if (!current()) return;
        setResultId(r.run_id);
        setResult(rows);
        setDraft((old) =>
          old
            ? {
                ...old,
                validation: {
                  syntactically_valid: true,
                  executable: true,
                  business_meaning_verified: false,
                },
              }
            : r,
        );
      }
      if (action === "optimize") setOptimization(r);
      if (action === "benchmark") setBenchmark(r);
      const [cs, s, cache] = await Promise.all([
        api<Connection[]>("/connections"),
        api<Session>("/session"),
        api<{ metadata: Metadata | null }>(`/connections/${selected}/schema`),
      ]);
      if (!current()) return;
      setConnections(cs);
      setSession(s);
      setMetadata(cache.metadata);
    } catch (e) {
      if (current()) setError((e as Error).message);
    } finally {
      if (current()) setBusy(false);
    }
  }
  async function cancel() {
    if (job)
      await safely(async () => {
        setJob(await api<Job>(`/jobs/${job.id}/cancel`, {}));
      });
  }
  async function resultPage(next: number) {
    await safely(async () =>
      setResult(
        await api<Result>(`/results/${resultId}?page=${next}&page_size=50`),
      ),
    );
  }
  async function addSeed() {
    await safely(async () => {
      const c = await api<Connection>("/connections/demo", {});
      setConnections((old) => [c, ...old]);
      choose(c.id);
      location.hash = "workspace";
      setNotice("A fresh synthetic SQLite copy is ready.");
    });
  }
  function load(
    item: {
      connection_id: string;
      query: string | null;
      prompt: string | null;
      id?: string;
    },
    fromHistory = false,
  ) {
    setSelected(item.connection_id);
    setQuery(item.query || "");
    setPrompt(item.prompt || "");
    setPrevious(fromHistory ? item.id || null : null);
    setResult(null);
    setResultId("");
    setDraft(null);
    setConversation([]);
    location.hash = "workspace";
  }
  function askRemove(c: Connection) {
    setConfirm({
      title: "Remove this connection?",
      body: "Its encrypted secrets, schema cache, saved queries, history, results and associated jobs will be removed.",
      action: async () => {
        await api(`/connections/${c.id}/remove`, {});
        const cs = await api<Connection[]>("/connections");
        setConnections(cs);
        if (selected === c.id) choose(cs[0]?.id || "");
        setNotice("Connection and associated data removed.");
      },
    });
  }
  const header = (
    <header className="q-public-header">
      <Brand />
      <nav>
        <a href="#docs">Field guide</a>
        <a href="#matrix">Support matrix</a>
        <a
          href="https://github.com/wauul/queryotter"
          target="_blank"
          rel="noreferrer"
        >
          GitHub <ArrowUpRight size={13} />
        </a>
      </nav>
      <ThemeControl />
      <button
        className="q-button"
        onClick={() =>
          session?.user ? (location.hash = "workspace") : setAuth(true)
        }
      >
        {session?.user ? "Workspace" : "Sign in"}
      </button>
    </header>
  );
  const feedback = (
    <>
      {error && (
        <div className="q-feedback error" role="alert">
          <AlertCircle size={17} />
          <span>{error}</span>
          <button aria-label="Dismiss error" onClick={() => setError("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {notice && (
        <div className="q-feedback success" role="status">
          <CheckCircle2 size={17} />
          <span>{notice}</span>
          <button aria-label="Dismiss notice" onClick={() => setNotice("")}>
            <X size={16} />
          </button>
        </div>
      )}
    </>
  );
  if (page === "experiments")
    return (
      <>
        <div className="q-legacy-return">
          <a href="#workspace">← Back to workspace</a>
          <span>Controlled synthetic PostgreSQL experiments</span>
          <ThemeControl />
        </div>
        <Legacy portfolioOnly />
      </>
    );
  return (
    <div className="q-studio">
      <a
        className="q-skip"
        href="#q-main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("q-main")?.focus();
        }}
      >
        Skip to content
      </a>
      {page === "home" ||
      documentPages.includes(page) ||
      ![
        "workspace",
        "connections",
        "optimization",
        "saved",
        "history",
        "settings",
      ].includes(page) ||
      !session?.user ? (
        <>
          {header}
          {feedback}
          {page === "home" ? (
            <Landing
              catalog={catalog}
              busy={busy}
              loading={loading}
              onDemo={(example) => void startDemo(example)}
              onConnect={() =>
                session?.user ? (location.hash = "connections") : setAuth(true)
              }
            />
          ) : page === "matrix" ? (
            <main className="q-prose q-matrix" id="q-main" tabIndex={-1}>
              <h1>Support matrix</h1>
              <p>
                Each adapter exposes different controls. Local verification does
                not imply hosted access. Your own configuration still needs
                discovery, generation, validation and execution checks.
              </p>
              {catalog?.engines.map((e) => (
                <section className="q-matrix-engine" key={e.id}>
                  <div>
                    <h2>{e.name}</h2>
                    <span className="q-tag">{e.verification.status}</span>
                  </div>
                  <p>
                    <strong>Version:</strong>{" "}
                    {e.verification.version || "Not verified"}
                    <br />
                    <strong>Hosted:</strong> {e.verification.hosted_provider}
                    <br />
                    <strong>Generation:</strong>{" "}
                    {e.verification.generation || "Verification pending"}
                  </p>
                  <div className="q-capabilities">
                    {Object.entries(e.capabilities).map(([k, v]) => (
                      <span className={v ? "available" : "unavailable"} key={k}>
                        <span className="q-sr-only">
                          {v ? "Supported: " : "Unsupported: "}
                        </span>
                        {v ? (
                          <Check size={13} aria-hidden="true" />
                        ) : (
                          <X size={13} aria-hidden="true" />
                        )}{" "}
                        {k.replaceAll("_", " ")}
                      </span>
                    ))}
                  </div>
                  {e.limitations.map((l) => (
                    <p className="q-note" key={l}>
                      {l}
                    </p>
                  ))}
                  <details>
                    <summary>Verified test scope</summary>
                    {e.verification.tests?.map((t) => (
                      <p key={t}>✓ {t}</p>
                    ))}
                    <a
                      href="/adapter-verification.json"
                      target="_blank"
                      rel="noreferrer"
                    >
                      Machine-readable evidence
                    </a>
                  </details>
                </section>
              ))}
            </main>
          ) : documentPages.includes(page) ? (
            <StudioDocs page={page} catalog={catalog} />
          ) : ![
              "workspace",
              "connections",
              "optimization",
              "saved",
              "history",
              "settings",
            ].includes(page) ? (
            <main className="q-prose" id="q-main" tabIndex={-1}>
              <h1>Page not found</h1>
              <p>This address does not match a QueryOtter page.</p>
              <a className="q-button" href="#home">
                Go to the home page
              </a>
            </main>
          ) : loading ? (
            <main
              className="q-prose"
              id="q-main"
              tabIndex={-1}
              role="status"
              aria-live="polite"
            >
              <h1>Restoring your workspace…</h1>
              <p>Checking your session and loading your connections.</p>
            </main>
          ) : (
            <main className="q-prose" id="q-main" tabIndex={-1}>
              <h1>Your query workspace</h1>
              <p>
                Sign in to save connections, queries and history. A synthetic
                public demo is available without database credentials.
              </p>
              <button className="q-button" onClick={() => setAuth(true)}>
                Choose a sign-in provider
              </button>
              <button
                className="q-button secondary"
                onClick={() => void startDemo()}
              >
                Try the safe demo
              </button>
            </main>
          )}
          <footer className="q-public-footer">
            <Brand />
            <span>Queries grounded in schema and evidence</span>
            <nav>
              <a href="#docs">Docs & FAQ</a>
              <a href="#support">Support</a>
              <a href="#privacy">Privacy</a>
              <a href="#terms">Terms</a>
            </nav>
          </footer>
        </>
      ) : (
        <div className="q-workspace-shell">
          <aside
            id="q-workspace-navigation"
            aria-label="Workspace navigation"
            className={"q-sidebar " + (mobileMenu ? "open" : "")}
          >
            <Brand />
            <div className="q-workspace-label">
              <span className="q-workspace-avatar">
                {session.demo ? "D" : session.user.name.charAt(0).toUpperCase()}
              </span>
              <div>
                <strong>{session.workspace?.name}</strong>
                <small>
                  {session.demo ? "Synthetic demo" : "Personal workspace"}
                </small>
              </div>
            </div>
            <nav>
              {links.map((l) => (
                <a
                  className={page === l.id ? "active" : ""}
                  aria-current={page === l.id ? "page" : undefined}
                  href={"#" + l.id}
                  key={l.id}
                >
                  <l.icon size={18} />
                  {l.name}
                  {l.id === "connections" && <span>{connections.length}</span>}
                </a>
              ))}
            </nav>
            <div className="q-sidebar-tip">
              <Otter small />
              <strong>Review the business meaning</strong>
              <p>
                A valid query can still answer the wrong question. Review its
                meaning.
              </p>
              <a href="#docs">Read the field guide</a>
            </div>
            <nav className="q-sidebar-bottom">
              <a href="#experiments">
                <FlaskConical size={18} />
                PostgreSQL experiments
              </a>
              <a
                href="#settings"
                className={page === "settings" ? "active" : ""}
              >
                <Settings2 size={18} />
                Settings & usage
              </a>
              <a href="#docs">
                <BookOpen size={18} />
                Docs & support
              </a>
              <button
                onClick={() =>
                  void safely(async () => {
                    await api("/logout", {});
                    clearWorkspace();
                    location.hash = "home";
                    setNotice("Signed out. This session was revoked.");
                  })
                }
              >
                <LogOut size={17} />
                Log out
              </button>
            </nav>
            <div className="q-user-label">
              <span>{session.user.name.charAt(0)}</span>
              <div>
                <strong>{session.user.name}</strong>
                <small>
                  {session.demo ? "Demo session · 24 hours" : "Session secured"}
                </small>
              </div>
            </div>
          </aside>
          <div className="q-workspace-main">
            <header className="q-topbar">
              <button
                ref={menuButton}
                className="q-mobile-menu"
                aria-label="Toggle workspace menu"
                aria-expanded={mobileMenu}
                aria-controls="q-workspace-navigation"
                onClick={() => setMobileMenu(!mobileMenu)}
              >
                <Menu size={21} />
              </button>
              <div>
                <span>Workspace</span>
                <ChevronRight size={13} />
                <strong>
                  {links.find((l) => l.id === page)?.name || "Settings & usage"}
                </strong>
              </div>
              <a href="#matrix">
                <ShieldCheck size={14} />
                Support evidence
              </a>
              <ThemeControl />
              <span className="q-tag">
                {session.demo ? "Synthetic data" : "Read-only by default"}
              </span>
            </header>
            <main className="q-workspace-content" id="q-main" tabIndex={-1}>
              {feedback}
              {!session.workspace?.onboarded && (
                <section className="q-onboarding">
                  <Otter small />
                  <div>
                    <strong>Set up your workspace</strong>
                    <p>
                      Choose a time zone, then explore a safe demo or connect
                      your read-only database.
                    </p>
                  </div>
                  <select
                    aria-label="Onboarding time zone"
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                  >
                    {[
                      "UTC",
                      "Europe/Paris",
                      "Europe/London",
                      "America/New_York",
                      "America/Los_Angeles",
                      "Asia/Tokyo",
                    ].map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                  <button
                    className="q-button"
                    disabled={busy}
                    onClick={() => {
                      setBusy(true);
                      void safely(async () => {
                        await api("/settings", {
                          name: workspaceName,
                          timezone,
                          retention_days: retention,
                        });
                        await refreshData();
                        setNotice("Workspace preferences saved.");
                      }).finally(() => setBusy(false));
                    }}
                  >
                    Get started
                  </button>
                </section>
              )}
              <div className="q-page-head">
                <div>
                  <h1>
                    {page === "workspace"
                      ? "Query workspace"
                      : page === "connections"
                        ? "Your connections"
                        : page === "optimization"
                          ? "Optimization"
                          : page === "history"
                            ? "Query history"
                            : page === "saved"
                              ? "Saved queries"
                              : "Settings & usage"}
                  </h1>
                  <p>
                    {page === "workspace"
                      ? "Ask in plain language. Review the native query. Run when you’re ready."
                      : page === "connections"
                        ? "Test, explore, rotate and remove your database connections."
                        : page === "optimization"
                          ? "Plan evidence and measured results have different meanings."
                          : page === "history"
                            ? "Private history, retained on your schedule."
                            : page === "saved"
                              ? "Load a query to review and run it against its original connection."
                              : "Manage retention, local access, exports and your account."}
                  </p>
                </div>
                {page === "connections" && (
                  <button
                    className="q-button"
                    onClick={() => {
                      setRotation(undefined);
                      setConnectionDialog(true);
                    }}
                    disabled={session.demo}
                  >
                    <Plus size={16} />
                    Add connection
                  </button>
                )}
              </div>
              {["workspace", "optimization"].includes(page) && (
                <div className="q-connection-bar">
                  <Database size={17} />
                  <label>
                    Selected connection
                    <select
                      aria-label="Selected connection"
                      value={selected}
                      onChange={(e) => choose(e.target.value)}
                      disabled={busy}
                    >
                      <option value="">Choose a database</option>
                      {connections.map((c) => (
                        <option value={c.id} key={c.id}>
                          {c.label} ·{" "}
                          {
                            catalog?.engines.find((e) => e.id === c.engine)
                              ?.name
                          }
                        </option>
                      ))}
                    </select>
                  </label>
                  {connection && (
                    <div className="q-connection-meta">
                      <span className="q-tag">{engine?.name}</span>
                      <span className="q-muted">
                        {metadata?.version?.split(" ").slice(0, 3).join(" ") ||
                          "Version after discovery"}
                      </span>
                      <button
                        className="q-icon-button"
                        aria-label="Refresh selected schema"
                        onClick={() => void run("discover")}
                        disabled={busy}
                      >
                        <RefreshCw size={16} />
                      </button>
                    </div>
                  )}
                </div>
              )}
              {busy && (
                <section
                  className="q-operation"
                  role="status"
                  aria-live="polite"
                >
                  <LoaderCircle className="q-spin" size={19} />
                  <div>
                    <strong>
                      {job?.state === "queued"
                        ? "Waiting for the worker…"
                        : "Working with your selected database…"}
                    </strong>
                    <p>
                      {job?.events.at(-1)?.message ||
                        "Preparing a durable operation."}
                    </p>
                  </div>
                  <button
                    className="q-button secondary"
                    disabled={!job}
                    onClick={() => void cancel()}
                  >
                    <Square size={13} />
                    Cancel
                  </button>
                </section>
              )}
              {page === "workspace" &&
                (!connection ? (
                  <Empty title="Choose a database to begin">
                    <p>
                      Use a safe synthetic copy or add a read-only database.
                    </p>
                    <button className="q-button" onClick={() => void addSeed()}>
                      Open a demo copy
                    </button>
                    <a href="#connections">Manage connections</a>
                  </Empty>
                ) : (
                  <div className="q-query-layout">
                    <section className="q-query-main">
                      <div className="q-card q-question-card">
                        <div className="q-card-heading">
                          <MessageSquare size={18} />
                          <h2>Ask your database</h2>
                          <span className="q-tag">Groq · metadata only</span>
                        </div>
                        {conversation.length > 0 && (
                          <details className="q-conversation">
                            <summary>
                              Conversation · {conversation.length}{" "}
                              {conversation.length === 1 ? "turn" : "turns"}
                            </summary>
                            {conversation.map((c, i) => (
                              <div key={i}>
                                <strong>{c.question}</strong>
                                <p>{c.response}</p>
                              </div>
                            ))}
                          </details>
                        )}
                        <label className="q-sr-only" htmlFor="q-prompt">
                          Natural-language request
                        </label>
                        <textarea
                          id="q-prompt"
                          value={prompt}
                          onChange={(e) => setPrompt(e.target.value)}
                          rows={3}
                          maxLength={3000}
                          placeholder="Show the five customers with the highest total paid orders last month…"
                        />
                        <div className="q-question-footer">
                          <span>
                            <LockKeyhole size={12} />
                            No records or credentials sent
                          </span>
                          <button
                            className="q-button"
                            onClick={() => void run("generate")}
                            disabled={busy || !prompt.trim()}
                          >
                            <MessageSquare size={15} />
                            {previous ? "Refine query" : "Generate query"}
                          </button>
                        </div>
                        {draft?.clarification && (
                          <div className="q-clarification">
                            <strong>Clarify your request</strong>
                            <p>{draft.clarification}</p>
                            <small>
                              Edit your request above to answer, then refine.
                            </small>
                          </div>
                        )}
                        {draft?.validation_error && (
                          <p role="alert" className="q-error">
                            {draft.validation_error}
                          </p>
                        )}
                      </div>
                      <div className="q-card q-editor-card">
                        <div className="q-card-heading">
                          <Code2 size={18} />
                          <h2>Native query</h2>
                          <span className="q-tag">{engine?.name}</span>
                          <button
                            className="q-text-button"
                            disabled={!query || busy}
                            onClick={() => {
                              setSaveName("");
                              setSaveDialog(true);
                            }}
                          >
                            <Save size={14} />
                            Save
                          </button>
                        </div>
                        <label className="q-sr-only" htmlFor="q-native">
                          Native query editor
                        </label>
                        <div className="q-code-editor">
                          <div aria-hidden="true">
                            {Array.from(
                              { length: Math.max(8, query.split("\n").length) },
                              (_, i) => (
                                <span key={i}>{i + 1}</span>
                              ),
                            )}
                          </div>
                          <textarea
                            id="q-native"
                            spellCheck={false}
                            value={query}
                            onChange={(e) => {
                              setQuery(e.target.value);
                              setDraft(null);
                            }}
                            rows={Math.max(
                              8,
                              Math.min(22, query.split("\n").length),
                            )}
                            maxLength={12000}
                            placeholder={
                              connection &&
                              [
                                "postgresql",
                                "mysql",
                                "mariadb",
                                "sqlserver",
                                "cockroachdb",
                                "sqlite",
                              ].includes(connection.engine)
                                ? "SELECT …"
                                : "Enter a supported native JSON query…"
                            }
                          />
                        </div>
                        <div className="q-editor-footer">
                          <span>
                            {draft?.validation?.syntactically_valid ? (
                              <>
                                <CheckCircle2 size={13} />
                                Syntax & metadata validated
                              </>
                            ) : (
                              <>
                                <ShieldCheck size={13} />
                                Review before Run
                              </>
                            )}
                          </span>
                          <button
                            className="q-button secondary"
                            disabled={!query || busy}
                            onClick={() => void run("validate")}
                          >
                            Validate
                          </button>
                          <button
                            className="q-button"
                            disabled={!query || busy}
                            onClick={() => void run("run")}
                          >
                            <Play size={14} />
                            Run query
                          </button>
                        </div>
                      </div>
                      {draft?.explanation && (
                        <div className="q-card q-explanation">
                          <div className="q-card-heading">
                            <GitBranch size={17} />
                            <h2>Query explanation</h2>
                          </div>
                          <p>{draft.explanation}</p>
                          {draft.assumptions?.length ? (
                            <ul>
                              {draft.assumptions.map((a) => (
                                <li key={a}>{a}</li>
                              ))}
                            </ul>
                          ) : null}
                          <p className="q-note">
                            Syntax:{" "}
                            {draft.validation?.syntactically_valid
                              ? "validated"
                              : "not validated"}{" "}
                            · Execution:{" "}
                            {draft.validation?.executable === true
                              ? "succeeded"
                              : "not run"}{" "}
                            · Business meaning: requires your review
                          </p>
                          <div className="q-usage-line">
                            <span>
                              Model calls {draft.usage.model_calls || 0}
                            </span>
                            <span>
                              Tokens{" "}
                              {Number(draft.usage.input_tokens || 0) +
                                Number(draft.usage.output_tokens || 0)}
                            </span>
                            <span>
                              {Number(draft.usage.seconds || 0).toFixed(2)} s
                            </span>
                            <span>
                              Estimated $
                              {Number(
                                draft.usage.estimated_cost_usd || 0,
                              ).toFixed(5)}
                            </span>
                          </div>
                        </div>
                      )}
                      <div className="q-card q-results">
                        <div className="q-card-heading">
                          <Activity size={18} />
                          <h2>Results</h2>
                          {result && (
                            <>
                              <span className="q-tag">
                                {result.row_count} rows ·{" "}
                                {result.elapsed_ms.toFixed(2)} ms
                              </span>
                              <a
                                href={`/api/assistant/results/${resultId}/export?format=json`}
                                className="q-text-button"
                              >
                                <Download size={14} />
                                JSON
                              </a>
                              <a
                                href={`/api/assistant/results/${resultId}/export?format=csv`}
                                className="q-text-button"
                              >
                                CSV
                              </a>
                            </>
                          )}
                        </div>
                        {!result ? (
                          <Empty title="Run a query to see results" icon={Play}>
                            <p>
                              Review or edit the query, then select Run.
                              Generating a draft never executes it.
                            </p>
                          </Empty>
                        ) : (
                          <>
                            <div className="q-table-scroll">
                              <table>
                                <thead>
                                  <tr>
                                    {result.columns.map((c, i) => (
                                      <th key={i}>{c}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {result.rows.map((row, i) => (
                                    <tr key={i}>
                                      {row.map((v, j) => (
                                        <td key={j}>
                                          {v === null ? (
                                            <span className="q-null">
                                              NULL / missing
                                            </span>
                                          ) : typeof v === "object" ? (
                                            JSON.stringify(v)
                                          ) : (
                                            String(v)
                                          )}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              {result.rows.length === 0 && (
                                <p className="q-table-empty">
                                  No rows matched this query. Review filters and
                                  date boundaries.
                                </p>
                              )}
                            </div>
                            <div className="q-results-footer">
                              <span>
                                {result.truncated
                                  ? "Clipped at 500 rows. "
                                  : ""}
                                Bounded snapshot · expires after 15 minutes
                              </span>
                              <div
                                className="q-pagination"
                                role="group"
                                aria-label="Results pagination"
                              >
                                <button
                                  aria-label="Previous results page"
                                  disabled={result.page <= 1}
                                  onClick={() =>
                                    void resultPage(result.page - 1)
                                  }
                                >
                                  <ChevronLeft size={17} />
                                </button>
                                <span>
                                  Page {result.page} of{" "}
                                  {Math.max(
                                    1,
                                    Math.ceil(result.row_count / 50),
                                  )}
                                </span>
                                <button
                                  aria-label="Next results page"
                                  disabled={
                                    result.page * 50 >= result.row_count
                                  }
                                  onClick={() =>
                                    void resultPage(result.page + 1)
                                  }
                                >
                                  <ChevronRight size={17} />
                                </button>
                              </div>
                            </div>
                            <p className="q-note">
                              Execution succeeded. Business meaning remains
                              unverified. Document JSON export preserves missing
                              fields.
                            </p>
                          </>
                        )}
                      </div>
                    </section>
                    <aside
                      className={
                        "q-schema-panel " + (schemaOpen ? "expanded" : "")
                      }
                    >
                      <div className="q-card-heading">
                        <Database size={17} />
                        <h2>Schema explorer</h2>
                        <button
                          className="q-schema-toggle"
                          aria-expanded={schemaOpen}
                          aria-controls="q-schema-content"
                          onClick={() => setSchemaOpen(!schemaOpen)}
                        >
                          {schemaOpen ? "Hide fields" : "Show fields"}
                        </button>
                        <button
                          aria-label="Refresh schema"
                          className="q-icon-button"
                          onClick={() => void run("discover")}
                          disabled={busy}
                        >
                          <RefreshCw size={14} />
                        </button>
                      </div>
                      <div id="q-schema-content" className="q-schema-content">
                        <div className="q-schema-search">
                          <Search size={14} />
                          <input
                            aria-label="Search schema"
                            value={schemaSearch}
                            onChange={(e) => setSchemaSearch(e.target.value)}
                            placeholder="Find a table or field…"
                          />
                        </div>
                        {!metadata ? (
                          <Empty title="Discover your schema">
                            <p>
                              Test or refresh the selected connection to
                              discover actual tables and fields.
                            </p>
                            <button
                              className="q-button secondary"
                              onClick={() => void run("test")}
                              disabled={busy}
                            >
                              Test & discover
                            </button>
                          </Empty>
                        ) : (
                          <>
                            <p className="q-schema-note">
                              {metadata.tables.length} tables / collections ·{" "}
                              {metadata.complete
                                ? "Discovered metadata"
                                : "Sampled, incomplete schema"}
                            </p>
                            {metadata.tables
                              .filter((t) =>
                                [t.name, ...t.columns.map((c) => c.name)].some(
                                  (n) =>
                                    n
                                      .toLowerCase()
                                      .includes(schemaSearch.toLowerCase()),
                                ),
                              )
                              .map((t) => (
                                <details
                                  className="q-schema-table"
                                  key={t.name}
                                  open={
                                    !!schemaSearch ||
                                    metadata.tables.length <= 3
                                  }
                                >
                                  <summary>
                                    <Database size={13} />
                                    <strong>{t.name}</strong>
                                    <span>{t.columns.length}</span>
                                  </summary>
                                  {t.inferred && (
                                    <p className="q-note">
                                      Inferred from {t.sampled_documents || 0}{" "}
                                      documents; sparse fields may be missing.
                                    </p>
                                  )}
                                  {t.columns.map((c) => (
                                    <div
                                      className="q-schema-column"
                                      key={c.name}
                                    >
                                      <span>
                                        {c.name}
                                        {c.nullable && <small> ?</small>}
                                      </span>
                                      <code>{c.type}</code>
                                    </div>
                                  ))}
                                </details>
                              ))}
                            <details>
                              <summary>Relationships & indexes</summary>
                              <pre>
                                {JSON.stringify(
                                  {
                                    relationships: metadata.relationships,
                                    indexes: metadata.indexes,
                                  },
                                  null,
                                  2,
                                )}
                              </pre>
                            </details>
                            <p className="q-note">
                              Metadata is cached for five minutes. Refresh after
                              schema changes. No raw record values enter model
                              context.
                            </p>
                            <details>
                              <summary>Import Prisma context</summary>
                              <textarea
                                aria-label="Prisma schema"
                                rows={5}
                                value={prisma}
                                onChange={(e) => setPrisma(e.target.value)}
                                placeholder="model Customer { … }"
                              />
                              <button
                                className="q-button secondary"
                                disabled={busy || !prisma.trim()}
                                onClick={() =>
                                  void safely(async () => {
                                    const r = await api<{ models: unknown[] }>(
                                      `/connections/${selected}/prisma`,
                                      { source: prisma },
                                    );
                                    setNotice(
                                      `Imported ${r.models.length} models as optional context. Actual database metadata remains authoritative.`,
                                    );
                                  })
                                }
                              >
                                Import & compare
                              </button>
                            </details>
                          </>
                        )}
                      </div>
                    </aside>
                  </div>
                ))}
              {page === "connections" && (
                <>
                  <div className="q-demo-banner">
                    <Otter small />
                    <div>
                      <strong>Start with a synthetic database</strong>
                      <p>
                        Add a synthetic shop database copy. No customer
                        credentials or records needed.
                      </p>
                    </div>
                    <button
                      className="q-button secondary"
                      onClick={() => void addSeed()}
                      disabled={busy}
                    >
                      <Plus size={15} />
                      Add demo copy
                    </button>
                  </div>
                  {connections.length === 0 ? (
                    <Empty title="Add your first connection">
                      <p>
                        Choose a provider or start with a synthetic SQLite copy.
                      </p>
                    </Empty>
                  ) : (
                    <div className="q-connection-grid">
                      {connections.map((c) => (
                        <article
                          className="q-card q-connection-tile"
                          key={c.id}
                        >
                          <div>
                            <span className="q-database-avatar">
                              <Database size={23} />
                            </span>
                            <span
                              className={
                                "q-tag " +
                                (c.status === "connected" ? "good" : "")
                              }
                            >
                              {c.status === "connected"
                                ? "Connected"
                                : "Needs validation"}
                            </span>
                          </div>
                          <h2>{c.label}</h2>
                          <p>
                            {
                              catalog?.engines.find((e) => e.id === c.engine)
                                ?.name
                            }{" "}
                            ·{" "}
                            {
                              catalog?.providers.find(
                                (p) => p.id === c.provider,
                              )?.name
                            }
                          </p>
                          <p className="q-connection-host">
                            {c.summary.masked_url || c.summary.scope}
                          </p>
                          <dl>
                            <dt>Access</dt>
                            <dd>
                              {c.status === "connected"
                                ? "Read-only checked"
                                : "Read-only required"}
                            </dd>
                            <dt>Last validated</dt>
                            <dd>{when(c.validated)}</dd>
                            <dt>Scope</dt>
                            <dd>{c.summary.schema || c.summary.scope}</dd>
                          </dl>
                          <div className="q-tile-actions">
                            <button
                              className="q-button secondary"
                              onClick={() => {
                                choose(c.id);
                                location.hash = "workspace";
                              }}
                            >
                              Explore
                            </button>
                            <button
                              aria-label={`Rotate ${c.label} secrets`}
                              disabled={session.demo || busy}
                              onClick={() => {
                                setRotation(c);
                                setConnectionDialog(true);
                              }}
                            >
                              <RefreshCw size={15} />
                            </button>
                            <button
                              aria-label={`Remove ${c.label}`}
                              onClick={() => askRemove(c)}
                              disabled={busy}
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                  <p className="q-note">
                    A successful connection test verifies credentials and
                    discovery; generation and bounded execution must be checked
                    separately.
                  </p>
                </>
              )}
              {page === "optimization" &&
                (!connection ? (
                  <Empty title="Select a database to investigate">
                    <p>Start with a connection or a synthetic copy.</p>
                    <a href="#connections">Open connections</a>
                  </Empty>
                ) : (
                  <>
                    <div className="q-card q-optimization-query">
                      <div className="q-card-heading">
                        <FlaskConical size={18} />
                        <h2>Query under investigation</h2>
                        <span className="q-tag">
                          {connection.capabilities?.query_plans
                            ? "Plan evidence available"
                            : "Limited native recommendations"}
                        </span>
                      </div>
                      <label className="q-sr-only" htmlFor="q-opt-query">
                        Query to optimize
                      </label>
                      <textarea
                        id="q-opt-query"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        rows={5}
                        placeholder="Paste a native read-only query, or generate one in the query workspace."
                        spellCheck={false}
                      />
                      <div className="q-editor-footer">
                        <span>No connected production indexes are changed</span>
                        <button
                          className="q-button"
                          disabled={busy || !query}
                          onClick={() => void run("optimize")}
                        >
                          <MessageSquare size={15} />
                          Investigate
                        </button>
                      </div>
                    </div>
                    {optimization && (
                      <>
                        <div className="q-card q-explanation">
                          <h2>What the evidence suggests</h2>
                          <p>{optimization.diagnosis}</p>
                          {optimization.recommendations?.map((r) => (
                            <p key={r}>{r}</p>
                          ))}
                          <span className="q-tag">
                            Recommendations · unmeasured
                          </span>
                          <details>
                            <summary>Actual plan evidence</summary>
                            <pre>
                              {JSON.stringify(optimization.plan, null, 2)}
                            </pre>
                          </details>
                        </div>
                        <div className="q-candidate-grid">
                          {optimization.candidates?.map((c, i) => (
                            <article className="q-card q-candidate" key={i}>
                              <span className="q-entry-meta">
                                Candidate {i + 1} · ranked hypothesis
                              </span>
                              <h2>{c.name}</h2>
                              <p>{c.hypothesis}</p>
                              <pre>{queryText(c.query)}</pre>
                              {c.indexes.length > 0 && (
                                <details>
                                  <summary>
                                    Proposed indexes · never applied to
                                    production
                                  </summary>
                                  <pre>{c.indexes.join("\n")}</pre>
                                </details>
                              )}
                              <p className="q-note">
                                Semantics and latency are not verified yet.
                              </p>
                              <div>
                                <button
                                  className="q-button secondary"
                                  disabled={busy}
                                  onClick={() => {
                                    setQuery(queryText(c.query));
                                    setDraft(null);
                                    location.hash = "workspace";
                                  }}
                                >
                                  Review query
                                </button>
                                <button
                                  className="q-button"
                                  disabled={
                                    busy ||
                                    !connection.capabilities
                                      ?.controlled_benchmarking
                                  }
                                  onClick={() =>
                                    void run("benchmark", {
                                      candidate: queryText(c.query),
                                      indexes: c.indexes,
                                    })
                                  }
                                >
                                  <FlaskConical size={14} />
                                  Benchmark copy
                                </button>
                              </div>
                            </article>
                          ))}
                        </div>
                        {!optimization.candidates?.length && (
                          <Empty
                            title="No validated candidates"
                            icon={ShieldCheck}
                          >
                            <p>
                              The query may already be appropriate, or the
                              available evidence is limited.
                            </p>
                          </Empty>
                        )}
                      </>
                    )}
                    {connection.capabilities?.controlled_benchmarking && (
                      <section className="q-card q-manual-benchmark">
                        <div className="q-card-heading">
                          <FlaskConical size={18} />
                          <h2>Compare a rewrite in this copy</h2>
                          <span className="q-tag">No model call needed</span>
                        </div>
                        <p>
                          Use the query above as the baseline. The candidate
                          must preserve its output columns, duplicates, NULLs
                          and ordering. A blank candidate compares the same
                          query with optional experimental indexes.
                        </p>
                        <label>
                          Candidate query
                          <textarea
                            rows={4}
                            value={manualCandidate}
                            onChange={(e) => setManualCandidate(e.target.value)}
                            maxLength={12000}
                            placeholder="Optional rewrite; leave blank to retain the baseline query"
                            spellCheck={false}
                          />
                        </label>
                        <label>
                          Experimental indexes · copy only
                          <textarea
                            rows={2}
                            value={manualIndexes}
                            onChange={(e) => setManualIndexes(e.target.value)}
                            maxLength={3000}
                            placeholder="Optional: one plain-column CREATE INDEX per line, maximum two"
                            spellCheck={false}
                          />
                        </label>
                        <button
                          className="q-button"
                          disabled={busy || !query}
                          onClick={() =>
                            void run("benchmark", {
                              candidate: manualCandidate || query,
                              indexes: manualIndexes
                                .split("\n")
                                .map((s) => s.trim())
                                .filter(Boolean),
                            })
                          }
                        >
                          Benchmark this copy <FlaskConical size={15} />
                        </button>
                      </section>
                    )}
                    {benchmark?.benchmark && (
                      <section className="q-card q-benchmark-report">
                        <div className="q-card-heading">
                          <Activity size={19} />
                          <h2>Observed copy benchmark</h2>
                          <span className="q-tag">
                            {benchmark.benchmark.correct
                              ? "Result comparison passed"
                              : "Result mismatch · rejected"}
                          </span>
                          <a
                            href={`/api/assistant/history/${benchmark.run_id}/export`}
                            download="queryotter-benchmark.json"
                            className="q-text-button"
                          >
                            <Download size={14} />
                            Export
                          </a>
                        </div>
                        <div className="q-metrics">
                          <Metric
                            label="Baseline median"
                            value={`${benchmark.benchmark.baseline?.median_ms.toFixed(3) || "—"} ms`}
                            note={`MAD ${benchmark.benchmark.baseline?.mad_ms.toFixed(3) || "—"} ms`}
                          />
                          <Metric
                            label="Candidate median"
                            value={`${benchmark.benchmark.candidate?.median_ms.toFixed(3) || "—"} ms`}
                            note={`MAD ${benchmark.benchmark.candidate?.mad_ms.toFixed(3) || "—"} ms`}
                          />
                          <Metric
                            label="Observed outcome"
                            value={
                              benchmark.benchmark.improvement_observed
                                ? `${benchmark.benchmark.speedup?.toFixed(2)}×`
                                : "No verified gain"
                            }
                            note="Disposable copy only"
                          />
                        </div>
                        <p>
                          Correctness scope: {benchmark.benchmark.scope.rows}{" "}
                          complete bounded rows;{" "}
                          {benchmark.benchmark.scope.comparison}.
                        </p>
                        <p>{benchmark.benchmark.methodology}</p>
                        <p>
                          Observed index allocation:{" "}
                          {
                            benchmark.benchmark.index_tradeoffs
                              .observed_allocated_bytes
                          }{" "}
                          bytes. {benchmark.benchmark.index_tradeoffs.writes}
                        </p>
                        <p className="q-note">
                          Other datasets and production performance remain
                          unverified.
                        </p>
                      </section>
                    )}
                    <a className="q-inline-link" href="#experiments">
                      Explore the controlled PostgreSQL benchmark portfolio{" "}
                    </a>
                  </>
                ))}
              {page === "history" && (
                <>
                  <div className="q-list-tools">
                    <span>{history.length} recent operations</span>
                    <button
                      className="q-text-button"
                      onClick={() =>
                        setConfirm({
                          title: "Clear query history?",
                          body: "Completed jobs, query history and result snapshots will be removed. Saved queries remain.",
                          action: async () => {
                            await api("/history/clear", {});
                            setHistory([]);
                            setResult(null);
                            setNotice("History cleared.");
                          },
                        })
                      }
                    >
                      Clear history <Trash2 size={14} />
                    </button>
                  </div>
                  {listLoading ? (
                    <div className="q-empty" role="status">
                      <LoaderCircle className="q-spin" /> Loading history…
                    </div>
                  ) : history.length === 0 ? (
                    <Empty title="No query history yet">
                      <p>
                        Your completed queries and investigations will appear
                        here.
                      </p>
                      <a href="#workspace">Ask your first question</a>
                    </Empty>
                  ) : (
                    <div className="q-history-list">
                      {history.map((h) => (
                        <article className="q-card" key={h.id}>
                          <span className="q-history-icon">
                            {h.kind === "generate" ? (
                              <MessageSquare size={18} />
                            ) : (
                              <Code2 size={18} />
                            )}
                          </span>
                          <div>
                            <span className="q-entry-meta">
                              {h.kind} · {when(h.created)}
                            </span>
                            <h3>
                              {h.prompt ||
                                h.query?.slice(0, 100) ||
                                "Connection discovery"}
                            </h3>
                            <p>
                              {
                                connections.find(
                                  (c) => c.id === h.connection_id,
                                )?.label
                              }{" "}
                              · {Number(h.usage.seconds || 0).toFixed(2)} s ·{" "}
                              {Number(h.usage.model_calls || 0)} model calls
                            </p>
                          </div>
                          <button
                            className="q-button secondary"
                            disabled={!h.query}
                            onClick={() => load(h, true)}
                          >
                            Open
                          </button>
                        </article>
                      ))}
                    </div>
                  )}
                </>
              )}
              {page === "saved" &&
                (listLoading ? (
                  <div className="q-empty" role="status">
                    <LoaderCircle className="q-spin" /> Loading saved queries…
                  </div>
                ) : saved.length === 0 ? (
                  <Empty title="Save a query for later">
                    <p>
                      Select Save in the native editor. It stays linked to the
                      original database.
                    </p>
                    <a href="#workspace">Open query workspace</a>
                  </Empty>
                ) : (
                  <div className="q-connection-grid">
                    {saved.map((s) => (
                      <article className="q-card q-saved-card" key={s.id}>
                        <Code2 size={21} />
                        <h2>{s.name}</h2>
                        <p>
                          {
                            connections.find((c) => c.id === s.connection_id)
                              ?.label
                          }
                        </p>
                        <pre>{s.query}</pre>
                        <div>
                          <button
                            className="q-button secondary"
                            onClick={() => load(s)}
                          >
                            Review query
                          </button>
                          <button
                            aria-label={`Delete saved query ${s.name}`}
                            onClick={() =>
                              setConfirm({
                                title: "Remove this saved query?",
                                body: s.name,
                                action: async () => {
                                  await api(`/saved/${s.id}/remove`, {});
                                  setSaved((old) =>
                                    old.filter((q) => q.id !== s.id),
                                  );
                                },
                              })
                            }
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                ))}
              {page === "settings" && (
                <div className="q-settings-grid">
                  <section className="q-card q-settings-card">
                    <h2>Workspace preferences</h2>
                    <label>
                      Workspace name
                      <input
                        value={workspaceName}
                        onChange={(e) => setWorkspaceName(e.target.value)}
                        maxLength={80}
                      />
                    </label>
                    <label>
                      IANA time zone
                      <input
                        value={timezone}
                        onChange={(e) => setTimezone(e.target.value)}
                        placeholder="Europe/Paris"
                      />
                    </label>
                    <label>
                      History retention
                      <select
                        value={retention}
                        onChange={(e) => setRetention(Number(e.target.value))}
                      >
                        {[1, 7, 14, 30, 60, 90].map((n) => (
                          <option key={n} value={n}>
                            {n} days
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="q-note">
                      Result snapshots expire in 15 minutes. Expired history is
                      pruned on account activity and maintenance.
                    </p>
                    <button
                      className="q-button"
                      onClick={() =>
                        void safely(async () => {
                          await api("/settings", {
                            name: workspaceName,
                            timezone,
                            retention_days: retention,
                          });
                          await refreshData();
                          setNotice("Preferences saved.");
                        })
                      }
                    >
                      <Check size={15} />
                      Save preferences
                    </button>
                  </section>
                  <section className="q-card q-settings-card">
                    <h2>Your usage</h2>
                    <div className="q-budget-number">
                      {session.usage?.tokens_used_or_reserved.toLocaleString()}
                      <small>
                        {" "}
                        / {session.usage?.daily_token_limit.toLocaleString()}{" "}
                        tokens today
                      </small>
                    </div>
                    <progress
                      value={session.usage?.tokens_used_or_reserved || 0}
                      max={session.usage?.daily_token_limit || 1}
                    />
                    <div className="q-metrics">
                      <Metric
                        label="Model calls · 24h"
                        value={session.usage?.last_24h.model_calls || 0}
                      />
                      <Metric
                        label="Database calls · 24h"
                        value={session.usage?.last_24h.database_calls || 0}
                      />
                      <Metric
                        label="Estimated cost · 24h"
                        value={
                          "$" +
                          Number(
                            session.usage?.last_24h.estimated_cost_usd || 0,
                          ).toFixed(5)
                        }
                      />
                    </div>
                    <p className="q-note">{session.usage?.cost_note}</p>
                    <p>
                      One active operation, ten connections, 100 saved queries.
                      Public demo model calls share a global daily limit.
                    </p>
                    <button
                      className="q-button secondary"
                      onClick={() => void safely(refreshData)}
                    >
                      Refresh usage <RefreshCw size={14} />
                    </button>
                  </section>
                  <section className="q-card q-settings-card">
                    <h2>Private network connectors</h2>
                    <p>
                      Install a scoped outbound connector on a machine that can
                      reach your database. Credentials stay on that machine.
                    </p>
                    <a
                      className="q-inline-link"
                      href="https://github.com/wauul/queryotter/blob/main/docs/local-connector.md"
                      target="_blank"
                      rel="noreferrer"
                    >
                      Installation instructions <ExternalLink size={14} />
                    </a>
                    {connectors.map((c) => (
                      <div className="q-connector-row" key={c.id}>
                        <span>
                          <strong>{c.label}</strong>
                          <small>Last seen {when(c.last_seen)}</small>
                        </span>
                        <button
                          aria-label={`Revoke ${c.label}`}
                          onClick={() =>
                            setConfirm({
                              title: "Revoke this connector?",
                              body: "Its token stops working and pending tasks are removed.",
                              action: async () => {
                                await api(`/connectors/${c.id}/remove`, {});
                                setConnectors((old) =>
                                  old.filter((x) => x.id !== c.id),
                                );
                                setEnrollment(null);
                              },
                            })
                          }
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ))}
                    <label>
                      Connector label
                      <input
                        value={connectorLabel}
                        onChange={(e) => setConnectorLabel(e.target.value)}
                      />
                    </label>
                    <button
                      className="q-button secondary"
                      disabled={session.demo}
                      onClick={() =>
                        void safely(async () => {
                          const r = await api<{ id: string; token: string }>(
                            "/connectors",
                            { label: connectorLabel },
                          );
                          setEnrollment(r);
                          setConnectors(await api("/connectors"));
                        })
                      }
                    >
                      <Plus size={15} />
                      Enroll local connector
                    </button>
                    {enrollment && (
                      <div className="q-enrollment">
                        <strong>
                          Shown once · store on your connector machine
                        </strong>
                        <label>
                          Connector ID
                          <input readOnly value={enrollment.id} />
                        </label>
                        <label>
                          Connector token
                          <input
                            type="password"
                            readOnly
                            value={enrollment.token}
                          />
                        </label>
                        <button
                          className="q-button secondary"
                          onClick={() =>
                            void navigator.clipboard
                              .writeText(enrollment.token)
                              .then(() =>
                                setNotice(
                                  "Connector token copied. Keep it private.",
                                ),
                              )
                              .catch(() =>
                                setError(
                                  "Clipboard access unavailable. Select the token field and copy manually.",
                                ),
                              )
                          }
                        >
                          Copy token
                        </button>
                        <button
                          className="q-text-button"
                          onClick={() => setEnrollment(null)}
                        >
                          Hide token
                        </button>
                      </div>
                    )}
                  </section>
                  <section className="q-card q-settings-card">
                    <h2>Account & data</h2>
                    <p>
                      {session.user.name}
                      {session.user.email ? " · " + session.user.email : ""}
                    </p>
                    <p>
                      Your connection secrets are excluded from account export.
                      Export unexpired results separately from their result
                      table.
                    </p>
                    <a
                      className="q-button secondary"
                      href="/api/assistant/account/export"
                    >
                      <Download size={15} />
                      Export account data
                    </a>
                    <div className="q-danger-zone">
                      <h3>Delete your account</h3>
                      <p>
                        Revoke sessions and connectors and remove connections,
                        schemas, saved queries, jobs, history and results from
                        the active application. Hosting backups expire under
                        provider retention policies.
                      </p>
                      <label>
                        Enter DELETE to confirm
                        <input
                          value={deleteText}
                          onChange={(e) => setDeleteText(e.target.value)}
                          placeholder="DELETE"
                        />
                      </label>
                      <button
                        className="q-button danger"
                        disabled={deleteText !== "DELETE" || busy}
                        onClick={() =>
                          setConfirm({
                            title: "Permanently delete this account?",
                            body: "All active application account data will be removed. This cannot be undone.",
                            action: async () => {
                              await api("/account/delete", {
                                confirmation: deleteText,
                              });
                              clearWorkspace();
                              location.hash = "home";
                              setNotice(
                                "Account deleted and access revoked. Hosting backups follow provider retention.",
                              );
                            },
                          })
                        }
                      >
                        Delete account <Trash2 size={15} />
                      </button>
                    </div>
                    <nav className="q-legal-links">
                      <a href="#privacy">Privacy</a>
                      <a href="#terms">Terms</a>
                      <a href="#support">Support</a>
                    </nav>
                  </section>
                </div>
              )}
            </main>
            <footer className="q-workspace-footer">
              <span>QueryOtter · reviewed queries, measured changes</span>
              <a href="#privacy">Privacy</a>
              <a href="#terms">Terms</a>
              <a href="#support">Support</a>
            </footer>
          </div>
        </div>
      )}
      {auth && (
        <div className="q-overlay">
          <section
            className="q-dialog q-auth-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="q-signin-title"
          >
            <button
              className="q-dialog-close"
              aria-label="Close sign-in"
              onClick={() => setAuth(false)}
            >
              <X size={20} />
            </button>
            <Otter />

            <h2 id="q-signin-title">Sign in to QueryOtter</h2>
            <p>
              Use your own workspace for connections, saved queries and private
              history.
            </p>
            {(catalog?.authentication || session?.authentication || []).map(
              (p) => (
                <button
                  className="q-oauth-button"
                  key={p.id}
                  disabled={!p.configured || busy}
                  onClick={() => void signIn(p.id)}
                >
                  <span>
                    {p.id === "github" ? (
                      <GitBranch size={17} />
                    ) : (
                      p.name.charAt(0)
                    )}
                  </span>
                  Continue with {p.name}
                  <small>{p.configured ? p.status : "Setup required"}</small>
                </button>
              ),
            )}
            <p className="q-note">
              Provider status shows the sign-in flows that have been checked.
              Microsoft organization accounts may require publisher
              verification.
            </p>
            <button
              className="q-button secondary"
              onClick={() => void startDemo()}
              disabled={busy}
            >
              Try the synthetic demo
            </button>
            <details className="q-owner-login">
              <summary>Owner access</summary>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void safely(async () => {
                    await api("/auth/owner", { password: ownerPass });
                    setOwnerPass("");
                    setAuth(false);
                    await refresh();
                    location.hash = "workspace";
                  });
                }}
              >
                <label>
                  Owner password
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={ownerPass}
                    onChange={(e) => setOwnerPass(e.target.value)}
                    required
                  />
                </label>
                <button className="q-button">Sign in as owner</button>
              </form>
            </details>
            {error && (
              <p className="q-error" role="alert">
                {error}
              </p>
            )}
            <p className="q-auth-terms">
              By using QueryOtter, review its{" "}
              <a href="#terms" onClick={() => setAuth(false)}>
                terms
              </a>{" "}
              and{" "}
              <a href="#privacy" onClick={() => setAuth(false)}>
                privacy policy
              </a>
              .
            </p>
          </section>
        </div>
      )}
      {connectionDialog && catalog && (
        <StudioConnection
          catalog={catalog}
          rotate={rotation}
          close={() => setConnectionDialog(false)}
          onSaved={(c) => {
            setConnections((old) => [c, ...old.filter((x) => x.id !== c.id)]);
            choose(c.id);
            setConnectionDialog(false);
            setNotice(
              "Connection saved with secrets masked. Test & discover before use.",
            );
            location.hash = "workspace";
          }}
        />
      )}
      {saveDialog && (
        <div className="q-overlay">
          <section
            className="q-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="q-save-title"
          >
            <h2 id="q-save-title">Save this query</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (savingQuery) return;
                setSavingQuery(true);
                const revision = sessionRevision.current;
                void safely(async () => {
                  try {
                    const item = await api<{ id: string }>("/saved", {
                      connection_id: selected,
                      name: saveName,
                      query,
                      prompt,
                    });
                    if (
                      !mounted.current ||
                      revision !== sessionRevision.current
                    )
                      return;
                    setSaved((old) =>
                      [
                        {
                          id: item.id,
                          connection_id: selected,
                          name: saveName,
                          query,
                          prompt,
                          updated: Date.now() / 1000,
                        },
                        ...old,
                      ].slice(0, 100),
                    );
                    setSaveDialog(false);
                    setNotice("Query saved to this workspace.");
                  } finally {
                    if (mounted.current) setSavingQuery(false);
                  }
                });
              }}
            >
              <label>
                Query name
                <input
                  autoFocus
                  disabled={savingQuery}
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  required
                  maxLength={100}
                />
              </label>
              <footer>
                <button
                  type="button"
                  className="q-button secondary"
                  onClick={() => setSaveDialog(false)}
                >
                  Cancel
                </button>
                <button className="q-button" disabled={savingQuery}>
                  {savingQuery ? "Saving query…" : "Save query"}
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}
      {confirm && (
        <div className="q-overlay">
          <section
            className="q-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="q-confirm-title"
          >
            <h2 id="q-confirm-title">{confirm.title}</h2>
            <p>{confirm.body}</p>
            <footer>
              <button
                className="q-button secondary"
                onClick={() => setConfirm(null)}
              >
                Keep it
              </button>
              <button
                className="q-button danger"
                onClick={() =>
                  void safely(async () => {
                    await confirm.action();
                    setConfirm(null);
                  })
                }
              >
                Confirm removal
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}
