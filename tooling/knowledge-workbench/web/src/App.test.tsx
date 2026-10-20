import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { ApiError, WorkbenchApi } from './api';
import { defaultProfile } from './contracts';
import type { Graph, Job } from './contracts';

function graph(repo = 'one', generation = 'gen-one'): Graph {
  return {
    schema_version: 1, repo_id: repo, generation_id: generation,
    profile: defaultProfile, status: 'partial',
    sources: [{ id: 'source', path: 'src/a.cpp', sha256: 'hash', size: 20 }],
    nodes: [{ id: `${repo}:main`, kind: 'function', name: `${repo}_main`, evidence_ids: ['e1'], properties: { translation_unit: 'src/a.cpp' } }],
    edges: [], evidence: [{ id: 'e1', source_id: 'source', start_byte: 0, end_byte: 20, line_start: 1, line_end: 2 }],
    diagnostics: [{ code: 'unsupported_header', message: 'System header not resolved', path: 'src/a.cpp' }],
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function apiFixture() {
  const api = new WorkbenchApi();
  vi.spyOn(api, 'session').mockResolvedValue();
  vi.spyOn(api, 'health').mockResolvedValue();
  vi.spyOn(api, 'sqliteHealth').mockResolvedValue();
  vi.spyOn(api, 'conversionHistory').mockResolvedValue([]);
  vi.spyOn(api, 'repos').mockResolvedValue({ repos: [
    { id: 'one', name: 'First repo', status: 'registered' },
    { id: 'two', name: 'Second repo', status: 'registered' },
  ] });
  vi.spyOn(api, 'graph').mockImplementation(async repo => graph(repo));
  vi.spyOn(api, 'assess').mockResolvedValue({ sources: [{ path: 'src/a.cpp', size: 20 }], profile: defaultProfile, diagnostics: [] });
  return api;
}
async function selectRepo(user: ReturnType<typeof userEvent.setup>, name = 'one') {
  await user.selectOptions(await screen.findByLabelText('Registered repository'), name);
}
afterEach(() => {
  vi.useRealTimers();
  window.history.replaceState(null, '', window.location.pathname);
});

describe('repository workflow', () => {
  it('does not load, assess or generate graphs on mount, repository selection or refresh', async () => {
    const user = userEvent.setup(), api = apiFixture();
    vi.spyOn(api, 'generate');
    render(<App api={api} />);
    await screen.findByText('Neo4j · Connected');
    await screen.findByText('SQLite · Connected');
    expect(api.graph).not.toHaveBeenCalled();
    await selectRepo(user);
    expect(screen.getByText(/No graph loaded/)).toBeInTheDocument();
    await selectRepo(user, 'two');
    await user.click(screen.getByRole('button', { name: 'Reconnect / refresh repositories' }));
    await selectRepo(user);
    expect(api.graph).not.toHaveBeenCalled();
    expect(api.assess).not.toHaveBeenCalled();
    expect(api.generate).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Load current graph' }));
    expect(await screen.findByRole('button', { name: 'one_main' })).toBeInTheDocument();
    expect(api.graph).toHaveBeenCalledTimes(1);
    expect(api.generate).not.toHaveBeenCalled();
  });

  it('offers conversion from the initial page without generating a graph', async () => {
    const user = userEvent.setup(), api = apiFixture();
    vi.spyOn(api, 'generate');
    vi.spyOn(api, 'startConversion');
    render(<App api={api} />);
    const convert = await screen.findByRole('button', { name: 'Convert code' });
    await waitFor(() => expect(convert).toBeEnabled());
    await user.click(convert);
    await screen.findByRole('heading', { name: 'Choose the repository to convert.' });
    expect(api.graph).not.toHaveBeenCalled();
    await selectRepo(user);
    expect(await screen.findByRole('heading', { name: 'Convert to C++20' })).toBeInTheDocument();
    expect(api.graph).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Start conversion' })).toBeDisabled();
    expect(api.generate).not.toHaveBeenCalled();
    expect(api.startConversion).not.toHaveBeenCalled();
  });

  it('keeps the selected repository when opening conversion from its initial workspace', async () => {
    const user = userEvent.setup(), api = apiFixture();
    render(<App api={api} />);
    await selectRepo(user, 'two');
    await user.click(screen.getByRole('button', { name: 'Convert code' }));
    expect(await screen.findByRole('heading', { name: 'Convert to C++20' })).toBeInTheDocument();
    expect(screen.getByLabelText('Registered repository')).toHaveValue('two');
    expect(api.graph).not.toHaveBeenCalled();
  });

  it('shows SQLite failure independently of the Neo4j connection', async () => {
    const api = apiFixture();
    vi.mocked(api.sqliteHealth).mockRejectedValue(new ApiError('job_store_unavailable', 'Cannot read conversion history'));
    render(<App api={api} />);
    expect(await screen.findByText('Neo4j · Connected')).toBeInTheDocument();
    expect(await screen.findByText('SQLite · Disconnected')).toBeInTheDocument();
    expect(screen.getByText(/Cannot read conversion history/)).toBeInTheDocument();
  });

  it('reports session failure without rendering a fake repository list', async () => {
    const api = apiFixture();
    vi.mocked(api.session).mockRejectedValue(new ApiError('unauthorized', 'Session rejected'));
    render(<App api={api} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('unauthorized: Session rejected');
    expect(api.repos).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Registered repository')).toBeDisabled();
  });

  it('requires assessment, sends the chosen standard, and displays a generation failure', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    vi.mocked(api.graph).mockRejectedValue(new ApiError('not_found', 'No graph'));
    vi.spyOn(api, 'generate').mockRejectedValue(new ApiError('neo4j_unavailable', 'Neo4j is unavailable'));
    render(<App api={api} />);
    await selectRepo(user);
    expect(screen.getByRole('button', { name: 'Generate graph' })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('C++ standard'), 'c++17');
    await user.click(screen.getByRole('button', { name: 'Assess repository' }));
    expect(api.assess).toHaveBeenCalledWith('one', expect.objectContaining({ standard: 'c++17' }), expect.any(AbortSignal));
    await user.click(screen.getByRole('button', { name: 'Generate graph' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Neo4j is unavailable');
    expect(screen.queryByRole('heading', { name: 'Structural graph' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generate graph' })).toBeEnabled();
  });

  it('discards a late previous-repository graph response and aborts its request', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    const pending = deferred<Graph>();
    let oldSignal: AbortSignal | undefined;
    vi.mocked(api.graph).mockImplementation((repo, signal) => {
      if (repo === 'one') { oldSignal = signal; return pending.promise; }
      return Promise.resolve(graph('two'));
    });
    render(<App api={api} />);
    await selectRepo(user);
    await user.click(screen.getByRole('button', { name: 'Load current graph' }));
    await selectRepo(user, 'two');
    await user.click(screen.getByRole('button', { name: 'Load current graph' }));
    await screen.findByText('two_main', { selector: 'button' });
    await act(async () => pending.resolve(graph('one')));
    expect(oldSignal?.aborted).toBe(true);
    expect(screen.queryByText('one_main')).not.toBeInTheDocument();
    expect(screen.getByText('gen-one')).toBeInTheDocument();
  });

  it('generates only on explicit request and then loads the published partial graph', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    vi.mocked(api.graph).mockResolvedValue(graph('one', 'new-generation'));
    vi.spyOn(api, 'generate').mockResolvedValue({ id: 'owned-job', repo_id: 'one', status: 'partial', stage: 'finished' });
    render(<App api={api} />);
    await selectRepo(user);
    expect(api.graph).not.toHaveBeenCalled();
    expect(api.generate).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Assess repository' }));
    expect(api.generate).not.toHaveBeenCalled();
    expect(api.graph).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Generate graph' }));
    expect(await screen.findByText('new-generation')).toBeInTheDocument();
    expect(api.generate).toHaveBeenCalledTimes(1);
    expect(api.graph).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Partial extraction: missing relations/)).toBeInTheDocument();
  });

  it('cancels an owned running job and never shows completion data for cancelled work', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    const running: Job = { id: 'owned-job', repo_id: 'one', status: 'running', stage: 'extracting' };
    vi.spyOn(api, 'generate').mockResolvedValue(running);
    vi.spyOn(api, 'job').mockResolvedValue({ ...running, status: 'cancelled' });
    vi.spyOn(api, 'cancel').mockResolvedValue({ ...running, status: 'cancelled' });
    render(<App api={api} />);
    await selectRepo(user);
    await user.click(screen.getByRole('button', { name: 'Assess repository' }));
    await user.click(screen.getByRole('button', { name: 'Generate graph' }));
    await user.click(await screen.findByRole('button', { name: 'Cancel generation' }));
    expect(api.cancel).toHaveBeenCalledWith('owned-job', expect.any(AbortSignal));
    await screen.findByText('Generation cancelled. No new graph is displayed.', {}, { timeout: 2500 });
    expect(screen.queryByRole('heading', { name: 'Structural graph' })).not.toBeInTheDocument();
  });

  it('shows a rejected late cancellation as an error, not a cancelled job', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    vi.spyOn(api, 'generate').mockResolvedValue({ id: 'owned-job', repo_id: 'one', status: 'running', stage: 'publishing' });
    vi.spyOn(api, 'cancel').mockRejectedValue(new ApiError('busy', 'Publishing has started; cancellation is too late', 409));
    render(<App api={api} />);
    await selectRepo(user);
    await user.click(screen.getByRole('button', { name: 'Assess repository' }));
    await user.click(screen.getByRole('button', { name: 'Generate graph' }));
    await user.click(await screen.findByRole('button', { name: 'Cancel generation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('cancellation is too late');
    expect(screen.getByText('Job: running')).toBeInTheDocument();
    expect(screen.queryByText('Job: cancelled')).not.toBeInTheDocument();
  });

  it('reports a failed terminal job and discards the previous graph', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    vi.spyOn(api, 'generate').mockResolvedValue({
      id: 'owned-job', repo_id: 'one', status: 'failed', stage: 'extracting',
      error: { code: 'compiler_missing', message: 'A compatible local compiler is required' },
    });
    render(<App api={api} />);
    await selectRepo(user);
    await user.click(screen.getByRole('button', { name: 'Assess repository' }));
    await user.click(screen.getByRole('button', { name: 'Generate graph' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('compiler_missing');
    expect(screen.getByText('Job: failed')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Structural graph' })).not.toBeInTheDocument();
  });

  it('aborts an evidence request on repository change and ignores a late result', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    const pending = deferred<{ id: string; path: string; line_start: number; line_end: number; text: string }>();
    let oldSignal: AbortSignal | undefined;
    vi.spyOn(api, 'excerpt').mockImplementation((_repo, _id, signal) => {
      oldSignal = signal; return pending.promise;
    });
    render(<App api={api} />);
    await selectRepo(user);
    await user.click(screen.getByRole('button', { name: 'Load current graph' }));
    await user.click(await screen.findByRole('button', { name: 'one_main' }));
    await user.click(screen.getByRole('button', { name: 'src/a.cpp:1–2' }));
    await selectRepo(user, 'two');
    await act(async () => pending.resolve({ id: 'e1', path: 'src/a.cpp', line_start: 1, line_end: 2, text: 'OLD SOURCE TEXT' }));
    expect(oldSignal?.aborted).toBe(true);
    expect(screen.queryByText('OLD SOURCE TEXT')).not.toBeInTheDocument();
  });

  it('rejects evidence after the server generation changes instead of mixing citations', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    vi.spyOn(api, 'excerpt').mockResolvedValue({ id: 'e1', path: 'src/a.cpp', line_start: 1, line_end: 2, text: 'untrusted <script> text' });
    render(<App api={api} />);
    await selectRepo(user);
    await user.click(screen.getByRole('button', { name: 'Load current graph' }));
    await user.click(await screen.findByRole('button', { name: 'one_main' }));
    vi.mocked(api.graph).mockResolvedValue(graph('one', 'gen-two'));
    await user.click(screen.getByRole('button', { name: 'src/a.cpp:1–2' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('generation_changed');
    expect(screen.queryByLabelText('Verified source excerpt')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Structural graph' })).not.toBeInTheDocument();
  });

  it('shows partial diagnostics, filters real graph nodes, and escapes verified source text', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    vi.spyOn(api, 'excerpt').mockResolvedValue({ id: 'e1', path: 'src/a.cpp', line_start: 1, line_end: 2, text: '<script>danger()</script>' });
    render(<App api={api} />);
    await selectRepo(user);
    await user.click(screen.getByRole('button', { name: 'Load current graph' }));
    expect(await screen.findByText('System header not resolved')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'one_main' }));
    await user.click(screen.getByRole('button', { name: 'src/a.cpp:1–2' }));
    expect(await screen.findByLabelText('Verified source excerpt')).toHaveTextContent('<script>danger()</script>');
    expect(document.querySelector('pre script')).toBeNull();
    await user.type(screen.getByLabelText('Find symbol or identifier'), 'missing_symbol');
    expect(screen.getByText(/No nodes match these filters/)).toBeInTheDocument();
  });

  it('rejects mismatched document previews without presenting them as current', async () => {
    const user = userEvent.setup();
    const api = apiFixture();
    vi.spyOn(api, 'preview').mockResolvedValue({
      id: 'export', kind: 'as-built', generation_id: 'different',
      files: [{ name: 'as-built.md', content: 'NOT CURRENT' }],
    });
    render(<App api={api} />);
    await selectRepo(user);
    await user.click(screen.getByRole('button', { name: 'Load current graph' }));
    await user.click(await screen.findByRole('button', { name: 'Preview documents' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('generation_changed');
    expect(screen.queryByText('NOT CURRENT')).not.toBeInTheDocument();
  });

  it('bounds the SVG and paginates a large graph without dropping table access', async () => {
    const api = apiFixture();
    const data = graph();
    data.nodes = Array.from({ length: 250 }, (_, i) => ({
      id: `node-${i}`, kind: 'function', name: `function_${i}`, properties: {}, evidence_ids: [],
    }));
    vi.mocked(api.graph).mockResolvedValue(data);
    render(<App api={api} />);
    fireEvent.change(await screen.findByLabelText('Registered repository'), { target: { value: 'one' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load current graph' }));
    const table = await screen.findByRole('table');
    expect(document.querySelectorAll('svg g[role="button"]')).toHaveLength(36);
    expect(within(table).getAllByRole('row')).toHaveLength(101);
    fireEvent.click(screen.getByRole('button', { name: 'Next symbols' }));
    await waitFor(() => expect(within(table).getByText('function_100')).toBeInTheDocument());
  });
});
