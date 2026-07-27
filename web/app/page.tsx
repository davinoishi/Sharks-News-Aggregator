'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { ApiClient } from './api-client';
import { Cluster, Entity, SiteStats } from './types';
import { ClusterCard } from './components/ClusterCard';
import { FilterBar } from './components/FilterBar';
import { DEFAULT_FILTERS, DEFAULT_SINCE, Filters, hasActiveFilters } from './lib/filters';

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

export default function Home() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [firstLoad, setFirstLoad] = useState(true);
  const [refetching, setRefetching] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedClusterId, setExpandedClusterId] = useState<number | null>(null);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);
  const [siteStats, setSiteStats] = useState<SiteStats | null>(null);

  const cursorRef = useRef<string | null>(null);

  // Initialise filters from the URL on the client (so shared/bookmarked links
  // restore the filtered view).
  useEffect(() => {
    setFilters(readFiltersFromUrl());
  }, []);

  // Record page view once on initial load.
  useEffect(() => {
    ApiClient.recordPageview();
    loadStats();
    loadHealth();
  }, []);

  const loadStats = async () => {
    try {
      setSiteStats(await ApiClient.getStats());
    } catch (err) {
      console.error('Error loading stats:', err);
    }
  };

  const loadHealth = async () => {
    try {
      const health = await ApiClient.getHealth();
      setLastScanAt(health.last_scan_at || null);
    } catch (err) {
      console.error('Error loading health:', err);
    }
  };

  const formatLastScanTime = (timestamp: string | null) => {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp);
    const diffMins = Math.floor((Date.now() - date.getTime()) / 60000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
  };

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
        const next = response.cursor ?? null;
        cursorRef.current = next;
        setCursor(next);
        setHasMore(response.has_more);
      } catch (err) {
        console.error('Error loading feed:', err);
        setError("We couldn't load the latest news. Please try again.");
      } finally {
        setRefetching(false);
        setLoadingMore(false);
        setFirstLoad(false);
      }
    },
    [filters]
  );

  // Reload (and reset pagination) whenever a filter changes; mirror to the URL.
  useEffect(() => {
    writeFiltersToUrl(filters);
    cursorRef.current = null;
    setCursor(null);
    fetchPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.tags.join(','), filters.since, filters.entity?.slug]);

  // Once a feed page loads, upgrade a URL-derived entity label (a de-slugified
  // guess) to the real entity name when it appears in the results.
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
  const showSkeletons = firstLoad && refetching && clusters.length === 0;
  const showEmpty =
    !firstLoad && !refetching && !error && clusters.length === 0;

  return (
    <main className="min-h-screen bg-canvas">
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        {/* Header */}
        <header className="mb-8">
          <div className="flex items-center gap-3 sm:gap-4 mb-2">
            {/* The crest sits directly beside the site name, so announcing it
                would just repeat the h1. */}
            <Image
              src="/logo.png"
              alt=""
              width={64}
              height={64}
              className="object-contain w-12 h-12 sm:w-16 sm:h-16 flex-shrink-0"
            />
            <div>
              <h1 className="font-display text-masthead uppercase text-content">
                Sharks News Aggregator
              </h1>
              {lastScanAt && (
                <p className="text-meta text-content-muted mt-1 tabular-nums">
                  Last scan: {formatLastScanTime(lastScanAt)}
                </p>
              )}
            </div>
          </div>
          <p className="text-body text-content-secondary mt-3 max-w-[62ch]">
            Built by a Sharks fan for Sharks fans. Consolidates Sharks news into one place. It is missing news from popular X(Twitter) feeds because the X API costs $ to access. This feed is also published to{' '}
            <a
              href="https://bsky.app/profile/sjsharks-news.bsky.social"
              target="_blank"
              rel="noopener noreferrer"
              className="text-action hover:underline"
            >
              BlueSky
              <span className="sr-only"> (opens in a new tab)</span>
            </a>{' '}
            and as{' '}
            <a href="/rss" className="text-action hover:underline">
              RSS
            </a>
            .
          </p>
        </header>

        {/* Filters */}
        <FilterBar
          selectedTags={filters.tags}
          since={filters.since}
          entity={filters.entity}
          onTagsChange={(tags) => setFilters((f) => ({ ...f, tags }))}
          onSinceChange={(since) => setFilters((f) => ({ ...f, since }))}
          onEntityChange={(entity) => setFilters((f) => ({ ...f, entity }))}
        />

        {/* Skeletons on first load */}
        {showSkeletons && (
          <div className="space-y-4" aria-busy="true" aria-label="Loading news">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Error State */}
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

        {/* Empty State */}
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

        {/* Feed */}
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

        {/* Footer */}
        <footer className="mt-12 pt-8 border-t border-edge text-center text-meta text-content-muted">
          {siteStats && (
            <p className="mb-3 tabular-nums">
              {siteStats.page_views.toLocaleString()} visits · {siteStats.total_stories.toLocaleString()} stories tracked · {siteStats.total_sources} sources
            </p>
          )}
          {/* A real navigation landmark, and each link gets its own tappable
              row height instead of being a 21px sliver of a sentence. */}
          <nav aria-label="Site links" className="mb-2">
            <ul className="flex flex-wrap justify-center items-center gap-x-3 gap-y-2.5">
              <li>
                <a
                  href="https://puckpedia.com/team/san-jose-sharks"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline"
                >
                  PuckPedia Salary Cap
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
              </li>
              <li>
                <a
                  href="https://capwages.com/teams/san_jose_sharks"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline"
                >
                  CapWages
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
              </li>
              <li>
                <a href="/rss" className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline">
                  RSS
                </a>
              </li>
              <li>
                <Link href="/about" className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline">
                  About
                </Link>
              </li>
              <li>
                <Link href="/legal" className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline">
                  Legal
                </Link>
              </li>
              <li>
                <Link href="/submit" className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline">
                  Submit a link
                </Link>
              </li>
            </ul>
          </nav>
          <p className="mb-2">
            Powered by RSS feeds from official sources and trusted media outlets.
          </p>
          <p className="max-w-[60ch] mx-auto">
            Sharks News Aggregator is an independent, unofficial project. Not affiliated with the
            NHL or the San Jose Sharks.
          </p>
        </footer>
      </div>
    </main>
  );
}
