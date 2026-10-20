import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, describeError, WorkbenchApi } from './api';
import { defaultProfile } from './contracts';
import type { Assessment, Diagnostic, DocumentKind, DocumentPreview, Excerpt, Graph, GraphNode, Job, Profile, Repo } from './contracts';
import { GraphExplorer } from './GraphExplorer';
import { DatabaseStatus } from './DatabaseStatus';
import { ConversionWorkspace } from './ConversionWorkspace';

const isTerminal = (status: string) => ['completed', 'succeeded', 'complete', 'partial', 'failed', 'cancelled', 'canceled'].includes(status);
const isSuccess = (status: string) => ['completed', 'succeeded', 'complete', 'partial'].includes(status);
const isMissing = (error: unknown) => error instanceof ApiError && ['not_found', 'no_generation'].includes(error.code);
const isFreshnessError = (error: unknown) => error instanceof ApiError &&
  /stale|changed|deleted|added|generation|source_missing|missing_source/.test(error.code);

function currentRoute() {
  const [path, query] = window.location.hash.slice(1).split('?', 2);
  const parameters = new URLSearchParams(query);
  return { page: path === '/conversion' ? 'conversion' : 'graph',
    repo: parameters.get('repo') ?? '', job: parameters.get('job') ?? '' };
}

function conversionLink(repo: string, job: string) {
  return repo && job ? `#/conversion?${new URLSearchParams({ repo, job })}` : '#/conversion';
}

function Diagnostics({ items }: { items: Diagnostic[] }) {
  return <details className="diagnostics" open={items.length > 0}>
    <summary>Completeness diagnostics ({items.length})</summary>
    {items.length === 0 ? <p>No diagnostics reported. Completeness applies only to the selected profile and scanned scope.</p> :
      <ul>{items.map((item, i) => <li key={`${item.code}-${i}`}><strong className="mono">{item.code}</strong>
        {item.path && <span className="mono"> · {item.path}</span>}<p>{item.message}</p></li>)}</ul>}
  </details>;
}

function pause(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 1000);
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, { once: true });
  });
}

