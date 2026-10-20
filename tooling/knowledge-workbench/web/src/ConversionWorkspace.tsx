import { useEffect, useRef, useState } from 'react';
import { ApiError, describeError, WorkbenchApi } from './api';
import { defaultProfile } from './contracts';
import type { Assessment, ConversionJob, ConversionPreview, Graph, Profile, Repo } from './contracts';

const terminal = (status: string) => ['succeeded', 'blocked', 'failed', 'cancelled', 'interrupted'].includes(status);
const stageNames: Record<string, string> = {
  loading_graph: 'Loading and verifying Neo4j generation',
  queued: 'Queued', extracting: 'Starting analysis', assessing: 'Assessing inputs',
  analysing: 'Analysing C++ declarations', rewriting: 'Planning record conversions',
  validating: 'Checking generated syntax and layouts', cancelling: 'Cancelling', finished: 'Finished',
};

function matchingProfiles(left: Profile, right: Profile) {
  return left.standard === right.standard && left.max_files === right.max_files &&
    left.max_file_bytes === right.max_file_bytes && left.max_total_bytes === right.max_total_bytes &&
    left.defines.length === right.defines.length && left.defines.every((item, index) => item === right.defines[index]) &&
    left.include_paths.length === right.include_paths.length &&
    left.include_paths.every((item, index) => item === right.include_paths[index]);
}

