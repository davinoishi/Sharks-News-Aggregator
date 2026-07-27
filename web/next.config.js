/** @type {import('next').NextConfig} */

const isDev = process.env.NODE_ENV === 'development'

// Content-Security-Policy.
// 'unsafe-inline' is required for styles (Tailwind/Next inject inline <style>)
// and for Next.js's inline hydration/bootstrap <script> tags (no nonce pipeline
// in use). Verified against `next start` — the feed, cluster expand, and filters
// run with this policy and no console violations. connect-src 'self' is enough
// because the browser only ever calls same-origin /api/* routes.
//
// The dev server needs two extra sources, and only the dev server:
//   'unsafe-eval'  next dev compiles with eval-based source maps and React
//                  Refresh evaluates modules at runtime. Without it the client
//                  bundle never executes — the page server-renders but never
//                  hydrates, so nothing fetches and no control responds.
//   ws:            the HMR socket. 'self' is specified to cover same-origin
//                  WebSockets, but browsers disagree in practice, so name it.
// These are appended only when NODE_ENV === 'development'. `next build` and
// `next start` — which is what the Pi runs — emit the identical policy to
// before this branch existed.
const scriptSrc = ["'self'", "'unsafe-inline'"]
const connectSrc = ["'self'"]

if (isDev) {
  scriptSrc.push("'unsafe-eval'")
  connectSrc.push('ws:')
}

const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "font-src 'self' data:",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "img-src 'self' data: blob:",
  "object-src 'none'",
  `script-src ${scriptSrc.join(' ')}`,
  "style-src 'self' 'unsafe-inline'",
  `connect-src ${connectSrc.join(' ')}`,
].join('; ')

const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=(), browsing-topics=()',
  },
  { key: 'Content-Security-Policy', value: csp },
]

const nextConfig = {
  allowedDevOrigins: ['x2mq74oetjlz.nobgp.com'],

  async headers() {
    return [
      {
        // Security headers on every response.
        source: '/:path*',
        headers: securityHeaders,
      },
      {
        // Never cache HTML pages — always revalidate so stale chunks never load.
        // /rss is excluded so its own 5-minute Cache-Control survives (U5).
        source: '/((?!_next/static|_next/image|favicon.ico|rss).*)',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-cache, no-store, must-revalidate',
          },
        ],
      },
      {
        // Static assets have content hashes — safe to cache aggressively.
        //
        // Only in a real build. `next dev` emits unhashed chunk names
        // (/_next/static/chunks/app/page.js), so marking them immutable makes
        // the browser pin the first dev bundle it ever sees for a year: edits
        // recompile on the server but never reach the page, and even a new tab
        // replays stale code against fresh HTML. Dev revalidates instead.
        source: '/_next/static/(.*)',
        headers: [
          {
            key: 'Cache-Control',
            value: isDev
              ? 'no-cache, no-store, must-revalidate'
              : 'public, max-age=31536000, immutable',
          },
        ],
      },
    ]
  },
}

module.exports = nextConfig
