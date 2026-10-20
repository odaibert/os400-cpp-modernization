import type { Assessment, ConversionFile, ConversionJob, ConversionPreview, DocumentKind, DocumentPreview, Excerpt, Graph, Job, Profile, Repo } from './contracts';

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === 'string';
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(text);
const number = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
const profile = (value: unknown): value is Profile => record(value) &&
  ['c++17', 'c++20'].includes(String(value.standard)) && strings(value.defines) && strings(value.include_paths) &&
  number(value.max_files) && number(value.max_file_bytes) && number(value.max_total_bytes);
const conversionFile = (value: unknown): value is ConversionFile => record(value) &&
  text(value.path) && ['ready', 'unchanged', 'blocked'].includes(String(value.status)) && number(value.changes) &&
  Array.isArray(value.diagnostics) && value.diagnostics.every(item => record(item) &&
    text(item.code) && text(item.message) && (item.path === null || text(item.path)));

function validConversionJob(value: unknown, repo: string): value is ConversionJob {
  if (!record(value) || !text(value.id) || !value.id || value.repo_id !== repo || value.kind !== 'conversion' ||
    !['queued', 'running', 'succeeded', 'blocked', 'failed', 'cancelled', 'interrupted'].includes(String(value.status)) ||
    !number(value.completed_files) || !number(value.total_files) || value.completed_files > value.total_files ||
    !text(value.stage) || (value.error !== null && !(record(value.error) && text(value.error.code) && text(value.error.message)))) return false;
  const result = value.conversion;
  if (result === null) return !['succeeded', 'blocked'].includes(String(value.status));
  return record(result) && result.target === 'linux-x86_64-c++20' && result.requires_review === true &&
    text(result.generation_id) && !!result.generation_id && text(result.graph_digest) && !!result.graph_digest &&
    profile(result.profile) &&
    ['passed', 'blocked'].includes(String(result.validation_status)) && text(result.validation) &&
    Array.isArray(result.files) && result.files.length > 0 && result.files.every(conversionFile) &&
    (value.status !== 'succeeded' || (result.validation_status === 'passed' &&
      result.files.every(item => ['ready', 'unchanged'].includes(item.status))));
}

function validConversionPreview(value: unknown, path: string): value is ConversionPreview {
  return conversionFile(value) && value.path === path && record(value) && text(value.before) &&
    value.requires_review === true && (value.after === null || text(value.after)) &&
    (value.status === 'blocked' || text(value.after)) &&
    (value.status !== 'unchanged' || value.before === value.after);
}

function validGraph(value: unknown, repo: string): value is Graph {
  if (!record(value) || value.schema_version !== 1 || value.repo_id !== repo ||
    !text(value.generation_id) || !value.generation_id || !profile(value.profile) ||
    !['complete', 'partial'].includes(String(value.status))) return false;
  return Array.isArray(value.nodes) && value.nodes.every(node => record(node) &&
    text(node.id) && text(node.name) &&
    ['file', 'function', 'record', 'field', 'variable', 'namespace', 'external'].includes(String(node.kind)) &&
    strings(node.evidence_ids) && record(node.properties)) &&
    Array.isArray(value.edges) && value.edges.every(edge => record(edge) && text(edge.id) &&
      text(edge.source) && text(edge.target) && strings(edge.evidence_ids) &&
      ['DECLARES', 'CONTAINS', 'CALLS', 'REFERENCES'].includes(String(edge.kind))) &&
    Array.isArray(value.sources) && value.sources.every(source => record(source) && text(source.id) &&
      text(source.path) && text(source.sha256) && number(source.size)) &&
    Array.isArray(value.evidence) && value.evidence.every(evidence => record(evidence) &&
      text(evidence.id) && text(evidence.source_id) && number(evidence.start_byte) &&
      number(evidence.end_byte) && number(evidence.line_start) && number(evidence.line_end)) &&
    Array.isArray(value.diagnostics) && value.diagnostics.every(item => record(item) &&
      text(item.code) && text(item.message) && (item.path === null || text(item.path)));
}

export class ApiError extends Error {
  constructor(public code: string, message: string, public status = 0) {
    super(message);
    this.name = 'ApiError';
  }
}

export const describeError = (error: unknown): string =>
  error instanceof ApiError ? `${error.code}: ${error.message}` :
    error instanceof Error ? error.message : 'Request failed. Check the local API and try again.';

export class WorkbenchApi {
  private csrf = '';

  async session(signal: AbortSignal): Promise<void> {
    const data = await this.request<{ csrf_token: string }>('/session', { signal });
    if (!data.csrf_token) throw new ApiError('invalid_response', 'The API did not establish a session.');
    this.csrf = data.csrf_token;
  }

  private async response(path: string, init: RequestInit = {}): Promise<Response> {
    const method = init.method ?? 'GET';
    const headers = new Headers(init.headers);
    if (method !== 'GET') {
      if (!this.csrf) throw new ApiError('session_required', 'Reconnect to the local API before making changes.');
      headers.set('X-CSRF-Token', this.csrf);
      if (init.body) headers.set('Content-Type', 'application/json');
    }
    let response: Response;
    try {
      response = await fetch(`/api${path}`, { ...init, headers, credentials: 'same-origin' });
    } catch (error) {
      if (init.signal?.aborted) throw error;
      throw new ApiError('network_error', 'Cannot reach the local API. Start the workbench service and reconnect.');
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(body?.error?.code ?? `http_${response.status}`,
        body?.error?.message ?? `The local API returned HTTP ${response.status}.`, response.status);
    }
    return response;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.response(path, init);
    try {
      return await response.json() as T;
    } catch {
      throw new ApiError('invalid_response', 'The local API returned an invalid JSON response.');
    }
  }

