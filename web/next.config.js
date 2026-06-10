/** @type {import('next').NextConfig} */

// Content-Security-Policy.
// 'unsafe-inline' is required for styles (Tailwind/Next inject inline <style>)
// and for Next.js's inline hydration/bootstrap <script> tags (no nonce pipeline
// in use). Verified against `next start` — the feed, cluster expand, and filters
// run with this policy and no console violations. connect-src 'self' is enough
// because the browser only ever calls same-origin /api/* routes.
const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "font-src 'self' data:",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "img-src 'self' data: blob:",
  "object-src 'none'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "connect-src 'self'",
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
        // Never cache HTML pages — always revalidate so stale chunks never load
        source: '/((?!_next/static|_next/image|favicon.ico).*)',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-cache, no-store, must-revalidate',
          },
        ],
      },
      {
        // Static assets have content hashes — safe to cache aggressively
        source: '/_next/static/(.*)',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
    ]
  },
}

module.exports = nextConfig
