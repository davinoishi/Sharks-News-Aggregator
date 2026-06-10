import { NextRequest, NextResponse } from 'next/server';
import { INTERNAL_API_URL, ADMIN_API_KEY } from '../../config';

/**
 * Catch-all proxy for every backend /admin/* endpoint.
 *
 * - Gated by middleware (HTTP Basic) like the rest of /api/admin/*.
 * - Injects the server-side X-Admin-API-Key (never exposed to the browser).
 * - Forwards path + query (GET) and body (POST) to the FastAPI backend.
 *
 * A more specific route (e.g. app/api/admin/sources/route.ts) takes precedence
 * over this catch-all, so existing dedicated routes keep their behaviour.
 */

function buildTarget(path: string[], search: string): string | null {
  // Defense in depth: never let a forged segment escape the /admin/ prefix.
  const bad = (seg: string) =>
    seg === '' || seg === '.' || seg.includes('..') || seg.includes('/') || seg.includes('\\');
  if (path.some(bad)) return null;
  const suffix = path.map(encodeURIComponent).join('/');
  return `${INTERNAL_API_URL}/admin/${suffix}${search}`;
}

async function forward(request: NextRequest, path: string[], method: 'GET' | 'POST') {
  const target = buildTarget(path, request.nextUrl.search);
  if (!target) {
    return NextResponse.json({ error: 'Invalid admin path' }, { status: 400 });
  }

  const headers: Record<string, string> = {
    Accept: 'application/json',
    'X-Admin-API-Key': ADMIN_API_KEY,
  };

  let body: string | undefined;
  if (method === 'POST') {
    const text = await request.text();
    if (text) {
      body = text;
      headers['Content-Type'] = request.headers.get('content-type') || 'application/json';
    }
  }

  try {
    const resp = await fetch(target, { method, headers, body, cache: 'no-store' });
    const text = await resp.text();
    return new NextResponse(text, {
      status: resp.status,
      headers: { 'content-type': resp.headers.get('content-type') || 'application/json' },
    });
  } catch (error) {
    console.error(`Error proxying to backend /admin/${path.join('/')}:`, error);
    return NextResponse.json({ error: 'Failed to reach backend' }, { status: 502 });
  }
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(request, path, 'GET');
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(request, path, 'POST');
}
