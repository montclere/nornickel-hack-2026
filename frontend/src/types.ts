// Типы ответов API «Феникс» — зеркало pydantic-сущностей бэкенда
// (app/service/entities.py). Единственный источник формы данных — там.

export type Origin = "gap" | "reanimation" | "contradiction";
export type Sign = "+" | "-" | "0";
export type Decision = "accept" | "reject" | "edit";

export interface Edge {
  source: string;
  target: string;
  sign: Sign;
  conditions: Record<string, unknown>;
  doc_id: string;
  evidence_quote: string;
  year: number;
}

export interface MetricBreakdown {
  value: number;
  components: Record<string, number>;
}

export interface GraveyardCheck {
  warning: boolean;
  report_ref: string | null;
  reason: string | null;
  difference: string | null;
}

export interface ExperimentProtocol {
  method: string;
  equipment: string;
  duration_days: number;
  cost_rub: number;
}

export interface Hypothesis {
  id: string;
  statement_if: string;
  statement_then: string;
  statement_because: string;
  origin: Origin;
  evidence_path: Edge[];
  novelty: number;
  risk: number;
  value: number;
  rank_score: number | null;
  novelty_breakdown: MetricBreakdown | null;
  risk_breakdown: MetricBreakdown | null;
  value_breakdown: MetricBreakdown | null;
  rank_contributions: Record<string, number>;
  phrasing_flag: string | null;
  graveyard_check: GraveyardCheck;
  experiment_protocol: ExperimentProtocol;
  sources: string[];
}

// --- /graph/path/{id} (формат Cytoscape) ---

export interface CyNode {
  data: { id: string; label: string; type: string };
}

export interface CyEdgeData {
  id: string;
  source: string;
  target: string;
  sign: Sign;
  year: number | null;
  quote: string | null;
  doc_id: string | null;
}

export interface CyEdge {
  data: CyEdgeData;
}

export interface GraphPath {
  hypothesis_id: string;
  elements: { nodes: CyNode[]; edges: CyEdge[] };
}

// --- GET /graph (полный граф, Connected-Papers-вид) ---

export interface FullCyNodeData {
  id: string;
  label: string;
  type: string;
  degree: number;
  closure_reason: string | null;
}

export interface FullGraph {
  snapshot_id: string | null;
  elements: { nodes: { data: FullCyNodeData }[]; edges: CyEdge[] };
}

// --- чат / агент ---

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

export interface ChatResponse {
  answer: string;
  sources: string[];
  trace_id: string;
}

export interface AgentStep {
  thought: string;
  tool: string;
  query: string;
  source_doc_id: string | null;
  evidence_quote: string | null;
}

export interface AgentTrace {
  id: string;
  mission: string;
  steps: AgentStep[];
  created_at: string;
}

export interface ResearchResponse {
  snapshot_id: string;
  triplet_count: number;
  trace_id: string | null;
}

// --- служебное ---

export interface Health {
  status: string;
  graph_built: boolean;
  adapter_modes: Record<string, string>;
}

export type Weights = Record<string, number>;
