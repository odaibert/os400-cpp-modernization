import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchApi } from './api';
import { defaultProfile } from './contracts';

afterEach(() => vi.unstubAllGlobals());

describe('same-origin API facade', () => {
  it('establishes a session and sends credentials, JSON profile, and CSRF on assessment', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'session-token' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ sources: [], profile: defaultProfile, diagnostics: [] })));
    vi.stubGlobal('fetch', fetchMock);
    const api = new WorkbenchApi();
    const signal = new AbortController().signal;
    await api.session(signal);
    await api.assess('repo/identifier', defaultProfile, signal);
    const [url, options] = fetchMock.mock.calls[1];
    expect(url).toBe('/api/repos/repo%2Fidentifier/assessment');
    expect(options.credentials).toBe('same-origin');
    expect(options.headers.get('X-CSRF-Token')).toBe('session-token');
    expect(options.headers.get('Content-Type')).toBe('application/json');
    expect(JSON.parse(options.body)).toEqual(defaultProfile);
  });

  it('turns network rejection and structured authorization errors into visible-safe failures', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'Session expired' } }), { status: 401 }));
    vi.stubGlobal('fetch', fetchMock);
    const api = new WorkbenchApi();
    const signal = new AbortController().signal;
    await expect(api.repos(signal)).rejects.toMatchObject({ code: 'network_error' });
    await expect(api.repos(signal)).rejects.toMatchObject({ code: 'unauthorized', message: 'Session expired' });
  });

  it('fetches ZIP downloads with session credentials and rejects success-shaped non-ZIP responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('<html>Not a ZIP</html>', { headers: { 'Content-Type': 'text/html' } }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(new WorkbenchApi().download('one', 'as-built', new AbortController().signal))
      .rejects.toMatchObject({ code: 'invalid_download' });
    expect(fetchMock.mock.calls[0][1].credentials).toBe('same-origin');
  });

  it('rejects malformed or cross-repository graph payloads before rendering', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({
      schema_version: 1, repo_id: 'other', generation_id: 'g', nodes: [{}],
    }))).mockResolvedValueOnce(new Response(JSON.stringify(null))));
    const api = new WorkbenchApi();
    await expect(api.graph('one', new AbortController().signal)).rejects.toMatchObject({ code: 'invalid_graph' });
    await expect(api.graph('one', new AbortController().signal)).rejects.toMatchObject({ code: 'invalid_graph' });
  });

  it('does not treat a merely configured database as connected', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready', neo4j: 'configured' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready', neo4j: 'connected' }))));
    const api = new WorkbenchApi(), signal = new AbortController().signal;
    await expect(api.health(signal)).rejects.toMatchObject({ code: 'invalid_health' });
    await expect(api.health(signal)).resolves.toBeUndefined();
  });

  it('checks SQLite independently and rejects a configured-only or wrong-database response', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready', sqlite: 'configured' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready', neo4j: 'connected' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready', sqlite: 'connected' })));
    vi.stubGlobal('fetch', fetchMock);
    const api = new WorkbenchApi(), signal = new AbortController().signal;
    await expect(api.sqliteHealth(signal)).rejects.toMatchObject({ code: 'invalid_health' });
    await expect(api.sqliteHealth(signal)).rejects.toMatchObject({ code: 'invalid_health' });
    await expect(api.sqliteHealth(signal)).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[2][0]).toBe('/api/health/sqlite');
    expect(fetchMock.mock.calls[2][1].credentials).toBe('same-origin');
  });

  it('rejects mismatched conversion jobs and wrong-file previews', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'job', repo_id: 'other', kind: 'conversion' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        path: 'other.cpp', status: 'ready', changes: 1, diagnostics: [],
        before: 'before', after: 'after', requires_review: true,
      }))));
    const api = new WorkbenchApi(), signal = new AbortController().signal;
    await expect(api.conversionJob('job', 'one', signal)).rejects.toMatchObject({ code: 'invalid_conversion' });
    await expect(api.conversionPreview('job', 'main.cpp', signal)).rejects.toMatchObject({ code: 'invalid_conversion' });
  });

  it('accepts unchanged previews only when before and after really match', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        path: 'main.cpp', status: 'unchanged', changes: 0, diagnostics: [],
        before: 'original', after: 'modified', requires_review: true,
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        path: 'main.cpp', status: 'unchanged', changes: 0, diagnostics: [],
        before: 'original', after: 'original', requires_review: true,
      }))));
    const api = new WorkbenchApi(), signal = new AbortController().signal;
    await expect(api.conversionPreview('job', 'main.cpp', signal)).rejects.toMatchObject({ code: 'invalid_conversion' });
    await expect(api.conversionPreview('job', 'main.cpp', signal)).resolves.toMatchObject({ status: 'unchanged' });
  });

  it('accepts successful jobs containing already-modernized files', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: 'job', repo_id: 'one', kind: 'conversion', status: 'succeeded', stage: 'finished',
      completed_files: 1, total_files: 1, error: null,
      conversion: {
        target: 'linux-x86_64-c++20', requires_review: true, validation_status: 'passed',
        validation: 'Native checks only',
        generation_id: 'generation', graph_digest: 'digest', profile: defaultProfile,
        files: [{ path: 'main.cpp', status: 'unchanged', changes: 0, diagnostics: [] }],
      },
    }))));
    await expect(new WorkbenchApi().conversionJob('job', 'one', new AbortController().signal))
      .resolves.toMatchObject({ status: 'succeeded', conversion: { files: [{ status: 'unchanged' }] } });
  });

  it('rejects cross-repository saved conversion history', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      jobs: [{ id: 'job', repo_id: 'other', kind: 'conversion', status: 'interrupted' }],
    }))));
    await expect(new WorkbenchApi().conversionHistory('one', new AbortController().signal))
      .rejects.toMatchObject({ code: 'invalid_conversion' });
  });
});
