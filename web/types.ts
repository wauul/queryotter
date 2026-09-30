export type Example = {
  id: string;
  title: string;
  category: string;
  sql: string;
};
export type Latency = {
  median_ms: number;
  min_ms: number;
  max_ms: number;
  mad_ms: number;
  samples_ms: number[];
};
export type PlanNode = {
  depth: number;
  "Node Type": string;
  "Relation Name"?: string;
  "Index Name"?: string;
  "Actual Total Time"?: number;
  "Plan Rows"?: number;
  "Actual Rows"?: number;
  "Total Cost"?: number;
};
export type Candidate = {
  name: string;
  hypothesis: string;
  query: string;
  indexes: string[];
  status: string;
  reason?: string;
  original?: Latency;
  optimized?: Latency;
  speedup?: number;
  index_build_ms?: number;
  index_bytes?: number;
  tradeoff?: string;
  plan?: PlanNode[];
  correctness: {
    passed: boolean;
    datasets: { size: number; seed: number; edges: boolean; passed: boolean }[];
  };
};
export type Report = {
  query: string;
  diagnosis: string;
  candidates: Candidate[];
  best: Candidate | null;
  original: Latency | null;
  plan_before: PlanNode[];
  schema: { columns: string[][]; indexes: string[][]; version: string };
  conditions: Record<string, unknown>;
  usage: Record<string, number | string | null>;
  limitations: string[];
  migration: string[];
};
export type Job = {
  id: string;
  case_id: string;
  query: string;
  state: string;
  created: number;
  error?: string;
  report: Report | null;
  events: { stage: string; message: string; at: number }[];
};
