'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

export const dynamic = 'force-dynamic';

function Viewer() {
  const params = useSearchParams();
  const endpoint = (params.get('endpoint') || '').replace(/^\/+/, '');
  const label = params.get('label') || endpoint || 'Admin view';

  const [data, setData] = useState<string>('');
  const [state, setState] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle');
  const [httpStatus, setHttpStatus] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!endpoint) {
      setState('error');
      setData('No endpoint specified.');
      return;
    }
    setState('loading');
    try {
      const res = await fetch(`/api/admin/${endpoint}`, { cache: 'no-store' });
      setHttpStatus(res.status);
      const text = await res.text();
      let pretty = text;
      try {
        pretty = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        /* leave as-is if not JSON */
      }
      setData(pretty);
      setState(res.ok ? 'ok' : 'error');
    } catch (err) {
      setState('error');
      setData(err instanceof Error ? err.message : String(err));
    }
  }, [endpoint]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="min-h-screen bg-canvas">
      <div className="max-w-5xl mx-auto p-4 md:p-8">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <Link href="/admin" className="text-ui text-action hover:underline">
              ← Admin
            </Link>
            <h1 className="font-display text-title text-content mt-1">{label}</h1>
            <p className="text-meta text-content-muted mt-1">
              <code>/api/admin/{endpoint}</code>
              {httpStatus !== null && <span className="ml-2">· HTTP {httpStatus}</span>}
            </p>
          </div>
          <button
            onClick={load}
            className="tap-44 shrink-0 inline-flex items-center rounded-md border border-edge-strong bg-surface px-3 py-2 text-ui text-content-secondary hover:bg-surface-sunken"
          >
            Refresh
          </button>
        </div>

        {state === 'loading' && <p className="text-body text-content-muted">Loading…</p>}
        {state === 'error' && (
          <p className="mb-3 rounded-md bg-critical border border-critical-edge px-3 py-2 text-ui font-normal text-critical-fg">
            Request failed{httpStatus ? ` (HTTP ${httpStatus})` : ''}.
          </p>
        )}

        {data && (
          <pre className="overflow-auto rounded-lg border border-edge bg-surface p-4 font-mono text-xs leading-relaxed text-content-secondary whitespace-pre-wrap break-words">
            {data}
          </pre>
        )}
      </div>
    </main>
  );
}

export default function AdminViewPage() {
  return (
    <Suspense fallback={<div className="p-8 text-body text-content-muted">Loading…</div>}>
      <Viewer />
    </Suspense>
  );
}
