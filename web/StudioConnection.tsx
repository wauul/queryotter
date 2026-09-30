import { useLanguage } from "./Language";
import React, { useState } from "react";
import { useModal } from "./useModal";
import {
  Database,
  LockKeyhole,
  ExternalLink,
  Upload,
  ArrowRight,
  X,
  ShieldCheck,
} from "lucide-react";
import { api, type Catalog, type Connection } from "./studio-api";

export default function StudioConnection({
  catalog,
  close,
  onSaved,
  rotate,
}: {
  catalog: Catalog;
  close: () => void;
  onSaved: (c: Connection) => void;
  rotate?: Connection;
}) {
  const { t: tr } = useLanguage();

  useModal(true, close);
  const [provider, setProvider] = useState(rotate?.provider || "neon");
  const [engine, setEngine] = useState(rotate?.engine || "postgresql");
  const [label, setLabel] = useState(rotate?.label || "");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState("url");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("5432");
  const [database, setDatabase] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [schema, setSchema] = useState(rotate?.summary.schema || "public");
  const [ca, setCa] = useState("");
  const [data, setData] = useState("");
  const [filename, setFilename] = useState("");
  const [project, setProject] = useState("");
  const [firebaseDb, setFirebaseDb] = useState("(default)");
  const [service, setService] = useState("");
  const [infer, setInfer] = useState(false);
  const [authToken, setAuthToken] = useState("");
  const [connector, setConnector] = useState("");
  const [profile, setProfile] = useState("");
  const [connectors, setConnectors] = useState<{ id: string; label: string }[]>(
    [],
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [parsed, setParsed] = useState("");
  const preset = catalog.providers.find((p) => p.id === provider)!;
  async function parse() {
    try {
      const r = await api<{ engine: string; host: string; database: string }>(
        "/parse-connection",
        { url },
      );
      setEngine(r.engine);
      setParsed(
        `${r.engine} · ${r.host} · ${r.database || "choose a database"}`,
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function upload(file: File | undefined) {
    if (!file) return;
    if (file.size > 2097152) {
      setError("SQLite copies must be at most 2 MiB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setData(String(reader.result).split(",")[1]);
      setFilename(file.name);
      setError("");
    };
    reader.readAsDataURL(file);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const config: Record<string, unknown> = { tls: "verify-full" };
      if (mode === "connector") {
        config.connector_id = connector;
        config.profile = profile;
      } else if (engine === "sqlite" && provider !== "turso") {
        if (!data) throw new Error("Upload a SQLite database copy.");
        config.data = data;
      } else if (engine === "firestore") {
        config.project_id = project;
        config.database_id = firebaseDb;
        config.service_account = JSON.parse(service);
        config.infer_document_schema = infer;
      } else {
        const scheme = (
          {
            postgresql: "postgresql",
            cockroachdb: "postgresql",
            mysql: "mysql",
            mariadb: "mariadb",
            sqlserver: "mssql",
            mongodb: "mongodb",
          } as Record<string, string>
        )[engine];
        config.url =
          mode === "form"
            ? `${scheme}://${encodeURIComponent(username)}:${encodeURIComponent(password)}@${host}:${port}/${encodeURIComponent(database)}`
            : url;
        if (engine === "firebase_realtime")
          config.service_account = JSON.parse(service);
        if (engine === "mongodb" || engine === "firebase_realtime")
          config.infer_document_schema = infer;
        if (provider === "turso") config.auth_token = authToken;
        if (
          [
            "postgresql",
            "cockroachdb",
            "mysql",
            "mariadb",
            "sqlserver",
          ].includes(engine)
        )
          config.schema = schema;
      }
      if (ca) config.ca_certificate = ca;
      const c = await api<Connection>(
        rotate ? `/connections/${rotate.id}/rotate` : "/connections",
        { label, engine, provider, config },
      );
      onSaved(c);
    } catch (e) {
      setError(
        e instanceof SyntaxError
          ? "Service account must be valid JSON."
          : (e as Error).message,
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="q-overlay">
      <section
        className="q-dialog q-connection-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="q-connect-title"
      >
        <div className="q-dialog-head">
          <div>
            <h2 id="q-connect-title">
              {rotate
                ? tr("Rotate connection secrets")
                : tr("Connect your database")}
            </h2>
          </div>
          <button aria-label={tr("Close connection dialog")} onClick={close}>
            <X size={21} />
          </button>
        </div>
        <form onSubmit={save}>
          <div className="q-field-row">
            <label>
              {tr("Provider")}
              <select
                value={provider}
                onChange={(e) => {
                  const p = catalog.providers.find(
                    (p) => p.id === e.target.value,
                  )!;
                  setProvider(p.id);
                  setEngine(p.engines[0]);
                  setSchema(p.default_schema || "public");
                }}
                disabled={!!rotate}
              >
                {catalog.providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {tr(p.name)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {tr("Database engine")}
              <select
                value={engine}
                onChange={(e) => {
                  setEngine(e.target.value);
                  setPort(
                    (
                      {
                        mysql: "3306",
                        mariadb: "3306",
                        sqlserver: "1433",
                        cockroachdb: "26257",
                        mongodb: "27017",
                      } as Record<string, string>
                    )[e.target.value] || "5432",
                  );
                  setSchema(e.target.value === "sqlserver" ? "dbo" : "public");
                }}
                disabled={!!rotate}
              >
                {catalog.engines
                  .filter((e) => preset.engines.includes(e.id))
                  .map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <label>
            {tr("Connection name")}
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={tr("Analytics · read only")}
              required
              maxLength={100}
            />
          </label>
          <div className="q-provider-guide">
            <ShieldCheck size={19} />
            <div>
              <strong>
                {tr(preset.name)}
                {tr(" connection guide")}
              </strong>
              <p>{tr(preset.instructions)}</p>
              <a href={preset.docs} target="_blank" rel="noreferrer">
                {tr("Official documentation ")}
                <ExternalLink size={12} />
              </a>
            </div>
          </div>
          <div className="q-segment">
            {["url", "form", "connector"]
              .filter(
                (m) =>
                  m !== "form" ||
                  !["sqlite", "firestore", "firebase_realtime"].includes(
                    engine,
                  ),
              )
              .map((m) => (
                <button
                  type="button"
                  key={m}
                  className={mode === m ? "selected" : ""}
                  aria-pressed={mode === m}
                  onClick={() => {
                    setMode(m);
                    if (m === "connector")
                      api<{ id: string; label: string }[]>("/connectors")
                        .then(setConnectors)
                        .catch((e) => setError(e.message));
                  }}
                >
                  {m === "url"
                    ? tr("URL or file")
                    : m === "form"
                      ? tr("Guided form")
                      : tr("Connector")}
                </button>
              ))}
          </div>
          {mode === "connector" ? (
            <>
              <label>
                {tr("Enrolled connector")}
                <select
                  value={connector}
                  onChange={(e) => setConnector(e.target.value)}
                  required
                >
                  <option value="">{tr("Choose a connector")}</option>
                  {connectors.map((c) => (
                    <option value={c.id} key={c.id}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {tr("Local profile name")}
                <input
                  value={profile}
                  onChange={(e) => setProfile(e.target.value)}
                  placeholder={tr("local-shop")}
                  required
                />
              </label>
              <p className="q-note">
                {tr(
                  "Enroll a connector in Settings first. The cloud app cannot access your localhost automatically. Credentials stay on the connector machine.",
                )}
              </p>
            </>
          ) : engine === "sqlite" && provider !== "turso" ? (
            <label className="q-upload">
              <Upload size={24} />
              <strong>{filename || "Upload a SQLite copy"}</strong>
              <span>{tr(".sqlite, .db · maximum 2 MiB")}</span>
              <input
                aria-label={tr("SQLite database file")}
                type="file"
                accept=".db,.sqlite,.sqlite3"
                onChange={(e) => void upload(e.target.files?.[0])}
              />
              <small>{tr("Queries and experiments run against a copy.")}</small>
            </label>
          ) : (
            <>
              {engine === "firestore" ? (
                <div className="q-field-row">
                  <label>
                    {tr("Firebase project ID")}
                    <input
                      value={project}
                      onChange={(e) => setProject(e.target.value)}
                      required
                    />
                  </label>
                  <label>
                    {tr("Firestore database ID")}
                    <input
                      value={firebaseDb}
                      onChange={(e) => setFirebaseDb(e.target.value)}
                      required
                    />
                  </label>
                </div>
              ) : mode === "form" ? (
                <>
                  <div className="q-field-row">
                    <label>
                      {tr("Hostname")}
                      <input
                        value={host}
                        onChange={(e) => setHost(e.target.value)}
                        required
                        placeholder={tr("db.example.com")}
                      />
                    </label>
                    <label>
                      {tr("Port")}
                      <input
                        inputMode="numeric"
                        value={port}
                        onChange={(e) => setPort(e.target.value)}
                        required
                      />
                    </label>
                  </div>
                  <label>
                    {tr("Database")}
                    <input
                      value={database}
                      onChange={(e) => setDatabase(e.target.value)}
                      required
                    />
                  </label>
                  <div className="q-field-row">
                    <label>
                      {tr("Read-only username")}
                      <input
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        autoComplete="off"
                        required
                      />
                    </label>
                    <label>
                      {tr("Password")}
                      <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete="new-password"
                        required
                      />
                    </label>
                  </div>
                </>
              ) : (
                <label>
                  {engine === "firebase_realtime"
                    ? tr("Realtime Database HTTPS URL")
                    : provider === "turso"
                      ? tr("Turso / libSQL database URL")
                      : tr("Connection URL")}
                  <input
                    type="password"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder={
                      provider === "turso"
                        ? "libsql://database-org.turso.io"
                        : tr("Paste the provider connection string")
                    }
                    autoComplete="new-password"
                    required
                  />
                  <button
                    type="button"
                    className="q-text-button"
                    onClick={() => void parse()}
                    disabled={engine === "firebase_realtime"}
                  >
                    {tr("Detect engine and database ")}
                    <ArrowRight size={12} />
                  </button>
                  {parsed && <small>{parsed}</small>}
                </label>
              )}
              {provider === "turso" && (
                <label>
                  {tr("Read-only database token")}
                  <input
                    type="password"
                    value={authToken}
                    onChange={(e) => setAuthToken(e.target.value)}
                    required
                    autoComplete="new-password"
                  />
                </label>
              )}
              {[
                "postgresql",
                "cockroachdb",
                "mysql",
                "mariadb",
                "sqlserver",
              ].includes(engine) && (
                <label>
                  {tr("Database schema")}
                  <input
                    value={schema}
                    onChange={(e) => setSchema(e.target.value)}
                    required
                    placeholder={
                      engine === "sqlserver" ? tr("dbo") : tr("public")
                    }
                  />
                </label>
              )}
              {["firestore", "firebase_realtime"].includes(engine) && (
                <label>
                  {tr("Dedicated read-only service account JSON")}
                  <textarea
                    value={service}
                    onChange={(e) => setService(e.target.value)}
                    className="q-secret-json"
                    rows={3}
                    required
                    placeholder={tr(
                      "Paste a dedicated viewer service account key",
                    )}
                  />
                </label>
              )}
              {["mongodb", "firestore", "firebase_realtime"].includes(
                engine,
              ) && (
                <label className="q-checkbox">
                  <input
                    type="checkbox"
                    checked={infer}
                    onChange={(e) => setInfer(e.target.checked)}
                  />
                  <span>
                    {tr(
                      "Infer document field names/types from up to 20 records per collection. Record values stay local to the worker and are not sent to Groq. Inference remains incomplete.",
                    )}
                  </span>
                </label>
              )}
              <details>
                <summary>{tr("Verified TLS and custom CA")}</summary>
                <p className="q-note">
                  {tr(
                    "TLS always verifies the server certificate and hostname. Use a provider CA bundle when its certificate is not publicly trusted.",
                  )}
                </p>
                <label>
                  {tr("CA certificate PEM (optional)")}
                  <textarea
                    rows={3}
                    value={ca}
                    onChange={(e) => setCa(e.target.value)}
                    placeholder={tr("-----BEGIN CERTIFICATE-----")}
                  />
                </label>
              </details>
            </>
          )}
          <p className="q-security-line">
            <LockKeyhole size={14} />
            {tr(
              "Secrets are encrypted and masked. Saving does not run a query.",
            )}
          </p>
          {error && (
            <p role="alert" className="q-error">
              {tr(error)}
            </p>
          )}
          <footer>
            <button
              type="button"
              className="q-button secondary"
              onClick={close}
            >
              {tr("Cancel")}
            </button>
            <button className="q-button" disabled={saving}>
              {saving
                ? tr("Saving…")
                : rotate
                  ? tr("Rotate secrets")
                  : tr("Save connection")}
              <Database size={16} />
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
