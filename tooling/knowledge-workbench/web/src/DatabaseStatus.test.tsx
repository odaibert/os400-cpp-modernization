import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, WorkbenchApi } from './api';
import { DatabaseStatus } from './DatabaseStatus';

afterEach(() => vi.useRealTimers());

describe.each([
  ['Neo4j', 'health'],
  ['SQLite', 'sqliteHealth'],
] as const)('%s connection indicator', (database, method) => {
  it('shows checking until the live check resolves, then connected', async () => {
    let resolve!: () => void;
    const api = new WorkbenchApi();
    vi.spyOn(api, method).mockReturnValue(new Promise<void>(yes => { resolve = yes; }));
    render(<DatabaseStatus api={api} session="ready" database={database} />);
    expect(screen.getByRole('status')).toHaveTextContent(`${database} · Checking`);
    await act(async () => resolve());
    expect(screen.getByRole('status')).toHaveTextContent(`${database} · Connected`);
  });

  it('reports database failure and allows an explicit successful retry', async () => {
    const api = new WorkbenchApi();
    vi.spyOn(api, method).mockRejectedValueOnce(new ApiError('database_unavailable', `Check local ${database}`, 503))
      .mockResolvedValueOnce();
    render(<DatabaseStatus api={api} session="ready" database={database} />);
    expect(await screen.findByText(`${database} · Disconnected`)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(`Check local ${database}`);
    fireEvent.click(screen.getByRole('button', { name: `Check ${database} connection` }));
    expect(await screen.findByText(`${database} · Connected`)).toBeInTheDocument();
  });

  it('polls again and aborts observation when unmounted', async () => {
    vi.useFakeTimers();
    const api = new WorkbenchApi();
    let signal: AbortSignal | undefined;
    vi.spyOn(api, method).mockResolvedValueOnce().mockImplementation(nextSignal => {
      signal = nextSignal;
      return new Promise(() => {});
    });
    const view = render(<DatabaseStatus api={api} session="ready" database={database} />);
    await act(async () => {});
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(api[method]).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('status')).toHaveTextContent('Checking');
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it('waits for a valid session and aborts checks when the session fails', async () => {
    const api = new WorkbenchApi();
    let signal: AbortSignal | undefined;
    vi.spyOn(api, method).mockImplementation(nextSignal => {
      signal = nextSignal;
      return new Promise(() => {});
    });
    const view = render(<DatabaseStatus api={api} session="loading" database={database} />);
    expect(api[method]).not.toHaveBeenCalled();
    view.rerender(<DatabaseStatus api={api} session="ready" database={database} />);
    expect(api[method]).toHaveBeenCalledTimes(1);
    view.rerender(<DatabaseStatus api={api} session="error" database={database} />);
    expect(signal?.aborted).toBe(true);
    expect(screen.getByRole('status')).toHaveTextContent(`${database} · Disconnected`);
  });
});
