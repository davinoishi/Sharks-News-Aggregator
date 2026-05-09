/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ['x2mq74oetjlz.nobgp.com'],

  async headers() {
    return [
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
