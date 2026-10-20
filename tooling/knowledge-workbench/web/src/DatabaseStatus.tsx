import { useEffect, useState } from 'react';
import { describeError, WorkbenchApi } from './api';

export function DatabaseStatus({ api, session, database }: {
  api: WorkbenchApi; session: 'loading' | 'ready' | 'error'; database: 'Neo4j' | 'SQLite';
}) {
  const [mode, setMode] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [detail, setDetail] = useState('Waiting for the local session.');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (session !== 'ready') {
      setMode(session === 'error' ? 'disconnected' : 'checking');
      setDetail(session === 'error' ? `Local API unavailable. Reconnect to check ${database}.` : 'Waiting for the local session.');
      return;
    }
    let stopped = false;
    let next: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    let deadline: ReturnType<typeof setTimeout>;
    const check = async () => {
      controller = new AbortController();
      let timedOut = false;
      setMode('checking'); setDetail('Checking the database connection.');
      deadline = setTimeout(() => { timedOut = true; controller.abort(); }, 12_000);
      try {
        if (database === 'Neo4j') await api.health(controller.signal);
        else await api.sqliteHealth(controller.signal);
        if (!stopped) { setMode('connected'); setDetail('Live database check passed. Rechecked every 15 seconds.'); }
      } catch (cause) {
        if (!stopped) {
          setMode('disconnected');
          setDetail(timedOut ? `Database check timed out. Check local ${database} and retry.` : describeError(cause));
        }
      } finally {
        clearTimeout(deadline);
        if (!stopped) next = setTimeout(() => void check(), 15_000);
      }
    };
    void check();
    return () => { stopped = true; controller?.abort(); clearTimeout(next); clearTimeout(deadline); };
  }, [api, session, refresh, database]);
  const label = { checking: 'Checking', connected: 'Connected', disconnected: 'Disconnected' }[mode];
  return <div className="database-status">
    <div className="database-state" role="status" aria-live="polite" title={detail}>
      <span className={`traffic-signal ${mode}`} aria-hidden="true">
        <span className="lamp red" /><span className="lamp amber" /><span className="lamp green" />
      </span>
      <span><strong>{database} · {label}</strong><small>{detail}</small></span>
    </div>
    <button className="text-button" onClick={() => setRefresh(value => value + 1)}
      disabled={session !== 'ready' || mode === 'checking'}>Check {database} connection</button>
  </div>;
}
