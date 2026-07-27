import type { MetadataRoute } from 'next';
import { absoluteUrl } from './lib/site';
import { fetchLastScanAt, topicHasEnoughClusters } from './lib/server-api';
import {
  PLAYER_TOPICS,
  SITEMAP_MIN_CLUSTERS,
  TAG_TOPICS,
  TOPIC_SINCE,
  Topic,
} from './lib/topics';

/**
 * Rendered per request; the underlying fetches are cached for 300s.
 *
 * `revalidate` alone was enough while the sitemap was four static URLs and the
 * only live value was a `lastmod` — a slightly stale timestamp on the first
 * request after a deploy is harmless. It stopped being enough once entries
 * became conditional on live cluster counts (TAG-5): the build-time prerender
 * runs with no reachable API, so every topic gated on a count was silently
 * omitted, and the sitemap served for the first five minutes after each deploy
 * advertised four URLs instead of ten.
 *
 * Same reasoning, and the same pair of flags, as the feed and topic pages.
 * Crawlers fetch this rarely and `fetchCache` keeps the nine count probes on
 * the 300s cache, so per-request rendering costs effectively nothing.
 */
export const dynamic = 'force-dynamic';
export const fetchCache = 'default-cache';

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

/**
 * Topic entries, included only when the topic has enough recent coverage.
 *
 * The page always exists and stays linked from "Browse by topic" — this only
 * decides whether it is *advertised* for crawling. Gating on a live count
 * rather than a hardcoded skip list matters because Waiver, Injury and Lineup
 * are thin in July and are exactly the tags that fill up from October; a static
 * exclusion would be wrong by opening night.
 */
async function topicEntries(
  filter: 'tags' | 'entities',
  basePath: string,
  topics: Topic[],
  lastModified: Date
): Promise<MetadataRoute.Sitemap> {
  const included = await Promise.all(
    topics.map(async (topic) => ({
      topic,
      enough: await topicHasEnoughClusters(
        filter,
        topic.slug,
        TOPIC_SINCE,
        SITEMAP_MIN_CLUSTERS
      ),
    }))
  );

  return included
    .filter((entry) => entry.enough)
    .map((entry) => ({
      url: absoluteUrl(`${basePath}/${entry.topic.slug}`),
      lastModified,
      changeFrequency: 'daily' as const,
      priority: 0.8,
    }));
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const lastScanAt = await fetchLastScanAt();
  const feedLastModified = lastScanAt ? new Date(lastScanAt) : new Date();

  const [tagEntries, playerEntries] = await Promise.all([
    topicEntries('tags', '/tag', TAG_TOPICS, feedLastModified),
    topicEntries('entities', '/player', PLAYER_TOPICS, feedLastModified),
  ]);

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
    ...tagEntries,
    ...playerEntries,
  ];
}
