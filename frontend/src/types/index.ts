export type NodeType =
  | 'pet'
  | 'owner'
  | 'provider'
  | 'visit'
  | 'symptom'
  | 'diagnosis'
  | 'medication'
  | 'vaccine';

export interface GraphNode {
  id: string;
  type: NodeType;
  name: string;
  properties: Record<string, unknown>;
  source_doc_ids: string[];
  // force-graph adds these at runtime
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
}

export interface GraphLink {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  relationship: string;
  properties: Record<string, unknown>;
  source_doc_id?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export type RelevanceLevel = 'strong' | 'moderate' | 'weak' | 'none' | 'unavailable';

export interface Relevance {
  level: RelevanceLevel;
  best_score: number | null;
  thresholds: { strong: number; weak: number };
  explanation: string;
}

export interface TraceOp {
  op: string;
  engine?: string;
  collection?: string;
  error?: string;
  results?: { snippet: string; score: number; document: string | null }[];
  cypher?: string;
  hop1_count?: number;
  hop2_count?: number;
  answer?: string | null;
}

export interface CogneeTrace {
  semantic_status: { state: string; docs_indexed: number; error: string | null };
  operations: TraceOp[];
  relevance?: Relevance;
  anchor_nodes?: string[];
}

export interface QueryResult {
  anchor_nodes: string[];
  traversal_path: string[];
  nodes: GraphNode[];
  links: GraphLink[];
  summary: string;
  citations: Citation[];
  suggestions: string[];
  relevance: Relevance;
  cognee_trace: CogneeTrace;
}

export interface Citation {
  entity: string;
  type: string;
  date?: string;
  source?: string;
}

export interface Conflict {
  conflict_key: string;
  type: 'medication_status' | 'vaccine_record_mismatch';
  severity: 'high' | 'medium' | 'low';
  description: string;
  suggested_question: string;
  involved_nodes: string[];
  medication?: string;
  vaccine?: string;
  pet?: string;
}

export interface Provider {
  id: string;
  name: string;
  properties: {
    clinic?: string;
    provider_type?: string;
  };
}

export interface Reminder {
  id: string;
  pet_id: string | null;
  pet_name: string | null;
  kind: 'vaccine_due' | 'follow_up' | 'medication_end';
  title: string;
  details?: string;
  due_date?: string;
  status: string;
}

export interface Insight {
  id: string;
  pet_id: string | null;
  pet_name: string | null;
  kind: string;
  title: string;
  body?: string;
  why?: string;
  source: 'pet_records' | 'general_guideline';
}

export interface CogneeStatus {
  state: 'empty' | 'indexing' | 'ready' | 'error';
  docs_indexed: number;
  error: string | null;
  domain_nodes: Record<string, number>;
  semantic_nodes: Record<string, number>;
}

export interface IngestionEvent {
  stage: string;
  message: string;
  pct: number;
  doc_id?: string;
  file?: string;
  file_index?: number;
}
