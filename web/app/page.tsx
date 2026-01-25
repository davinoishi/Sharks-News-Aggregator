'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { ApiClient } from './api-client';
import { Cluster } from './types';
import { ClusterCard } from './components/ClusterCard';
import { FilterBar } from './components/FilterBar';

export default function Home() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedClusterId, setExpandedClusterId] = useState<number | null>(null);
  const [filters, setFilters] = useState<{ tags?: string; since?: string }>({ since: '24h' });
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);

  useEffect(() => {
    loadFeed();
    loadHealth();
  }, [filters]);

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
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
  };

  const loadFeed = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await ApiClient.getFeed({ ...filters, limit: 50 });
      setClusters(response.clusters);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load feed');
      console.error('Error loading feed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleExpandCluster = async (clusterId: number) => {
    if (expandedClusterId === clusterId) {
      setExpandedClusterId(null);
      return;
    }

    try {
      const response = await ApiClient.getCluster(clusterId);

      // Update the cluster with variants
      setClusters((prev) =>
        prev.map((c) =>
          c.id === clusterId ? { ...c, variants: response.variants } : c
        )
      );

      setExpandedClusterId(clusterId);
    } catch (err) {
      console.error('Error loading cluster details:', err);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-4 mb-2">
            <Image
              src="/logo.png"
              alt="San Jose Sharks Logo"
              width={64}
              height={64}
              className="object-contain"
            />
            <div>
              <h1 className="text-4xl font-bold text-gray-900">
                Sharks News Aggregator
              </h1>
              {lastScanAt && (
                <p className="text-sm text-gray-500 mt-1">
                  Last scan: {formatLastScanTime(lastScanAt)}
                </p>
              )}
            </div>
          </div>
          <p className="text-gray-600 ml-20">
            One story per event. All the Sharks news, none of the duplicates.
          </p>
        </div>

        {/* Filters */}
        <FilterBar onFilterChange={setFilters} />

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="mt-4 text-gray-600">Loading news...</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800">
              <strong>Error:</strong> {error}
            </p>
            <button
              onClick={loadFeed}
              className="mt-2 text-sm text-red-600 hover:text-red-700 underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && clusters.length === 0 && (
          <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
            <p className="text-gray-600 mb-2">No news items found.</p>
            <p className="text-sm text-gray-500">
              Try adjusting your filters or check back later.
            </p>
          </div>
        )}

        {/* Feed */}
        {!loading && !error && clusters.length > 0 && (
          <>
            <div className="mb-4 text-sm text-gray-600">
              Showing {clusters.length} {clusters.length === 1 ? 'story' : 'stories'}
            </div>

            <div className="space-y-4">
              {clusters.map((cluster) => (
                <ClusterCard
                  key={cluster.id}
                  cluster={cluster}
                  onExpand={handleExpandCluster}
                  isExpanded={expandedClusterId === cluster.id}
                />
              ))}
            </div>
          </>
        )}

        {/* Footer */}
        <div className="mt-12 pt-8 border-t border-gray-200 text-center text-sm text-gray-500">
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
            <Link href="/about" className="text-blue-600 hover:underline">
              About
            </Link>
            {' | '}
            <Link href="/legal" className="text-blue-600 hover:underline">
              Legal
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
