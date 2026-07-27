import type { MetadataRoute } from 'next';
import { absoluteUrl } from './lib/site';
import { fetchLastScanAt } from './lib/server-api';

// Matches the feed's cache window — the only entry that moves is `/`, and it
// moves at ingest cadence.
export const revalidate = 300;

/**
 * sitemap.xml (SEO-5). Previously 404, so only the homepage was ever indexed;
 * /about, /legal and /submit were reachable solely through footer links.
 *
 * `/` carries a real `lastModified` taken from the last successful ingest,
 * which is the honest answer to "when did this page change" for a feed. The
 * static pages use their own content dates rather than `new Date()` — a
 * sitemap that claims every page changed on every request is noise, and
 * crawlers discount it.
 */

// Bumped when the copy on these pages actually changes.
const ABOUT_LAST_MODIFIED = new Date('2026-07-27');
const LEGAL_LAST_MODIFIED = new Date('2026-07-27'); // "Last updated" on /legal
const SUBMIT_LAST_MODIFIED = new Date('2026-07-27');

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const lastScanAt = await fetchLastScanAt();
  const feedLastModified = lastScanAt ? new Date(lastScanAt) : new Date();

  return [
    {
      url: absoluteUrl('/'),
      lastModified: feedLastModified,
      changeFrequency: 'hourly',
      priority: 1,
    },
    {
      url: absoluteUrl('/about'),
      lastModified: ABOUT_LAST_MODIFIED,
      changeFrequency: 'yearly',
      priority: 0.5,
    },
    {
      url: absoluteUrl('/legal'),
      lastModified: LEGAL_LAST_MODIFIED,
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: absoluteUrl('/submit'),
      lastModified: SUBMIT_LAST_MODIFIED,
      changeFrequency: 'yearly',
      priority: 0.4,
    },
  ];
}
