'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiClient } from '../api-client';
import { Cluster, Entity } from '../types';
import { ClusterCard } from './ClusterCard';
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

function writeFiltersToUrl(filters: Filters) {
  if (typeof window === 'undefined') return;
  const p = new URLSearchParams();
  if (filters.tags.length) p.set('tags', filters.tags.join(','));
  if (filters.since && filters.since !== DEFAULT_SINCE) p.set('since', filters.since);
  if (filters.entity) p.set('entities', filters.entity.slug);
  const qs = p.toString();
  window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
}

function filtersMatchDefault(filters: Filters): boolean {
  return (
    filters.tags.length === 0 &&
    filters.since === DEFAULT_SINCE &&
    filters.entity === null
  );
}

function SkeletonCard() {
  return (
    // Block heights track the real type roles: two headline lines at the
    // headline role's line box, then chip and meta rows.
    <div className="border border-edge rounded-lg p-4 bg-surface animate-pulse">
      <div className="h-[23px] bg-surface-sunken rounded-md w-full mb-1" />
      <div className="h-[23px] bg-surface-sunken rounded-md w-2/3 mb-3" />
      <div className="flex gap-2 mb-3">
        <div className="h-[21px] w-16 bg-surface-sunken rounded-md" />
        <div className="h-[21px] w-12 bg-surface-sunken rounded-md" />
      </div>
      <div className="h-[19px] bg-surface-sunken rounded-md w-1/3" />
    </div>
  );
}

/**
 * Interactive half of the feed.
 *
 * The page shell and the first page of stories are rendered on the server; this
 * component adopts them as its initial state and takes over from there. The
 * critical consequence is that it must NOT refetch on mount when the filters
 * still match the server's — doing so would throw away perfectly good markup,
 * flash a skeleton, and put a request on the Pi for every visitor.
 */
export function FeedList({
  initialClusters,
  initialCursor,
  initialHasMore,
  initialFetchFailed,
  suggestedEntities,
}: FeedListProps) {
  const [clusters, setClusters] = useState<Cluster[]>(initialClusters);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [refetching, setRefetching] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedClusterId, setExpandedClusterId] = useState<number | null>(null);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);

  const cursorRef = useRef<string | null>(initialCursor);
  // The server already fetched the default view. Skip the first filter-effect
  // run unless the URL asked for something else, or the server fetch failed.
  const hydratedRef = useRef(false);

  // Restore filters from the URL so shared/bookmarked links open filtered.
  useEffect(() => {
    const fromUrl = readFiltersFromUrl();
    if (!filtersMatchDefault(fromUrl)) setFilters(fromUrl);
  }, []);

  // Beacon stays client-side on purpose: the page is ISR-cached, so a
  // server-side count would record one view per revalidate window, not one per
  // reader.
  useEffect(() => {
    ApiClient.recordPageview();
  }, []);

  const fetchPage = useCallback(
    async (reset: boolean) => {
      setError(null);
      if (reset) setRefetching(true);
      else setLoadingMore(true);
      try {
        const response = await ApiClient.getFeed({
          tags: filters.tags.join(',') || undefined,
          entities: filters.entity?.slug,
          since: filters.since,
          limit: 50,
          cursor: reset ? undefined : cursorRef.current ?? undefined,
        });
        setClusters((prev) =>
          reset ? response.clusters : [...prev, ...response.clusters]
        );
        cursorRef.current = response.cursor ?? null;
        setHasMore(response.has_more);
      } catch (err) {
        console.error('Error loading feed:', err);
        setError("We couldn't load the latest news. Please try again.");
      } finally {
        setRefetching(false);
        setLoadingMore(false);
      }
    },
    [filters]
  );

  // Refetch whenever a filter changes; mirror to the URL. The first run is
  // skipped when the server already rendered exactly this view.
  useEffect(() => {
    if (!hydratedRef.current) {
      hydratedRef.current = true;
      if (filtersMatchDefault(filters) && !initialFetchFailed) return;
    }
    writeFiltersToUrl(filters);
    cursorRef.current = null;
    fetchPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.tags.join(','), filters.since, filters.entity?.slug]);

  // Upgrade a URL-derived entity label (a de-slugified guess) to the real name
  // once it shows up in results.
  useEffect(() => {
    if (!filters.entity) return;
    for (const c of clusters) {
      const match = c.entities.find((e) => e.slug === filters.entity!.slug);
      if (match && match.name !== filters.entity.name) {
        setFilters((f) =>
          f.entity ? { ...f, entity: { slug: f.entity.slug, name: match.name } } : f
        );
        break;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clusters]);

  const handleExpandCluster = async (clusterId: number) => {
    if (expandedClusterId === clusterId) {
      setExpandedClusterId(null);
      return;
    }
    try {
      const response = await ApiClient.getCluster(clusterId);
      setClusters((prev) =>
        prev.map((c) => (c.id === clusterId ? { ...c, variants: response.variants } : c))
      );
      setExpandedClusterId(clusterId);
    } catch (err) {
      console.error('Error loading cluster details:', err);
    }
  };

  const handleEntityClick = (entity: Entity) => {
    setFilters((f) => ({ ...f, entity: { slug: entity.slug, name: entity.name } }));
  };

  const filtersActive = hasActiveFilters(filters);
  const showSkeletons = refetching && clusters.length === 0;
  const showEmpty = !refetching && !error && clusters.length === 0;

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

      {showSkeletons && (
        <div className="space-y-4" aria-busy="true" aria-label="Loading news">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {error && (
        <div className="bg-critical border border-critical-edge rounded-lg p-4 mb-6">
          <p className="text-body text-critical-fg">{error}</p>
          <button
            onClick={() => fetchPage(true)}
            className="tap-44 mt-2 inline-flex items-center text-ui text-critical-fg underline hover:no-underline"
          >
            Try again
          </button>
        </div>
      )}

      {showEmpty && (
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
      )}

      {clusters.length > 0 && (
        <>
          <div
            className="mb-4 text-meta text-content-muted tabular-nums"
            role="status"
            aria-live="polite"
          >
            Showing {clusters.length} {clusters.length === 1 ? 'story' : 'stories'}
          </div>

          <div
            className={`space-y-4 transition-opacity ${
              refetching ? 'opacity-50 pointer-events-none' : ''
            }`}
          >
            {clusters.map((cluster) => (
              <ClusterCard
                key={cluster.id}
                cluster={cluster}
                onExpand={handleExpandCluster}
                isExpanded={expandedClusterId === cluster.id}
                onEntityClick={handleEntityClick}
                activeEntitySlug={filters.entity?.slug ?? null}
              />
            ))}
          </div>

          {hasMore && (
            <div className="mt-6 text-center">
              <button
                onClick={() => fetchPage(false)}
                disabled={loadingMore}
                className="tap-44 inline-flex items-center px-5 py-2.5 rounded-md bg-action text-on-action text-ui hover:bg-action-hover disabled:bg-control disabled:text-content-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
