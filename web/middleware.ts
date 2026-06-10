import { NextRequest, NextResponse } from 'next/server';

/**
 * Gate the admin surface with HTTP Basic auth.
 *
 * Protects both the admin page (`/admin/*`) and the admin proxy API routes
 * (`/api/admin/*`). Basic auth is used because browsers (including mobile)
 * prompt natively, so the admin page stays usable from a phone with no custom
 * login UI. Credentials come from server-side env vars only.
 *
 * Fail closed: if no password is configured the admin area returns 503.
 */

const ADMIN_USER = process.env.ADMIN_PANEL_USER || 'admin';
const ADMIN_PASSWORD = process.env.ADMIN_PANEL_PASSWORD || '';

function unauthorized() {
  return new NextResponse('Authentication required.', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="Sharks Admin", charset="UTF-8"',
    },
  });
}

// Length-independent comparison to avoid leaking the password via timing.
function safeEqual(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let mismatch = a.length === b.length ? 0 : 1;
  for (let i = 0; i < len; i++) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

export function middleware(request: NextRequest) {
  if (!ADMIN_PASSWORD) {
    return new NextResponse('Admin panel is not configured.', { status: 503 });
  }

  const header = request.headers.get('authorization') || '';
  if (header.startsWith('Basic ')) {
    let decoded = '';
    try {
      decoded = atob(header.slice(6));
    } catch {
      return unauthorized();
    }
    const sep = decoded.indexOf(':');
    if (sep !== -1) {
      const user = decoded.slice(0, sep);
      const pass = decoded.slice(sep + 1);
      if (safeEqual(user, ADMIN_USER) && safeEqual(pass, ADMIN_PASSWORD)) {
        return NextResponse.next();
      }
    }
  }

  return unauthorized();
}

export const config = {
  matcher: ['/admin/:path*', '/api/admin/:path*'],
};
