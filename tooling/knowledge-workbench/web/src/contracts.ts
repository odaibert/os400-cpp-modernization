export interface Profile {
  standard: 'c++17' | 'c++20';
  defines: string[];
  include_paths: string[];
  max_files: number;
  max_file_bytes: number;
  max_total_bytes: number;
}

export interface Diagnostic { code: string; message: string; path: string | null }
export interface Source { id: string; path: string; sha256: string; size: number }
export type NodeKind = 'file' | 'function' | 'record' | 'field' | 'variable' | 'namespace' | 'external';
export type EdgeKind = 'DECLARES' | 'CONTAINS' | 'CALLS' | 'REFERENCES';
export interface GraphNode {
  id: string;
  kind: NodeKind;
  name: string;
  evidence_ids: string[];
  properties: Record<string, unknown>;
}
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  evidence_ids: string[];
}
export interface Evidence {
  id: string;
  source_id: string;
  start_byte: number;
  end_byte: number;
  line_start: number;
  line_end: number;
}
export interface Graph {
  schema_version: 1;
  repo_id: string;
  generation_id: string;
  profile: Profile;
  sources: Source[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  evidence: Evidence[];
  diagnostics: Diagnostic[];
  status: 'complete' | 'partial';
}
export interface Repo { id: string; name: string; status: string }
export interface Assessment {
  sources: { path: string; size: number }[];
  profile: Profile;
  diagnostics: Diagnostic[];
}
export interface Job {
  id: string;
  repo_id: string;
  status: string;
  stage?: string;
  error?: { code: string; message: string };
}
export interface ConversionFile {
  path: string;
  status: 'ready' | 'unchanged' | 'blocked';
  changes: number;
  diagnostics: Diagnostic[];
}
export interface ConversionSummary {
  target: 'linux-x86_64-c++20';
  requires_review: true;
  validation_status: 'passed' | 'blocked';
  validation: string;
  files: ConversionFile[];
  generation_id: string;
  graph_digest: string;
  profile: Profile;
}
export interface ConversionJob extends Job {
  kind: 'conversion';
  completed_files: number;
  total_files: number;
  conversion: ConversionSummary | null;
  created_at?: number;
  updated_at?: number;
}
export interface ConversionPreview extends ConversionFile {
  before: string;
  after: string | null;
  requires_review: true;
}
export interface Excerpt { id: string; path: string; line_start: number; line_end: number; text: string }
export type DocumentKind = 'as-built' | 'spec-draft';
export interface DocumentPreview {
  id: string;
  kind: DocumentKind;
  files: { name: string; content: string }[];
  generation_id: string;
}

export const defaultProfile: Profile = {
  standard: 'c++20', defines: [], include_paths: [],
  max_files: 200, max_file_bytes: 1_000_000, max_total_bytes: 10_000_000,
};
