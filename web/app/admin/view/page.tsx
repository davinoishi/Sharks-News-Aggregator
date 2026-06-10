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
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto p-4 md:p-8">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <Link href="/admin" className="text-sm text-blue-600 hover:underline">
              ← Admin
            </Link>
            <h1 className="text-2xl font-bold text-gray-900 mt-1">{label}</h1>
            <p className="text-xs text-gray-500 mt-1">
              <code>/api/admin/{endpoint}</code>
              {httpStatus !== null && <span className="ml-2">· HTTP {httpStatus}</span>}
            </p>
          </div>
          <button
            onClick={load}
            className="shrink-0 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Refresh
          </button>
        </div>

        {state === 'loading' && <p className="text-gray-500">Loading…</p>}
        {state === 'error' && (
          <p className="mb-3 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            Request failed{httpStatus ? ` (HTTP ${httpStatus})` : ''}.
          </p>
        )}

        {data && (
          <pre className="overflow-auto rounded-lg border border-gray-200 bg-white p-4 text-xs leading-relaxed text-gray-800 whitespace-pre-wrap break-words">
            {data}
          </pre>
        )}
      </div>
    </main>
  );
}

export default function AdminViewPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-500">Loading…</div>}>
      <Viewer />
    </Suspense>
  );
}