export function ConversionWorkspace({ api, repo, jobId, onJob }: {
  api: WorkbenchApi; repo: Repo; jobId: string; onJob: (id: string) => void;
}) {
  const [profile, setProfile] = useState<Profile>(defaultProfile);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [paths, setPaths] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [job, setJob] = useState<ConversionJob | null>(null);
  const [preview, setPreview] = useState<ConversionPreview | null>(null);
  const [file, setFile] = useState('');
  const [comparisonVersion, setComparisonVersion] = useState(0);
  const [comparisonBusy, setComparisonBusy] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [stale, setStale] = useState(false);
  const [staleMessage, setStaleMessage] = useState('');
  const [downloaded, setDownloaded] = useState(false);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [graphError, setGraphError] = useState('');
  const [graphVersion, setGraphVersion] = useState(0);
  const [history, setHistory] = useState<ConversionJob[]>([]);
  const [historyError, setHistoryError] = useState('');
  const [historyVersion, setHistoryVersion] = useState(0);
  const requests = useRef(new Set<AbortController>());
  const comparison = useRef<AbortController | null>(null);
  const request = () => { const controller = new AbortController(); requests.current.add(controller); return controller; };
  const finish = (controller: AbortController) => requests.current.delete(controller);
  const fail = (cause: unknown) => {
    setError(describeError(cause));
    if (cause instanceof ApiError && ['source_changed', 'stale_evidence', 'graph_changed', 'graph_required', 'conversion_outdated', 'not_found'].includes(cause.code)) {
      comparison.current?.abort();
      requests.current.forEach(controller => controller.abort());
      setBusy(''); setComparisonBusy(false); setStale(true); setPreview(null);
      setStaleMessage(cause.code === 'conversion_outdated' ? 'Safety checks changed — start a new conversion' :
        ['graph_changed', 'graph_required'].includes(cause.code) ? 'Graph changed — restart required' :
          cause.code === 'not_found' ? 'Context unavailable — restart required' : 'Source changed — restart required');
    }
  };
  useEffect(() => () => {
    requests.current.forEach(controller => controller.abort());
    requests.current.clear();
  }, []);
  useEffect(() => {
    if (graphVersion === 0) return;
    const controller = new AbortController();
    setGraph(null); setGraphError('');
    void api.graph(repo.id, controller.signal).then(value => {
      if (!controller.signal.aborted) setGraph(value);
    }).catch(cause => { if (!controller.signal.aborted) setGraphError(describeError(cause)); });
    return () => controller.abort();
  }, [api, repo.id, graphVersion]);
  const jobStatus = job?.status;
  useEffect(() => {
    const controller = new AbortController();
    setHistoryError('');
    void api.conversionHistory(repo.id, controller.signal).then(value => {
      if (!controller.signal.aborted) setHistory(value);
    }).catch(cause => { if (!controller.signal.aborted) setHistoryError(describeError(cause)); });
    return () => controller.abort();
  }, [api, repo.id, historyVersion, jobId, jobStatus]);
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    comparison.current?.abort();
    setJob(null); setFile(''); setPreview(null); setError(''); setStale(false); setDownloaded(false);
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const current = await api.conversionJob(jobId, repo.id, controller.signal);
        if (controller.signal.aborted) return;
        setJob(current);
        if (current.error) setError(`${current.error.code}: ${current.error.message}`);
        if (!terminal(current.status)) timer = setTimeout(() => void poll(), 800);
      } catch (cause) { if (!controller.signal.aborted) fail(cause); }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [api, repo.id, jobId]);
  useEffect(() => {
    if (!jobId || !file) { setComparisonBusy(false); return; }
    comparison.current?.abort();
    const controller = new AbortController();
    comparison.current = controller;
    setPreview(null); setError(''); setComparisonBusy(true);
    void api.conversionPreview(jobId, file, controller.signal).then(value => {
      if (!controller.signal.aborted) setPreview(value);
    }).catch(cause => { if (!controller.signal.aborted) fail(cause); })
      .finally(() => { if (!controller.signal.aborted) setComparisonBusy(false); });
    return () => controller.abort();
  }, [api, jobId, file, comparisonVersion]);
  const assess = async () => {
    const controller = request(); setBusy('Assessing conversion inputs'); setError(''); setPaths([]); setAssessment(null);
    try {
      const result = await api.assess(repo.id, profile, controller.signal);
      if (!controller.signal.aborted) setAssessment(result);
    } catch (cause) { if (!controller.signal.aborted) fail(cause); }
    finally { finish(controller); if (!controller.signal.aborted) setBusy(''); }
  };
  const start = async () => {
    if (!confirmed || !paths.length || !graph || graph.status !== 'complete' || !matchingProfiles(graph.profile, profile)) return;
    const controller = request();
    comparison.current?.abort(); setPreview(null); setFile(''); setJob(null);
    setBusy('Starting conversion'); setError(''); setStale(false); setDownloaded(false);
    try {
      const current = await api.startConversion(repo.id, paths, profile, controller.signal);
      if (!controller.signal.aborted) { setJob(current); onJob(current.id); }
    } catch (cause) { if (!controller.signal.aborted) fail(cause); }
    finally { finish(controller); if (!controller.signal.aborted) setBusy(''); }
  };
  const cancel = async () => {
    if (!job) return;
    const controller = request(); setBusy('Requesting cancellation'); setError('');
    try { await api.cancel(job.id, controller.signal); }
    catch (cause) { if (!controller.signal.aborted) fail(cause); }
    finally { finish(controller); if (!controller.signal.aborted) setBusy(''); }
  };
  const download = async () => {
    if (!job || stale) return;
    const controller = request(); setBusy('Verifying conversion download'); setError(''); setDownloaded(false);
    try {
      const blob = await api.downloadConversion(job.id, controller.signal);
      if (!controller.signal.aborted) {
        const url = URL.createObjectURL(blob);
        try {
          const anchor = document.createElement('a');
          anchor.href = url; anchor.download = 'x86-conversion-draft.zip'; anchor.click();
          setDownloaded(true);
        } finally { URL.revokeObjectURL(url); }
      }
    } catch (cause) { if (!controller.signal.aborted) fail(cause); }
    finally { finish(controller); if (!controller.signal.aborted) setBusy(''); }
  };
  const running = !!job && !terminal(job.status);
  const graphReady = graph?.status === 'complete' && matchingProfiles(graph.profile, profile);
  const unchanged = job?.status === 'succeeded' &&
    job.conversion?.files.every(item => item.status === 'unchanged');
  return <div className="workspace conversion-workspace">
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">OS/400 C++ → Linux x86-64</p><h2>Convert to C++20</h2></div>
        <span className="badge">Reviewable draft</span></div>
      <p>Convert supported big-endian fixed-record reads. IBM APIs, EBCDIC, packed decimals, conditional code and unknown layouts require manual porting and can block conversion. This is not a general OS/400 translator.</p>
      <p className="caption">Conversion uses the verified Neo4j graph. SQLite saves job history and provenance, not another copy of the graph or source files. Originals are never overwritten; no application code is executed.</p>
      <div className="notice">
        <strong>Neo4j conversion context</strong>
        {!graph && !graphError && <p role="status">{graphVersion === 0
          ? 'No graph context loaded. Choose Refresh graph context to verify an existing generation; this does not generate a graph.'
          : 'Loading the current graph…'}</p>}
        {graphError && <p role="alert">{graphError}</p>}
        {graph && <>
          <p className="identifier">Generation: {graph.generation_id}</p>
          <p>{graph.status === 'complete' ? 'Complete source analysis' : 'Incomplete analysis — resolve diagnostics and regenerate'} · {graph.profile.standard}</p>
          {!matchingProfiles(graph.profile, profile) && <p className="warning">The selected conversion settings do not match this graph.
            {' '}<button onClick={() => { setProfile(graph.profile); setAssessment(null); setPaths([]); }}
              disabled={!!busy || running}>Use graph settings</button></p>}
        </>}
        <p>Generate a complete graph with matching settings on the <a href="#/graph">Knowledge graph page</a> before starting.
          Source changes require regeneration; the server rechecks before converting and before showing or downloading output.</p>
        <button onClick={() => setGraphVersion(value => value + 1)} disabled={!!busy || running}>Refresh graph context</button>
      </div>
      <div className="control-row">
        <button onClick={() => void assess()} disabled={!!busy || running}>Assess conversion inputs</button>
        <label>Source C++ standard<select value={profile.standard} disabled={!!busy || running} onChange={event => {
          setProfile({ ...profile, standard: event.target.value as Profile['standard'] });
          setAssessment(null); setPaths([]);
        }}><option value="c++17">C++17</option><option value="c++20">C++20</option></select></label>
      </div>
      {assessment && <fieldset className="conversion-files" disabled={!!busy || running}><legend>Select C++ files to convert</legend>
        {assessment.sources.filter(source => /\.(cpp|cc|cxx)$/i.test(source.path)).map(source => <label key={source.path} className="check-row">
          <input type="checkbox" checked={paths.includes(source.path)} onChange={event => setPaths(previous =>
            event.target.checked ? [...previous, source.path] : previous.filter(path => path !== source.path))} />
          <code>{source.path}</code><small>{source.size.toLocaleString()} bytes</small>
        </label>)}
        <p className="caption">Headers are assessed as dependencies and included unchanged in downloads. Up to 20 selected files, 250 KB per selected file and 1 MB of total inputs.</p>
      </fieldset>}
      <label className="check-row conversion-consent"><input type="checkbox" checked={confirmed} disabled={!!busy || running}
        onChange={event => setConfirmed(event.target.checked)} />
        I confirm records are big-endian, use the declared fixed-width field layout, and text fields already use a target-compatible encoding. Existing endian conversions must match a reviewed pattern.</label>
      <button className="primary" onClick={() => void start()}
        disabled={!graphReady || !assessment || !confirmed || !paths.length || paths.length > 20 || !!busy || running}>Start conversion</button>
      {busy && <p role="status" className="working">{busy}…</p>}
    </section>
    <section className="panel" aria-labelledby="conversion-history-title">
      <div className="panel-heading"><h2 id="conversion-history-title">Saved conversions</h2>
        <button onClick={() => setHistoryVersion(value => value + 1)}>Refresh history</button></div>
      <p className="caption">History survives server restarts for this browser session. Interrupted jobs are not resumed automatically.
        Up to 100 conversions are retained locally across all sessions; expired sessions cannot reopen private jobs.</p>
      {historyError && <p role="alert" className="notice error">{historyError}</p>}
      {!history.length && !historyError && <p>No saved conversions for this repository and browser session.</p>}
      <ul className="conversion-results">{history.map(item => <li key={item.id}>
        <button className="text-button" onClick={() => onJob(item.id)}
          disabled={item.id === jobId || !!busy}>Open conversion {item.id}</button>
        <span> · {item.status} · {item.completed_files} / {item.total_files} files</span>
        {item.conversion && <p className="identifier">Neo4j generation: {item.conversion.generation_id}</p>}
      </li>)}</ul>
    </section>
    {error && <div className="notice error" role="alert">{error}</div>}
    {job && <section className="panel conversion-progress" aria-labelledby="conversion-progress-title">
      <div className="panel-heading"><h2 id="conversion-progress-title">Conversion progress</h2>
        <strong className={`badge ${job.status}`}>{stale ? staleMessage :
          unchanged ? 'Already modernized — no changes required' :
          ({ succeeded: 'Draft ready — review required', blocked: 'Blocked — manual porting required', failed: 'Failed', cancelled: 'Cancelled',
            interrupted: 'Interrupted — start a new conversion' }[job.status] ?? 'In progress')}</strong></div>
      <p role="status">{stageNames[job.stage ?? 'queued'] ?? job.stage} · {job.completed_files} / {job.total_files} files analysed</p>
      <progress aria-label="Files analysed" max={job.total_files || 1} value={job.completed_files} />
      <p className="caption">Counts reflect completed file analysis, not proof that migration is complete. Leaving this page does not cancel the job.</p>
      <p className="identifier">{job.id}</p>
      {running && <button onClick={() => void cancel()} disabled={!!busy}>Cancel conversion</button>}
      {job.conversion && <>
        <p className="identifier">Conversion based on Neo4j generation: {job.conversion.generation_id}</p>
        <p>{job.conversion.validation}</p>
        <ul className="conversion-results">{job.conversion.files.map(item => <li key={item.path}>
          <strong><code>{item.path}</code> · {item.status === 'unchanged' ? 'Already modernized — unchanged' :
            item.status === 'ready' ? `${item.changes} record copies rewritten` : 'Blocked'}</strong>
          {item.diagnostics.map((diagnostic, index) => <p className="warning" key={index}>{diagnostic.code}: {diagnostic.message}</p>)}
          <button className="text-button" onClick={() => { setFile(item.path); setComparisonVersion(value => value + 1); }}
            disabled={stale}>Compare {item.path}</button>
        </li>)}</ul>
        <button onClick={() => void download()} disabled={job.status !== 'succeeded' || stale || !!busy}>Download conversion draft</button>
        {downloaded && <p role="status">Download prepared. Review the manifest and validate on Linux x86-64 before using the code.</p>}
      </>}
    </section>}
    {file && <section className="panel" aria-labelledby="comparison-title">
      <div className="panel-heading"><h2 id="comparison-title">Before / after conversion</h2><code>{file}</code></div>
      {comparisonBusy && <p role="status">Verifying current source and loading comparison…</p>}
      {preview && <div className="code-comparison">
        <div><h3>Before · original OS/400-oriented C++</h3><pre tabIndex={0} aria-label="Original source"><code>{preview.before}</code></pre></div>
        <div><h3>After · Linux x86-64 C++20 draft</h3>{preview.after === null
          ? <p className="notice warning">No converted output: resolve the reported blockers first.</p>
          : <pre tabIndex={0} aria-label="Converted source"><code>{preview.after}</code></pre>}</div>
      </div>}
      {preview?.status === 'unchanged' && <p className="caption">The supported existing endian conversion was recognized. Before and after are identical; no extra byte swap was inserted.</p>}
      <p className="caption">Source text is shown literally, not rendered as HTML. Comparison and download requests recheck the complete input manifest.</p>
    </section>}
  </div>;
}
