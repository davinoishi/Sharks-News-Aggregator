import { INTERNAL_API_URL } from '../api/config';
import {
  EntitiesResponse,
  FeedResponse,
  PublicSource,
  SiteStats,
  SourcesResponse,
} from '../types';

/**
 * Server-side reads of the backend, for rendering the feed in the HTML (SEO-1).
 *
 * **Server components only.** This reads `INTERNAL_API_URL`, which names a host
 * only reachable from inside the docker network; importing it from a `'use
 * client'` module would ship a URL the browser cannot reach and quietly break
 * the page. The usual guard is the `server-only` package, deliberately not
 * added here to avoid a `package.json` bump for a one-line shim — so this
 * comment is the guard. Client code goes through `ApiClient` and the `/api/*`
 * routes.
 *
 * These go **straight to `INTERNAL_API_URL`** over the docker network, not
 * through this app's own `/api/*` route handlers. A server component fetching
 * its own routes would need an absolute public URL, take a pointless second
 * network hop through the tunnel, and break during `next build` when no server
 * is listening yet. The BFF routes still exist and still serve the browser —
 * that is what they are for.
 *
 * Every read is wrapped so a backend hiccup degrades instead of 500-ing the
 * page: the shell still renders and the client retries on mount. The Pi is a
 * single box behind a tunnel, so "the API is briefly unreachable" is a normal
 * condition, not an exceptional one.
 */

// Matches the ingest cadence (INGEST_INTERVAL_MINUTES=10), so the page is never
// more than half a cycle stale, and matches web/app/rss/route.ts.
export const FEED_REVALIDATE_SECONDS = 300;

// Outlets change when a source is added or disabled — hourly is plenty.
const SOURCES_REVALIDATE_SECONDS = 3600;

async function getJson<T>(
  path: string,
  revalidate: number,
  label: string
): Promise<T | null> {
  try {
    const response = await fetch(`${INTERNAL_API_URL}${path}`, {
      headers: { Accept: 'application/json' },
      next: { revalidate },
    });
    if (!response.ok) {
      console.error(`Server fetch ${label} failed: ${response.status}`);
      return null;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`Server fetch ${label} threw:`, error);
    return null;
  }
}

/** Initial feed page. `since` should match the UI's default window. */
export async function fetchInitialFeed(
  since: string,
  limit = 50
): Promise<FeedResponse | null> {
  return getJson<FeedResponse>(
    `/feed?since=${encodeURIComponent(since)}&limit=${limit}`,
    FEED_REVALIDATE_SECONDS,
    '/feed'
  );
}

/**
 * Players and coaches ranked by how many stories currently mention them.
 *
 * Scoped to the same window as the feed so the chips describe what is actually
 * on screen. Alphabetical (the endpoint's default) would be useless here — see
 * `get_entities_by_prominence` in the API.
 */
export async function fetchProminentEntities(
  since: string,
  limit = 18
): Promise<EntitiesResponse['entities']> {
  const data = await getJson<EntitiesResponse>(
    `/entities?order_by=cluster_count&since=${encodeURIComponent(since)}&limit=${limit}`,
    FEED_REVALIDATE_SECONDS,
    '/entities'
  );
  return data?.entities ?? [];
}

/** Feed for one topic page, filtered by a single tag or entity slug. */
export async function fetchTopicFeed(
  filter: 'tags' | 'entities',
  slug: string,
  since: string,
  limit = 50
): Promise<FeedResponse | null> {
  return getJson<FeedResponse>(
    `/feed?${filter}=${encodeURIComponent(slug)}&since=${encodeURIComponent(since)}&limit=${limit}`,
    FEED_REVALIDATE_SECONDS,
    `/feed (${filter}=${slug})`
  );
}

/**
 * Whether a topic has at least `threshold` clusters in the window.
 *
 * Asks for exactly `threshold` items and checks whether that many came back,
 * rather than pulling a full page to count them. The sitemap runs this for
 * every topic, so the difference is nine small responses instead of nine
 * hundred-item ones on a Raspberry Pi.
 */
export async function topicHasEnoughClusters(
  filter: 'tags' | 'entities',
  slug: string,
  since: string,
  threshold: number
): Promise<boolean> {
  const data = await fetchTopicFeed(filter, slug, since, threshold);
  return (data?.clusters.length ?? 0) >= threshold;
}

export async function fetchPublicSources(): Promise<PublicSource[]> {
  const data = await getJson<SourcesResponse>(
    '/sources',
    SOURCES_REVALIDATE_SECONDS,
    '/sources'
  );
  return data?.sources ?? [];
}

export async function fetchSiteStats(): Promise<SiteStats | null> {
  return getJson<SiteStats>('/stats', FEED_REVALIDATE_SECONDS, '/stats');
}

export async function fetchLastScanAt(): Promise<string | null> {
  const data = await getJson<{ last_scan_at?: string | null }>(
    '/health',
    FEED_REVALIDATE_SECONDS,
    '/health'
  );
  return data?.last_scan_at ?? null;
}
