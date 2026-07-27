'use client';

import { ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiClient } from '../api-client';
import { Cluster, Entity } from '../types';
import { ClusterCard } from './ClusterCard';

/** The fixed query a list renders. Changing it triggers a refetch. */
export interface FeedQuery {
  tags?: string;
  entities?: string;
  since: string;
}

interface ClusterListProps {
  /** Clusters rendered on the server, adopted as initial state. */
  initialClusters: Cluster[];
  initialCursor: string | null;
  initialHasMore: boolean;
  /** True when the server-side fetch failed; the client retries on mount. */
  initialFetchFailed?: boolean;
  query: FeedQuery;
  /** Shown when there are no stories. Callers word this for their context. */
  emptyState?: ReactNode;
  /** Lets a parent react to loaded data without owning the fetch. */
  onClustersChange?: (clusters: Cluster[]) => void;
  onEntityClick?: (entity: Entity) => void;
  /**
   * Send entity chips to the feed filtered by that entity, instead of handling
   * them locally. Topic pages have no filter state of their own, so without
   * this the chips would render as buttons that look interactive and do
   * nothing.
   */
  navigateEntitiesToFeed?: boolean;
  activeEntitySlug?: string | null;
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

function queryKey(query: FeedQuery): string {
  return `${query.tags ?? ''}|${query.entities ?? ''}|${query.since}`;
}

/**
 * A server-rendered list of clusters that keeps paginating on the client.
 *
 * Extracted from `FeedList` so the feed, the tag pages and the player page share
 * one implementation of list rendering, expansion and "Load more" — three copies
 * of pagination logic is how they drift apart.
 *
 * The important behaviour: this component **adopts** the server's markup rather
 * than refetching on mount. Refetching would discard perfectly good HTML, flash
 * a skeleton, and put a request on the Pi for every visitor. It only fetches
 * when the query actually changes, or when the server fetch failed.
 */
export function ClusterList({
  initialClusters,
  initialCursor,
  initialHasMore,
  initialFetchFailed = false,
  query,
  emptyState,
  onClustersChange,
  onEntityClick,
  navigateEntitiesToFeed = false,
  activeEntitySlug = null,
}: ClusterListProps) {
  const router = useRouter();
  const [clusters, setClusters] = useState<Cluster[]>(initialClusters);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [refetching, setRefetching] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedClusterId, setExpandedClusterId] = useState<number | null>(null);

  const cursorRef = useRef<string | null>(initialCursor);
  // The query the server already rendered. The effect below skips its first run
  // unless something actually differs from it.
  const renderedKeyRef = useRef<string>(queryKey(query));
  const hydratedRef = useRef(false);

  const fetchPage = useCallback(
    async (reset: boolean) => {
      setError(null);
      if (reset) setRefetching(true);
      else setLoadingMore(true);
      try {
        const response = await ApiClient.getFeed({
          tags: query.tags || undefined,
          entities: query.entities || undefined,
          since: query.since,
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
    [query.tags, query.entities, query.since]
  );

  const key = queryKey(query);

  useEffect(() => {
    if (!hydratedRef.current) {
      hydratedRef.current = true;
      // Server already rendered exactly this query — keep its markup.
      if (key === renderedKeyRef.current && !initialFetchFailed) return;
    }
    cursorRef.current = null;
    fetchPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    onClustersChange?.(clusters);
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

  const showSkeletons = refetching && clusters.length === 0;
  const showEmpty = !refetching && !error && clusters.length === 0;

  return (
    <>
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

      {showEmpty && emptyState}

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
                onEntityClick={
                  navigateEntitiesToFeed
                    ? (entity) =>
                        router.push(`/?entities=${encodeURIComponent(entity.slug)}`)
                    : onEntityClick
                }
                activeEntitySlug={activeEntitySlug}
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