export default function App({ api: suppliedApi }: { api?: WorkbenchApi }) {
  const api = useMemo(() => suppliedApi ?? new WorkbenchApi(), [suppliedApi]);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [repoId, setRepoId] = useState('');
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [connection, setConnection] = useState(0);
  const [route, setRoute] = useState(currentRoute);
  const page = route.page;
  const [conversionJobs, setConversionJobs] = useState<Record<string, string>>({});
  useEffect(() => {
    const navigate = () => setRoute(currentRoute());
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  useEffect(() => {
    if (status === 'ready' && route.page === 'conversion' && route.job &&
        repos.some(repo => repo.id === route.repo)) {
      setRepoId(route.repo);
      setConversionJobs(previous => ({ ...previous, [route.repo]: route.job }));
    }
  }, [route, repos, status]);
  useEffect(() => {
    const controller = new AbortController();
    setStatus('loading'); setError(''); setRepoId('');
    void (async () => {
      try {
        await api.session(controller.signal);
        const result = await api.repos(controller.signal);
        if (!Array.isArray(result.repos)) throw new ApiError('invalid_response', 'The API returned an invalid repository list.');
        if (!controller.signal.aborted) { setRepos(result.repos); setStatus('ready'); }
      } catch (cause) {
        if (!controller.signal.aborted) { setError(describeError(cause)); setStatus('error'); }
      }
    })();
    return () => controller.abort();
  }, [api, connection]);
  return <div className="app">
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <header className="app-header"><div className="wordmark" aria-hidden="true">{'{ }'}</div><div>
      <p className="eyebrow">Local repository instrument</p><h1>C++ Knowledge Workbench</h1>
    </div><div className="database-statuses">
      <DatabaseStatus api={api} session={status} database="Neo4j" />
      <DatabaseStatus api={api} session={status} database="SQLite" />
    </div></header>
    <nav className="page-navigation" aria-label="Workbench pages">
      <a href="#/graph" aria-current={page === 'graph' ? 'page' : undefined}>Knowledge graph</a>
      <a href={conversionLink(repoId, conversionJobs[repoId] ?? '')}
        aria-current={page === 'conversion' ? 'page' : undefined}>Code conversion</a>
    </nav>
    <div className="repository-bar">
      <label>Registered repository
        <select value={repoId} disabled={status !== 'ready'} onChange={e => {
          const next = e.target.value;
          setRepoId(next);
          if (page === 'conversion') window.location.hash = conversionLink(next, conversionJobs[next] ?? '');
        }}>
          <option value="">Select a registered repository</option>
          {repos.map(repo => <option key={repo.id} value={repo.id}>{repo.name} · {repo.status}</option>)}
        </select>
      </label>
      <button className="primary" onClick={() => {
        window.location.hash = conversionLink(repoId, conversionJobs[repoId] ?? '');
      }} disabled={status !== 'ready' || repos.length === 0}>Convert code</button>
      <button onClick={() => setConnection(value => value + 1)} disabled={status === 'loading'}>Reconnect / refresh repositories</button>
      <span className="caption">No cloud models · no automatic exports</span>
    </div>
    <main id="workspace" tabIndex={-1}>
      {status === 'loading' && <p role="status" className="notice">Connecting to the local API and establishing a session…</p>}
      {error && <div role="alert" className="notice error"><strong>Connection unavailable</strong><p>{error}</p>
        <p>Verify the local API serving this page, then reconnect. Authentication failures are not bypassed.</p></div>}
      {status === 'ready' && !repoId && <section className="welcome panel">
        <p className="eyebrow">Source → structure → evidence</p>
        <h2>{repos.length ? (page === 'conversion' ? 'Choose the repository to convert.' : 'Choose the repository to inspect.') : 'Register a local repository first.'}</h2>
        <p>This workbench records structural facts for an explicit C++ profile. It does not recover requirements or certify IBM i compatibility.</p>
        {repos.length > 0 && <p>{page === 'conversion'
          ? 'Select a repository above to choose inputs and prepare a conversion draft.'
          : 'Select a repository to assess sources and explicitly generate a graph, or choose Convert code above. Graphs are not loaded or generated automatically.'}</p>}
        {!repos.length && <><p>Register a trusted local root using the CLI, then refresh repositories:</p>
          <pre>knowledge-workbench register /absolute/path/to/repository --name my-repository</pre>
          <p className="caption">The browser accepts registered IDs only, never filesystem paths.</p></>}
      </section>}
      {status === 'ready' && repoId && (page === 'graph'
        ? <RepositoryWorkspace key={`${connection}:${repoId}`} api={api} repo={repos.find(repo => repo.id === repoId)!} />
        : <ConversionWorkspace key={`${connection}:${repoId}`} api={api} repo={repos.find(repo => repo.id === repoId)!}
          jobId={conversionJobs[repoId] ?? ''} onJob={id => {
            setConversionJobs(previous => ({ ...previous, [repoId]: id }));
            window.location.hash = conversionLink(repoId, id);
          }} />)}
    </main>
    <footer>Original source remains authoritative. Excerpts and exports are reverified against current files.</footer>
  </div>;
}

function RepositoryWorkspace({ api, repo }: { api: WorkbenchApi; repo: Repo }) {
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [profile, setProfile] = useState<Profile>(defaultProfile);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [excerpt, setExcerpt] = useState<Excerpt | null>(null);
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [kind, setKind] = useState<DocumentKind>('as-built');
  const [busy, setBusy] = useState('');
  const [evidenceBusy, setEvidenceBusy] = useState(false);
  const [error, setError] = useState('');
  const [graphMessage, setGraphMessage] = useState('No graph loaded. Assess sources and choose Generate graph, or choose Load current graph to inspect an existing generation.');
  const [downloadMessage, setDownloadMessage] = useState('');
  const [cancelBusy, setCancelBusy] = useState(false);
  const mounted = useRef(true);
  const controllers = useRef(new Set<AbortController>());
  const graphRequest = useRef<AbortController | null>(null);
  const evidenceRequest = useRef<AbortController | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const request = useCallback(() => {
    const controller = new AbortController();
    controllers.current.add(controller);
    return controller;
  }, []);
  const finish = (controller: AbortController) => controllers.current.delete(controller);
  const clearEvidence = () => {
    evidenceRequest.current?.abort(); setExcerpt(null); setEvidenceBusy(false);
    setSelected(null); setPreview(null); setDownloadMessage('');
  };
  const dropGraph = (message: string) => {
    graphRef.current = null; setGraph(null); clearEvidence(); setGraphMessage(message);
  };
  const report = (cause: unknown) => {
    if (isFreshnessError(cause) || isMissing(cause)) dropGraph('This generation is no longer current. Assess sources and generate again.');
    setError(describeError(cause));
  };
  const acceptGraph = (value: Graph) => {
    clearEvidence(); graphRef.current = value; setGraph(value); setGraphMessage('');
  };
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controllers.current.forEach(controller => controller.abort());
      controllers.current.clear();
    };
    // The parent keys this workspace by repository and session connection.
  }, [api, repo.id]);

  const assess = async () => {
    const controller = request(); setBusy('Assessing sources'); setError('');
    try {
      const value = await api.assess(repo.id, profile, controller.signal);
      if (!controller.signal.aborted) { setAssessment(value); setProfile(value.profile); }
    } catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally { finish(controller); if (mounted.current) setBusy(''); }
  };
  const generate = async () => {
    graphRequest.current?.abort();
    const controller = request();
    setBusy('Generating graph'); setError(''); setJob(null);
    dropGraph('Generation in progress. Previous graph is not displayed.');
    try {
      let next = await api.generate(repo.id, profile, controller.signal);
      while (!controller.signal.aborted) {
        if (!next.id || (next.repo_id && next.repo_id !== repo.id)) throw new ApiError('job_mismatch', 'The API returned a job for a different repository.');
        setJob(next);
        if (isTerminal(next.status)) {
          if (isSuccess(next.status)) {
            const value = await api.graph(repo.id, controller.signal);
            if (!controller.signal.aborted) acceptGraph(value);
          } else {
            setGraphMessage(next.status === 'failed' ? 'Generation failed. Review the job error and assess before retrying.' : 'Generation cancelled. No new graph is displayed.');
            if (next.error) setError(`${next.error.code}: ${next.error.message}`);
          }
          break;
        }
        if (!['queued', 'running', 'pending', 'cancelling', 'cancel_requested'].includes(next.status)) {
          throw new ApiError('unknown_job_status', `Unsupported job status: ${next.status}. No completion is assumed.`);
        }
        await pause(controller.signal);
        next = await api.job(next.id, controller.signal);
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        setGraphMessage('Generation outcome unavailable. The server job may still be running; cancel the owned job or reload its published graph.');
        report(cause);
      }
    }
    finally { finish(controller); if (mounted.current) setBusy(''); }
  };
  const cancel = async () => {
    if (!job) return;
    const controller = request(); setCancelBusy(true); setError('');
    try {
      const next = await api.cancel(job.id, controller.signal);
      if (!controller.signal.aborted) {
        if (next.id !== job.id || (next.repo_id && next.repo_id !== repo.id)) throw new ApiError('job_mismatch', 'Cancellation response does not match the owned job.');
        setJob(next);
        if (next.status === 'cancelled') setGraphMessage('Generation cancelled. No new graph is displayed.');
      }
    } catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally { finish(controller); if (mounted.current) setCancelBusy(false); }
  };
  const assertCurrent = async (generation: string, signal: AbortSignal) => {
    const current = await api.graph(repo.id, signal);
    if (current.generation_id !== generation || graphRef.current?.generation_id !== generation) {
      throw new ApiError('generation_changed', 'The generation changed during this request. Reload the current graph.');
    }
  };
  const selectEvidence = async (id: string) => {
    evidenceRequest.current?.abort();
    if (!graphRef.current) return;
    const generation = graphRef.current.generation_id;
    const controller = request(); evidenceRequest.current = controller;
    setExcerpt(null); setEvidenceBusy(true); setError('');
    try {
      const value = await api.excerpt(repo.id, id, controller.signal);
      if (controller.signal.aborted) return;
      await assertCurrent(generation, controller.signal);
      if (!controller.signal.aborted && evidenceRequest.current === controller) {
        if (value.id !== id) throw new ApiError('evidence_mismatch', 'The API returned a different evidence record.');
        setExcerpt(value);
      }
    } catch (cause) { if (!controller.signal.aborted && evidenceRequest.current === controller) report(cause); }
    finally {
      finish(controller);
      if (mounted.current && evidenceRequest.current === controller) setEvidenceBusy(false);
    }
  };
  const documents = async (download: boolean) => {
    if (!graphRef.current) return;
    const generation = graphRef.current.generation_id;
    const controller = request(); setBusy(download ? 'Preparing ZIP' : 'Preparing preview');
    setError(''); setPreview(null); setDownloadMessage('');
    try {
      if (download) {
        const blob = await api.download(repo.id, kind, controller.signal);
        if (controller.signal.aborted) return;
        await assertCurrent(generation, controller.signal);
        if (!controller.signal.aborted) {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url; anchor.download = `knowledge-workbench-${kind}.zip`;
          document.body.append(anchor); anchor.click(); anchor.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
          setDownloadMessage('Verified ZIP prepared. Check your browser downloads.');
        }
      } else {
        const value = await api.preview(repo.id, kind, controller.signal);
        if (!controller.signal.aborted) {
          if (value.generation_id !== generation || value.kind !== kind) throw new ApiError('generation_changed', 'Preview does not match this generation and document kind.');
          setPreview(value);
        }
      }
    } catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally { finish(controller); if (mounted.current) setBusy(''); }
  };
  const reloadGraph = async () => {
    graphRequest.current?.abort();
    const controller = request(); setBusy('Loading graph'); setError('');
    graphRequest.current = controller;
    dropGraph('Loading current generation…');
    try {
      const value = await api.graph(repo.id, controller.signal);
      if (!controller.signal.aborted) acceptGraph(value);
    } catch (cause) {
      if (!controller.signal.aborted) {
        if (isMissing(cause)) setGraphMessage('No current generation. Assess and generate first.');
        else report(cause);
      }
    } finally { finish(controller); if (mounted.current) setBusy(''); }
  };
  const selectedEvidence = useMemo(() => {
    if (!graph || !selected) return [];
    const ids = new Set(selected.evidence_ids);
    for (const edge of graph.edges) if (edge.source === selected.id || edge.target === selected.id) {
      edge.evidence_ids.forEach(id => ids.add(id));
    }
    const sourceMap = new Map(graph.sources.map(source => [source.id, source.path]));
    return graph.evidence.filter(evidence => ids.has(evidence.id))
      .map(evidence => ({ ...evidence, path: sourceMap.get(evidence.source_id) ?? 'Unknown source' }));
  }, [graph, selected]);
  const selectedRelations = useMemo(() => {
    if (!graph || !selected) return { rows: [], total: 0 };
    const names = new Map(graph.nodes.map(node => [node.id, node.name]));
    const related = graph.edges.filter(edge => edge.source === selected.id || edge.target === selected.id);
    return {
      total: related.length,
      rows: related.slice(0, 100).map(edge => ({
        ...edge, sourceName: names.get(edge.source) ?? edge.source, targetName: names.get(edge.target) ?? edge.target,
      })),
    };
  }, [graph, selected]);

  return <div className="workspace">
    <section className="panel controls" aria-labelledby="scope-title">
      <div className="panel-heading"><h2 id="scope-title">Scope & extraction</h2><span className="mono">{repo.name}</span></div>
      <div className="control-row">
        <button onClick={() => void assess()} disabled={!!busy}>Assess repository</button>
        <label>C++ standard<select value={profile.standard} disabled={!!busy}
          onChange={e => setProfile({ ...profile, standard: e.target.value as Profile['standard'] })}>
          <option value="c++17">C++17</option><option value="c++20">C++20</option>
        </select></label>
        <button className="primary" onClick={() => void generate()} disabled={!!busy || !assessment}>Generate graph</button>
        <button onClick={() => void reloadGraph()} disabled={!!busy}>Load current graph</button>
      </div>
      <p className="caption">C++ sources and headers only. Markdown and build documents are excluded from inputs; generated documentation is still available.</p>
      <p className="caption">Graphs are never loaded or generated on page load or repository selection. Assess first, then choose Generate graph, or explicitly load an existing graph. No build scripts are executed. Changing repositories stops observation, not an already submitted server job.</p>
      <p className="mono profile-summary">Limits: {profile.max_files} files · {profile.max_file_bytes.toLocaleString()} bytes/file · {profile.max_total_bytes.toLocaleString()} bytes total</p>
      <p className="caption">Defines: {profile.defines.join(', ') || 'none'} · Include roots: {profile.include_paths.join(', ') || 'none'}</p>
      {assessment && <><details><summary>Assessed sources ({assessment.sources.length})</summary><ul className="source-list">
        {assessment.sources.map(source => <li key={source.path}><code>{source.path}</code><span>{source.size.toLocaleString()} bytes</span></li>)}
      </ul></details><Diagnostics items={assessment.diagnostics} /></>}
      {busy && <p role="status" className="working">{busy}…</p>}
      {job && <div className="job" role="status"><div><strong>Job: {job.status}</strong>
        <span className="mono identifier">{job.id}</span><span>{job.stage || 'No stage reported'}</span></div>
        {!isTerminal(job.status) && <button onClick={() => void cancel()} disabled={cancelBusy}>{cancelBusy ? 'Requesting cancellation…' : 'Cancel generation'}</button>}
        {job.status === 'failed' && !job.error && <p>Generation failed; the API did not provide further detail.</p>}
      </div>}
    </section>
    {error && <div role="alert" className="notice error"><strong>Request could not complete</strong><p>{error}</p>
      <p className="caption">No replacement data was fabricated. For session or CSRF errors, reconnect using the repository bar.</p></div>}
    {!graph && <p className="notice" role="status">{graphMessage || 'No verified graph available. Reload or generate again.'}</p>}
    {graph && <>
      <section className="generation panel">
        <div className="panel-heading"><h2>Current generation</h2><strong className={`badge ${graph.status}`}>{graph.status}</strong></div>
        <p className="mono identifier">{graph.generation_id}</p>
        <p>{graph.profile.standard.toUpperCase()} · {graph.sources.length} sources · {graph.nodes.length} nodes · {graph.edges.length} relations</p>
        {graph.status === 'partial' && <p className="warning">Partial extraction: missing relations are not evidence of absence. Review diagnostics before using these facts.</p>}
        <Diagnostics items={graph.diagnostics} />
      </section>
      <div className="exploration">
        <GraphExplorer key={graph.generation_id} graph={graph} selected={selected} onSelect={node => {
          evidenceRequest.current?.abort(); setSelected(node); setExcerpt(null); setEvidenceBusy(false);
        }} />
        <aside className="panel evidence-panel" aria-labelledby="evidence-title">
          <div className="panel-heading"><h2 id="evidence-title">Source evidence</h2><span className="caption">READ-ONLY</span></div>
          {!selected ? <p className="empty">Select a symbol in the index or table to inspect its citations and connected relation evidence.</p> : <>
            <h3 className="mono">{selected.name}</h3><p className="mono identifier">{selected.id}</p>
            <details className="relations"><summary>Recorded relations ({selectedRelations.total})</summary>
              {selectedRelations.rows.length === 0 ? <p>No relations recorded for this symbol.</p> :
                <ul>{selectedRelations.rows.map(edge => <li key={edge.id}>
                  <code>{edge.sourceName}</code><strong>{edge.kind} →</strong><code>{edge.targetName}</code>
                  <small className="mono identifier">{edge.id}</small>
                </li>)}</ul>}
              {selectedRelations.total > 100 && <p className="warning">First 100 connected relations shown.</p>}
            </details>
            {selectedEvidence.length === 0 && <p>No evidence is recorded for this symbol or its relations. Do not treat it as a cited fact.</p>}
            <ul className="evidence-list">{selectedEvidence.slice(0, 200).map(evidence => <li key={evidence.id}>
              <button className="text-button" onClick={() => void selectEvidence(evidence.id)} aria-pressed={excerpt?.id === evidence.id}>
                {evidence.path}:{evidence.line_start}–{evidence.line_end}
              </button></li>)}</ul>
            {selectedEvidence.length > 200 && <p className="warning">Showing the first 200 citations. Narrow the symbol selection.</p>}
          </>}
          {evidenceBusy && <p role="status">Verifying original source…</p>}
          {excerpt && <div className="excerpt"><p className="caption">Freshly verified · <code>{excerpt.path}:{excerpt.line_start}–{excerpt.line_end}</code></p>
            <pre tabIndex={0} aria-label="Verified source excerpt"><code>{excerpt.text}</code></pre></div>}
        </aside>
      </div>
      <section className="panel documents" aria-labelledby="documents-title">
        <div className="panel-heading"><h2 id="documents-title">Cited documents</h2><span className="caption">EXPLICIT EXPORT ONLY</span></div>
        <p>As-built documents describe recorded facts. Spec Kit-style drafts are proposals for human review, not recovered requirements, official Spec Kit certification, or pinned-template compatibility. No Spec Kit tools are installed or executed.</p>
        <div className="control-row"><label>Document kind<select value={kind} disabled={!!busy}
          onChange={e => { setKind(e.target.value as DocumentKind); setPreview(null); setDownloadMessage(''); }}>
          <option value="as-built">As-built facts</option><option value="spec-draft">Spec Kit-style drafts — review needed</option>
        </select></label><button onClick={() => void documents(false)} disabled={!!busy}>Preview documents</button>
          <button onClick={() => void documents(true)} disabled={!!busy}>Download verified ZIP</button></div>
        <p className="caption">ZIP files are verified and generated in memory. Downloaded copies are unmanaged: deleting a registered graph cannot recall them.</p>
        {downloadMessage && <p role="status">{downloadMessage}</p>}
        {preview && <div className="document-preview"><p className="caption">Generation <code>{preview.generation_id}</code> · Markdown shown as text</p>
          {preview.files.map(file => <details key={file.name} open><summary>{file.name}</summary>
            <pre tabIndex={0}><code>{file.content}</code></pre></details>)}</div>}
      </section>
    </>}
  </div>;
}
