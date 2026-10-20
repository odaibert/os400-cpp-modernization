import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ApiError, WorkbenchApi } from './api';
import { ConversionWorkspace } from './ConversionWorkspace';
import { defaultProfile } from './contracts';
import type { ConversionJob } from './contracts';

afterEach(() => vi.unstubAllGlobals());

function job(status = 'succeeded'): ConversionJob {
  return {
    id: 'conversion-one', repo_id: 'one', kind: 'conversion', status, stage: 'finished',
    completed_files: 1, total_files: 1,
    conversion: {
      target: 'linux-x86_64-c++20', requires_review: true, validation_status: 'passed',
      validation: 'Native checks only. Linux x86-64 execution not performed.',
      generation_id: 'stored-generation', graph_digest: 'graph-digest', profile: defaultProfile,
      files: [{ path: 'main.cpp', status: 'ready', changes: 1, diagnostics: [] }],
    },
  };
}
function fixture() {
  const api = new WorkbenchApi();
  vi.spyOn(api, 'graph').mockResolvedValue({
    schema_version: 1, repo_id: 'one', generation_id: 'stored-generation', status: 'complete',
    profile: defaultProfile, sources: [], nodes: [], edges: [], evidence: [], diagnostics: [],
  });
  vi.spyOn(api, 'conversionHistory').mockResolvedValue([]);
  vi.spyOn(api, 'assess').mockResolvedValue({
    sources: [{ path: 'main.cpp', size: 100 }, { path: 'record.hpp', size: 20 }],
    profile: defaultProfile, diagnostics: [],
  });
  vi.spyOn(api, 'startConversion').mockResolvedValue(job());
  vi.spyOn(api, 'conversionJob').mockResolvedValue(job());
  vi.spyOn(api, 'conversionPreview').mockResolvedValue({
    path: 'main.cpp', status: 'ready', changes: 1, diagnostics: [], requires_review: true,
    before: '<script>original()</script>', after: '<script>converted()</script>',
  });
  return api;
}
function Harness({ api, initial = '' }: { api: WorkbenchApi; initial?: string }) {
  const [id, setId] = useState(initial);
  return <ConversionWorkspace api={api} repo={{ id: 'one', name: 'Example', status: 'registered' }} jobId={id} onJob={setId} />;
}

it('requires assessed file selection and explicit layout confirmation before starting', async () => {
  const user = userEvent.setup(), api = fixture();
  render(<Harness api={api} />);
  const start = screen.getByRole('button', { name: 'Start conversion' });
  expect(start).toBeDisabled();
  expect(api.graph).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Refresh graph context' }));
  await screen.findByText(/Complete source analysis/);
  await user.click(screen.getByRole('button', { name: 'Assess conversion inputs' }));
  await user.click(screen.getByLabelText(/main.cpp/));
  expect(start).toBeDisabled();
  await user.click(screen.getByLabelText(/I confirm records are big-endian/));
  await user.click(start);
  await screen.findByText('Draft ready — review required');
  expect(api.startConversion).toHaveBeenCalledWith('one', ['main.cpp'], defaultProfile, expect.any(AbortSignal));
  expect(screen.queryByRole('checkbox', { name: /record.hpp/ })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Compare main.cpp' }));
  expect(await screen.findByLabelText('Original source')).toHaveTextContent('<script>original()</script>');
  expect(screen.getByLabelText('Converted source')).toHaveTextContent('<script>converted()</script>');
  expect(document.querySelector('pre script')).toBeNull();
});

it('rechecks the same comparison and removes old output when sources change', async () => {
  const user = userEvent.setup(), api = fixture();
  render(<Harness api={api} initial="conversion-one" />);
  const compare = await screen.findByRole('button', { name: 'Compare main.cpp' });
  expect(api.graph).not.toHaveBeenCalled();
  await user.click(compare);
  await screen.findByLabelText('Converted source');
  vi.mocked(api.conversionPreview).mockRejectedValueOnce(new ApiError('source_changed', 'Start a new conversion', 409));
  await user.click(compare);
  expect(await screen.findByRole('alert')).toHaveTextContent('source_changed');
  expect(screen.queryByLabelText('Converted source')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Download conversion draft' })).toBeDisabled();
});

it('shows blockers without inventing converted output or enabling download', async () => {
  const user = userEvent.setup(), api = fixture(), blocked = job('blocked');
  blocked.conversion!.validation_status = 'blocked';
  blocked.conversion!.files[0] = { path: 'main.cpp', status: 'blocked', changes: 0,
    diagnostics: [{ code: 'unsupported_call', message: 'IBM API requires a porting adapter', path: 'main.cpp' }] };
  vi.mocked(api.conversionJob).mockResolvedValue(blocked);
  vi.mocked(api.conversionPreview).mockResolvedValue({
    ...blocked.conversion!.files[0], before: 'IBM_api();', after: null, requires_review: true,
  });
  render(<Harness api={api} initial="conversion-one" />);
  expect(await screen.findByText(/IBM API requires a porting adapter/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Download conversion draft' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Compare main.cpp' }));
  expect(await screen.findByText(/No converted output/)).toBeInTheDocument();
});

it('labels already-modernized input unchanged and shows identical before/after code', async () => {
  const user = userEvent.setup(), api = fixture(), unchanged = job();
  unchanged.conversion!.files[0] = { path: 'main.cpp', status: 'unchanged', changes: 0, diagnostics: [] };
  vi.mocked(api.conversionJob).mockResolvedValue(unchanged);
  vi.mocked(api.conversionPreview).mockResolvedValue({
    ...unchanged.conversion!.files[0], before: 'existing_portable_code();',
    after: 'existing_portable_code();', requires_review: true,
  });
  render(<Harness api={api} initial="conversion-one" />);
  expect(await screen.findByText('Already modernized — no changes required')).toBeInTheDocument();
  expect(screen.getByText(/Already modernized — unchanged/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Download conversion draft' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Compare main.cpp' }));
  expect(await screen.findByLabelText('Original source')).toHaveTextContent('existing_portable_code();');
  expect(screen.getByLabelText('Converted source')).toHaveTextContent('existing_portable_code();');
});

