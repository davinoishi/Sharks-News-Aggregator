'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { ApiClient } from './api-client';
import { Cluster, Entity, SiteStats } from './types';
import { ClusterCard } from './components/ClusterCard';
import { ActiveEntity, FilterBar } from './components/FilterBar';

interface Filters {
  tags: string[];
  since: string;
  entity: ActiveEntity | null;
}

const DEFAULT_FILTERS: Filters = { tags: [], since: '24h', entity: null };

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
  const since = p.get('since') || '24h';
  const entSlug = p.get('entities');
  const entity = entSlug ? { slug: entSlug, name: deslugify(entSlug) } : null;
  return { tags, since, entity };
}

function writeFiltersToUrl(filters: Filters) {
  if (typeof window === 'undefined') return;
  const p = new URLSearchParams();
  if (filters.tags.length) p.set('tags', filters.tags.join(','));
  if (filters.since && filters.since !== '24h') p.set('since', filters.since);
  if (filters.entity) p.set('entities', filters.entity.slug);
  const qs = p.toString();
  window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
}

function SkeletonCard() {
  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-white animate-pulse">
      <div className="h-5 bg-gray-200 rounded w-3/4 mb-3" />
      <div className="flex gap-2 mb-3">
        <div className="h-5 w-16 bg-gray-200 rounded" />
        <div className="h-5 w-12 bg-gray-200 rounded" />
      </div>
      <div className="h-4 bg-gray-200 rounded w-1/3" />
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

  const showSkeletons = firstLoad && refetching && clusters.length === 0;
  const showEmpty =
    !firstLoad && !refetching && !error && clusters.length === 0;

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 sm:gap-4 mb-2">
            <Image
              src="/logo.png"
              alt="Sharks News Logo"
              width={64}
              height={64}
              className="object-contain w-12 h-12 sm:w-16 sm:h-16 flex-shrink-0"
            />
            <div>
              <h1 className="text-2xl sm:text-4xl font-bold text-gray-900">
                Sharks News Aggregator
              </h1>
              {lastScanAt && (
                <p className="text-sm text-gray-500 mt-1">
                  Last scan: {formatLastScanTime(lastScanAt)}
                </p>
              )}
            </div>
          </div>
          <p className="text-gray-600 mt-3">
            Built by a Sharks fan for Sharks fans. Consolidates Sharks news into one place. It is missing news from popular X(Twitter) feeds because the X API costs $ to access. This feed is also published to{' '}
            <a
              href="https://bsky.app/profile/sjsharks-news.bsky.social"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              BlueSky
            </a>{' '}
            and as{' '}
            <a href="/rss" className="text-blue-600 hover:underline">
              RSS
            </a>
            .
          </p>
        </div>

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
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800">{error}</p>
            <button
              onClick={() => fetchPage(true)}
              className="mt-2 text-sm font-medium text-red-700 hover:text-red-800 underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Empty State */}
        {showEmpty && (
          <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
            <p className="text-gray-600 mb-2">No news items found.</p>
            <p className="text-sm text-gray-500">
              Try adjusting your filters or check back later.
            </p>
          </div>
        )}

        {/* Feed */}
        {clusters.length > 0 && (
          <>
            <div className="mb-4 text-sm text-gray-600">
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
                  className="px-5 py-2 rounded-lg bg-[#006D75] text-white text-sm font-medium hover:bg-[#005a61] disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#006D75] focus-visible:ring-offset-2"
                >
                  {loadingMore ? 'Loading…' : 'Load more'}
                </button>
              </div>
            )}
          </>
        )}

        {/* Footer */}
        <div className="mt-12 pt-8 border-t border-gray-200 text-center text-sm text-gray-500">
          {siteStats && (
            <p className="mb-3 text-xs text-gray-400">
              {siteStats.page_views.toLocaleString()} visits · {siteStats.total_stories.toLocaleString()} stories tracked · {siteStats.total_sources} sources
            </p>
          )}
          <p className="mb-2">
            <a
              href="https://puckpedia.com/team/san-jose-sharks"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              PuckPedia Salary Cap
            </a>
            {' | '}
            <a
              href="https://capwages.com/teams/san_jose_sharks"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              CapWages
            </a>
            {' | '}
            <a href="/rss" className="text-blue-600 hover:underline">
              RSS
            </a>
            {' | '}
            <Link href="/about" className="text-blue-600 hover:underline">
              About
            </Link>
            {' | '}
            <Link href="/legal" className="text-blue-600 hover:underline">
              Legal
            </Link>
            {' | '}
            <Link href="/submit" className="text-blue-600 hover:underline">
              Submit a link
            </Link>
          </p>
          <p className="mb-2">
            Powered by RSS feeds from official sources and trusted media outlets.
          </p>
          <p className="text-xs text-gray-400">
            Sharks News Aggregator is an independent, unofficial project. Not affiliated with the
            NHL or the San Jose Sharks.
          </p>
        </div>
      </div>
    </main>
  );
}
