'use client';

import { useCallback, useEffect, useState } from 'react';
import { ApiClient } from '../api-client';
import { Cluster, Entity } from '../types';
import { ClusterList, FeedQuery } from './ClusterList';
import { FilterBar } from './FilterBar';
import { DEFAULT_FILTERS, DEFAULT_SINCE, Filters, hasActiveFilters } from '../lib/filters';

interface FeedListProps {
  /** Clusters rendered on the server for the default window (SEO-1). */
  initialClusters: Cluster[];
  initialCursor: string | null;
  initialHasMore: boolean;
  /** True when the server-side fetch failed; the client retries on mount. */
  initialFetchFailed: boolean;
  /** Prominent entities, server-rendered as filter chips (SEO-2). */
  suggestedEntities: Entity[];
}

function deslugify(slug: string): string {
  return slug
    .split('-')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function readFiltersFromUrl(): Filters {
  if (typeof window === 'undefined') return DEFAULT_FILTERS;
  const p = new URLSearchParams(window.location.search);
  const tags = p.get('tags')?.split(',').filter(Boolean) ?? [];
  const since = p.get('since') || DEFAULT_SINCE;
  const entSlug = p.get('entities');
  const entity = entSlug ? { slug: entSlug, name: deslugify(entSlug) } : null;
  return { tags, since, entity };
}

/**
 * Mirror filter state into the URL without a navigation.
 *
 * **`history.state` must be preserved.** Passing `null` — which this did — wipes
 * the App Router's own routing state (`__NA`,
 * `__PRIVATE_NEXTJS_INTERNALS_TREE`) for the current history entry. Next reads
 * that on `popstate` to rebuild the route tree, so with it gone the Back button
 * changed the URL and left the previous page's DOM on screen: going
 * home → /tag/rumors → Back showed the URL `/` with the Rumors heading, count
 * and stories still rendered.
 *
 * `router.replace()` would also be correct but costs a server round-trip on a
 * `force-dynamic` page every time a filter chip is tapped, which is exactly why
 * this uses the raw history API.
 */
function writeFiltersToUrl(filters: Filters) {
  if (typeof window === 'undefined') return;
  const p = new URLSearchParams();
  if (filters.tags.length) p.set('tags', filters.tags.join(','));
  if (filters.since && filters.since !== DEFAULT_SINCE) p.set('since', filters.since);
  if (filters.entity) p.set('entities', filters.entity.slug);
  const qs = p.toString();
  window.history.replaceState(
    window.history.state,
    '',
    qs ? `?${qs}` : window.location.pathname
  );
}

function filtersMatchDefault(filters: Filters): boolean {
  return (
    filters.tags.length === 0 &&
    filters.since === DEFAULT_SINCE &&
    filters.entity === null
  );
}

/**
 * The feed's filter layer.
 *
 * Owns filter state and URL syncing; `ClusterList` owns everything about
 * rendering and paginating the results, and is shared with the tag and player
 * pages.
 */
export function FeedList({
  initialClusters,
  initialCursor,
  initialHasMore,
  initialFetchFailed,
  suggestedEntities,
}: FeedListProps) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);

  // Restore filters from the URL so shared/bookmarked links open filtered.
  useEffect(() => {
    const fromUrl = readFiltersFromUrl();
    if (!filtersMatchDefault(fromUrl)) setFilters(fromUrl);
  }, []);

  // Beacon stays client-side on purpose: the page is cached, so a server-side
  // count would record one view per cache window, not one per reader.
  useEffect(() => {
    ApiClient.recordPageview();
  }, []);

  useEffect(() => {
    writeFiltersToUrl(filters);
  }, [filters]);

  // Upgrade a URL-derived entity label (a de-slugified guess) to the real name
  // once it shows up in results.
  const handleClustersChange = useCallback(
    (clusters: Cluster[]) => {
      setFilters((current) => {
        if (!current.entity) return current;
        for (const c of clusters) {
          const match = c.entities.find((e) => e.slug === current.entity!.slug);
          if (match && match.name !== current.entity.name) {
            return { ...current, entity: { slug: current.entity.slug, name: match.name } };
          }
        }
        return current;
      });
    },
    []
  );

  const query: FeedQuery = {
    tags: filters.tags.join(',') || undefined,
    entities: filters.entity?.slug,
    since: filters.since,
  };

  const filtersActive = hasActiveFilters(filters);

  return (
    <>
      <FilterBar
        selectedTags={filters.tags}
        since={filters.since}
        entity={filters.entity}
        suggestedEntities={suggestedEntities}
        onTagsChange={(tags) => setFilters((f) => ({ ...f, tags }))}
        onSinceChange={(since) => setFilters((f) => ({ ...f, since }))}
        onEntityChange={(entity) => setFilters((f) => ({ ...f, entity }))}
      />

      <ClusterList
        initialClusters={initialClusters}
        initialCursor={initialCursor}
        initialHasMore={initialHasMore}
        initialFetchFailed={initialFetchFailed}
        query={query}
        onClustersChange={handleClustersChange}
        onEntityClick={(entity) =>
          setFilters((f) => ({ ...f, entity: { slug: entity.slug, name: entity.name } }))
        }
        activeEntitySlug={filters.entity?.slug ?? null}
        emptyState={
          <div className="bg-surface border border-edge rounded-lg p-8 text-center">
            <p className="text-body text-content-secondary mb-1">No news items found.</p>
            <p className="text-meta text-content-muted">
              {filtersActive
                ? 'No stories match these filters.'
                : 'Nothing new in this window — check back later.'}
            </p>
            {filtersActive && (
              <button
                onClick={() => setFilters(DEFAULT_FILTERS)}
                className="tap-44 mt-4 inline-flex items-center px-4 py-2 rounded-md bg-action text-on-action text-ui hover:bg-action-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
              >
                Clear all filters
              </button>
            )}
          </div>
        }
      />
    </>
  );
}