it('aborts a pending comparison on navigation and ignores its late result', async () => {
  const api = fixture();
  let resolve!: (value: Awaited<ReturnType<WorkbenchApi['conversionPreview']>>) => void;
  let signal: AbortSignal | undefined;
  vi.mocked(api.conversionPreview).mockImplementation((_id, _path, currentSignal) => {
    signal = currentSignal; return new Promise(yes => { resolve = yes; });
  });
  const view = render(<Harness api={api} initial="conversion-one" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Compare main.cpp' }));
  await waitFor(() => expect(api.conversionPreview).toHaveBeenCalled());
  view.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve({ path: 'main.cpp', status: 'ready', changes: 1, diagnostics: [],
    before: 'old', after: 'late', requires_review: true }));
  expect(screen.queryByText('late')).not.toBeInTheDocument();
});

it('requires a complete Neo4j graph with matching settings before conversion', async () => {
  const user = userEvent.setup(), api = fixture();
  vi.mocked(api.graph).mockResolvedValueOnce({
    schema_version: 1, repo_id: 'one', generation_id: 'partial-generation', status: 'partial',
    profile: defaultProfile, sources: [], nodes: [], edges: [], evidence: [], diagnostics: [],
  });
  render(<Harness api={api} />);
  expect(api.graph).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Refresh graph context' }));
  await screen.findByText(/Incomplete analysis/);
  await user.click(screen.getByRole('button', { name: 'Assess conversion inputs' }));
  await user.click(screen.getByLabelText(/main.cpp/));
  await user.click(screen.getByLabelText(/I confirm records are big-endian/));
  expect(screen.getByRole('button', { name: 'Start conversion' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Refresh graph context' }));
  await screen.findByText(/Complete source analysis/);
  expect(screen.getByRole('button', { name: 'Start conversion' })).toBeEnabled();
  await user.selectOptions(screen.getByLabelText('Source C++ standard'), 'c++17');
  expect(screen.getByRole('button', { name: 'Start conversion' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Use graph settings' })).toBeInTheDocument();
});

it('recovers an interrupted conversion from saved history without resubmitting it', async () => {
  const user = userEvent.setup(), api = fixture(), interrupted = job('interrupted');
  interrupted.conversion = null;
  interrupted.error = { code: 'job_interrupted', message: 'Server stopped. Start a new conversion.' };
  vi.mocked(api.conversionHistory).mockResolvedValue([interrupted]);
  vi.mocked(api.conversionJob).mockResolvedValue(interrupted);
  render(<Harness api={api} />);
  await user.click(await screen.findByRole('button', { name: 'Open conversion conversion-one' }));
  expect(await screen.findByText('Interrupted — start a new conversion')).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('job_interrupted');
  expect(api.startConversion).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: 'Download conversion draft' })).not.toBeInTheDocument();
});

it('never restores a delayed comparison after download proves the source stale', async () => {
  const user = userEvent.setup(), api = fixture();
  let resolve!: (value: Awaited<ReturnType<WorkbenchApi['conversionPreview']>>) => void;
  let signal: AbortSignal | undefined;
  vi.mocked(api.conversionPreview).mockImplementation((_id, _path, currentSignal) => {
    signal = currentSignal;
    return new Promise(yes => { resolve = yes; });
  });
  vi.spyOn(api, 'downloadConversion').mockRejectedValue(
    new ApiError('source_changed', 'Source changed. Start a new conversion.', 409),
  );
  render(<Harness api={api} initial="conversion-one" />);
  await user.click(await screen.findByRole('button', { name: 'Compare main.cpp' }));
  await user.click(screen.getByRole('button', { name: 'Download conversion draft' }));
  await screen.findByText('Source changed — restart required');
  await act(async () => resolve({
    path: 'main.cpp', status: 'ready', changes: 1, diagnostics: [],
    before: 'old original', after: 'stale converted output', requires_review: true,
  }));
  expect(signal?.aborted).toBe(true);
  expect(screen.queryByLabelText('Original source')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Converted source')).not.toBeInTheDocument();
});

it('never delivers a delayed download after a comparison proves the source stale', async () => {
  const user = userEvent.setup(), api = fixture(), createObjectURL = vi.fn();
  vi.stubGlobal('URL', { createObjectURL, revokeObjectURL: vi.fn() });
  let resolve!: (value: Blob) => void;
  let signal: AbortSignal | undefined;
  vi.spyOn(api, 'downloadConversion').mockImplementation((_id, currentSignal) => {
    signal = currentSignal;
    return new Promise(yes => { resolve = yes; });
  });
  vi.mocked(api.conversionPreview).mockRejectedValue(
    new ApiError('source_changed', 'Start a new conversion.', 409),
  );
  render(<Harness api={api} initial="conversion-one" />);
  await user.click(await screen.findByRole('button', { name: 'Download conversion draft' }));
  await user.click(screen.getByRole('button', { name: 'Compare main.cpp' }));
  await screen.findByText('Source changed — restart required');
  await act(async () => resolve(new Blob(['obsolete output'])));
  expect(signal?.aborted).toBe(true);
  expect(createObjectURL).not.toHaveBeenCalled();
  expect(screen.queryByText(/Download prepared/)).not.toBeInTheDocument();
});
