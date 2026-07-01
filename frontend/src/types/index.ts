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

export interface QueryResult {
  anchor_nodes: string[];
  traversal_path: string[];
  nodes: GraphNode[];
  links: GraphLink[];
  summary: string;
  citations: Citation[];
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

export interface IngestionEvent {
  stage: string;
  message: string;
  pct: number;
  doc_id?: string;
  file?: string;
  file_index?: number;
}
