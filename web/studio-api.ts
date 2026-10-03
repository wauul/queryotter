export interface Engine {
  id: string;
  name: string;
  capabilities: Record<string, boolean>;
  limitations: string[];
  verification: {
    status: string;
    version?: string;
    generation?: string;
    hosted_provider: string;
    tests?: string[];
  };
}
export interface Provider {
  id: string;
  name: string;
  engines: string[];
  instructions: string;
  docs: string;
  tls: string;
  authentication: string;
  default_schema?: string;
  limitation?: string;
}
export interface AuthProvider {
  id: string;
  name: string;
  configured: boolean;
  status: string;
}
export interface Catalog {
  engines: Engine[];
  providers: Provider[];
  authentication: AuthProvider[];
}
export interface Session {
  user: { id: string; name: string; email?: string } | null;
  demo?: boolean;
  workspace?: {
    id: string;
    name: string;
    onboarded: number;
    retention_days: number;
    timezone: string;
  };
  usage?: {
    daily_token_limit: number;
    tokens_used_or_reserved: number;
    last_24h: Record<string, number>;
    cost_note: string;
  };
  authentication: AuthProvider[];
}
export interface Connection {
  id: string;
  configuration_revision?: string;
  label: string;
  engine: string;
  provider: string;
  status: string;
  validated?: number;
  capabilities: Record<string, boolean> | null;
  summary: {
    scope: string;
    masked_url?: string;
    host?: string;
    schema?: string;
  };
}
export interface Metadata {
  engine: string;
  version: string;
  tables: {
    name: string;
    schema: string;
    columns: {
      name: string;
      type: string;
      nullable: boolean;
      may_be_missing?: boolean;
    }[];
    inferred?: boolean;
    sampled_documents?: number;
  }[];
  indexes: unknown[];
  relationships: unknown[];
  complete: boolean;
  limitations: string[];
}
export interface Job {
  id: string;
  state: string;
  events: { stage: string; message: string; at: number }[];
  report: AssistantReport | null;
  error: string | null;
}
export interface Candidate {
  name: string;
  query: string | Record<string, unknown>;
  hypothesis: string;
  indexes: string[];
  status: string;
  correctness_verified: boolean;
}
export interface AssistantReport {
  run_id: string;
  connection_id: string;
  engine: string;
  version: string;
  query?: string | Record<string, unknown> | null;
  clarification?: string | null;
  explanation?: string;
  assumptions?: string[];
  validation?: {
    syntactically_valid: boolean;
    executable: boolean | null;
    business_meaning_verified: boolean;
  };
  validation_error?: string;
  requires_run?: boolean;
  result_ready?: boolean;
  row_count?: number;
  elapsed_ms?: number;
  metadata?: Metadata;
  capabilities?: Record<string, boolean>;
  usage: Record<string, number | string | boolean | null>;
  plan?: unknown;
  diagnosis?: string;
  recommendations?: string[];
  candidates?: Candidate[];
  benchmark?: {
    correct: boolean;
    improvement_observed: boolean;
    speedup: number | null;
    baseline: { median_ms: number; mad_ms: number } | null;
    candidate: { median_ms: number; mad_ms: number } | null;
    scope: { rows: number; comparison: string };
    index_tradeoffs: { observed_allocated_bytes: number; writes: string };
    methodology: string;
    experimental_indexes: string[];
  };
}
export interface Result {
  columns: string[];
  rows: unknown[][];
  documents: Record<string, unknown>[];
  row_count: number;
  page: number;
  page_size: number;
  truncated: boolean;
  elapsed_ms: number;
  pagination: string;
}
export interface HistoryEntry {
  id: string;
  connection_id: string;
  kind: string;
  query: string | null;
  prompt: string | null;
  summary: AssistantReport;
  created: number;
  usage: Record<string, unknown>;
}
export interface Saved {
  id: string;
  connection_id: string;
  name: string;
  query: string;
  prompt: string | null;
}
export const queryText = (query: unknown) =>
  typeof query === "string"
    ? query
    : query
      ? JSON.stringify(query, null, 2)
      : "";
export const when = (seconds?: number, locale = "en-GB") =>
  seconds
    ? new Date(seconds * 1000).toLocaleString(locale)
    : "Not yet validated";
import { monitoredFetch } from "./monitoring";
export async function api<T>(path: string, body?: unknown): Promise<T> {
  return monitoredFetch("/api/assistant" + path, body) as Promise<T>;
}
