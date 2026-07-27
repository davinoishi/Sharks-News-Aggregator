import type { MetadataRoute } from 'next';
import { absoluteUrl } from './lib/site';

// Cheap and near-static; no reason to recompute per request.
export const revalidate = 3600;

/**
 * robots.txt (SEO-5). Previously 404 — nothing declared the sitemap, and
 * nothing told a crawler which paths were pointless to fetch.
 *
 * `/admin` is already 401 and carries `robots: noindex`, and `/api` is a JSON
 * BFF surface. Neither should be indexed; disallowing them saves crawl budget
 * that is better spent on the feed. Note this is a crawl directive, not a
 * security control — the 401 is what actually protects admin.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/admin', '/api/'],
      },
    ],
    sitemap: absoluteUrl('/sitemap.xml'),
    host: absoluteUrl('/'),
  };
}