  repos(signal: AbortSignal) { return this.request<{ repos: Repo[] }>('/repos', { signal }); }
  async health(signal: AbortSignal): Promise<void> {
    const result = await this.request<unknown>('/health', { signal });
    if (!record(result) || result.status !== 'ready' || result.neo4j !== 'connected') {
      throw new ApiError('invalid_health', 'Neo4j did not confirm a live database connection.');
    }
  }
  async sqliteHealth(signal: AbortSignal): Promise<void> {
    const result = await this.request<unknown>('/health/sqlite', { signal });
    if (!record(result) || result.status !== 'ready' || result.sqlite !== 'connected') {
      throw new ApiError('invalid_health', 'SQLite did not confirm a live conversion-history connection.');
    }
  }
  async startConversion(repo: string, paths: string[], profile: Profile, signal: AbortSignal): Promise<ConversionJob> {
    const result = await this.request<unknown>(`/repos/${encodeURIComponent(repo)}/conversions`, {
      method: 'POST', body: JSON.stringify({ paths, profile, confirmed_big_endian_layout: true, target: 'linux-x86_64-c++20' }), signal,
    });
    if (!validConversionJob(result, repo)) throw new ApiError('invalid_conversion', 'The API returned a mismatched conversion job.');
    return result;
  }
  async conversionJob(id: string, repo: string, signal: AbortSignal): Promise<ConversionJob> {
    const result = await this.request<unknown>(`/jobs/${encodeURIComponent(id)}`, { signal });
    if (!validConversionJob(result, repo) || result.id !== id) {
      throw new ApiError('invalid_conversion', 'The API returned a mismatched conversion job.');
    }
    return result;
  }
  async conversionHistory(repo: string, signal: AbortSignal): Promise<ConversionJob[]> {
    const result = await this.request<unknown>(`/repos/${encodeURIComponent(repo)}/conversions`, { signal });
    if (!record(result) || !Array.isArray(result.jobs) || result.jobs.length > 100 ||
      !result.jobs.every(value => validConversionJob(value, repo))) {
      throw new ApiError('invalid_conversion', 'The API returned invalid conversion history.');
    }
    return result.jobs;
  }
  async conversionPreview(id: string, path: string, signal: AbortSignal): Promise<ConversionPreview> {
    const result = await this.request<unknown>(`/conversions/${encodeURIComponent(id)}/preview?path=${encodeURIComponent(path)}`, { signal });
    if (!validConversionPreview(result, path)) {
      throw new ApiError('invalid_conversion', 'The API returned an invalid source comparison.');
    }
    return result;
  }
  assess(repo: string, profile: Profile, signal: AbortSignal) {
    return this.request<Assessment>(`/repos/${encodeURIComponent(repo)}/assessment`,
      { method: 'POST', body: JSON.stringify(profile), signal });
  }
  generate(repo: string, profile: Profile, signal: AbortSignal) {
    return this.request<Job>(`/repos/${encodeURIComponent(repo)}/generations`,
      { method: 'POST', body: JSON.stringify(profile), signal });
  }
  job(id: string, signal: AbortSignal) { return this.request<Job>(`/jobs/${encodeURIComponent(id)}`, { signal }); }
  cancel(id: string, signal: AbortSignal) {
    return this.request<Job>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST', signal });
  }
  async graph(repo: string, signal: AbortSignal): Promise<Graph> {
    const graph = await this.request<unknown>(`/repos/${encodeURIComponent(repo)}/graph`, { signal });
    if (!validGraph(graph, repo)) {
      throw new ApiError('invalid_graph', 'The API returned an unsupported or mismatched graph.');
    }
    return graph;
  }
  excerpt(repo: string, id: string, signal: AbortSignal) {
    return this.request<Excerpt>(`/repos/${encodeURIComponent(repo)}/evidence/${encodeURIComponent(id)}`, { signal });
  }
  preview(repo: string, kind: DocumentKind, signal: AbortSignal) {
    return this.request<DocumentPreview>(`/repos/${encodeURIComponent(repo)}/exports`,
      { method: 'POST', body: JSON.stringify({ kind }), signal });
  }
  async download(repo: string, kind: DocumentKind, signal: AbortSignal): Promise<Blob> {
    return this.zip(`/repos/${encodeURIComponent(repo)}/export?kind=${kind}`, signal);
  }
  downloadConversion(id: string, signal: AbortSignal): Promise<Blob> {
    return this.zip(`/conversions/${encodeURIComponent(id)}/download`, signal);
  }
  private async zip(path: string, signal: AbortSignal): Promise<Blob> {
    const response = await this.response(path, { signal });
    if (!response.headers.get('Content-Type')?.includes('application/zip')) {
      throw new ApiError('invalid_download', 'The API did not return a ZIP archive.');
    }
    return response.blob();
  }
}
