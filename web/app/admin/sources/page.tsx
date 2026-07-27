'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

interface Source {
  id: number;
  name: string;
  category: string;
  feed_url: string | null;
  status: string;
  health: 'active' | 'broken' | 'stale' | 'disabled' | 'unknown';
  last_fetched_at: string | null;
  fetch_error_count: number;
  recent_items_7d: number;
}

interface SourcesResponse {
  sources: Source[];
  total: number;
  healthy: number;
  broken: number;
}

export default function AdminSourcesPage() {
  const [data, setData] = useState<SourcesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'active' | 'broken' | 'stale' | 'disabled'>('all');

  useEffect(() => {
    loadSources();
  }, []);

  const loadSources = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/admin/sources');
      if (!response.ok) {
        throw new Error(`Failed to load sources: ${response.statusText}`);
      }
      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sources');
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (timestamp: string | null) => {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  const healthBadge = (health: string) => {
    const styles: Record<string, string> = {
      active: 'bg-positive text-positive-fg ring-1 ring-inset ring-positive-edge',
      broken: 'bg-critical text-critical-fg ring-1 ring-inset ring-critical-edge',
      stale: 'bg-caution text-caution-fg ring-1 ring-inset ring-caution-edge',
      disabled: 'bg-surface-sunken text-content-muted ring-1 ring-inset ring-edge',
      unknown: 'bg-surface-sunken text-content-secondary ring-1 ring-inset ring-edge',
    };
    return (
      <span className={`inline-block px-2 py-1 rounded-full text-chip uppercase ${styles[health] || styles.unknown}`}>
        {health}
      </span>
    );
  };

  const categoryBadge = (category: string) => {
    const styles: Record<string, string> = {
      official: 'bg-action-quiet text-action ring-1 ring-inset ring-action/25',
      press: 'bg-surface-sunken text-content-secondary ring-1 ring-inset ring-edge',
      other: 'bg-surface-sunken text-content-muted ring-1 ring-inset ring-edge',
    };
    return (
      <span className={`inline-block px-2 py-1 rounded-full text-chip uppercase ${styles[category] || styles.other}`}>
        {category}
      </span>
    );
  };

  const filteredSources = data?.sources.filter((s) => {
    if (filter === 'all') return true;
    return s.health === filter;
  }) || [];

  return (
    <main className="min-h-screen bg-canvas">
      <div className="max-w-6xl mx-auto p-4 md:p-8">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-display text-title text-content">RSS Sources</h1>
              <p className="text-meta text-content-muted mt-1">
                Admin view of all configured news sources
              </p>
            </div>
            <Link
              href="/"
              className="text-ui text-action hover:underline"
            >
              Back to Feed
            </Link>
          </div>
        </div>

        {/* Summary Cards */}
        {data && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div className="bg-surface rounded-lg border border-edge p-4">
              <p className="font-display text-title text-content tabular-nums">{data.total}</p>
              <p className="text-meta text-content-muted">Total Sources</p>
            </div>
            <div className="bg-surface rounded-lg border border-positive-edge p-4">
              <p className="font-display text-title text-positive-fg tabular-nums">{data.healthy}</p>
              <p className="text-meta text-content-muted">Healthy</p>
            </div>
            <div className="bg-surface rounded-lg border border-critical-edge p-4">
              <p className="font-display text-title text-critical-fg tabular-nums">{data.broken}</p>
              <p className="text-meta text-content-muted">Broken</p>
            </div>
            <div className="bg-surface rounded-lg border border-caution-edge p-4">
              <p className="font-display text-title text-caution-fg tabular-nums">
                {data.sources.filter((s) => s.health === 'stale').length}
              </p>
              <p className="text-meta text-content-muted">Stale</p>
            </div>
            <div className="bg-surface rounded-lg border border-edge p-4">
              <p className="font-display text-title text-content-muted tabular-nums">
                {data.sources.filter((s) => s.health === 'disabled').length}
              </p>
              <p className="text-meta text-content-muted">Disabled</p>
            </div>
          </div>
        )}

        {/* Filter Tabs */}
        <div className="flex gap-2 mb-4">
          {(['all', 'active', 'broken', 'stale', 'disabled'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`tap-44 inline-flex items-center px-3 py-2 rounded-md text-ui transition-colors ${
                filter === f
                  ? 'bg-action text-on-action'
                  : 'bg-surface text-content-secondary border border-edge hover:bg-surface-sunken'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
              {data && f !== 'all' && (
                <span className="ml-1 text-meta opacity-70 tabular-nums">
                  ({data.sources.filter((s) => s.health === f).length})
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Loading */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-action"></div>
            <p className="mt-4 text-body text-content-secondary">Loading sources...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-critical border border-critical-edge rounded-lg p-4 mb-6">
            <p className="text-body text-critical-fg">
              <strong>Error:</strong> {error}
            </p>
            <button
              onClick={loadSources}
              className="mt-2 text-ui text-critical-fg underline hover:no-underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Sources Table */}
        {!loading && !error && (
          <div className="bg-surface rounded-lg border border-edge overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-surface-sunken border-b border-edge">
                    <th className="text-left px-4 py-3 text-label uppercase text-content-muted">Source</th>
                    <th className="text-left px-4 py-3 text-label uppercase text-content-muted">Category</th>
                    <th className="text-left px-4 py-3 text-label uppercase text-content-muted">Health</th>
                    <th className="text-left px-4 py-3 text-label uppercase text-content-muted">Last Fetch</th>
                    <th className="text-right px-4 py-3 text-label uppercase text-content-muted">Errors</th>
                    <th className="text-right px-4 py-3 text-label uppercase text-content-muted">Items (7d)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge">
                  {filteredSources.map((source) => (
                    <tr
                      key={source.id}
                      className={`hover:bg-surface-sunken ${source.health === 'broken' ? 'bg-critical/40' : ''}`}
                    >
                      <td className="px-4 py-3">
                        <div>
                          <p className="text-ui text-content">{source.name}</p>
                          {source.feed_url && (
                            <p className="text-meta text-content-muted truncate max-w-xs" title={source.feed_url}>
                              {source.feed_url}
                            </p>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">{categoryBadge(source.category)}</td>
                      <td className="px-4 py-3">{healthBadge(source.health)}</td>
                      <td className="px-4 py-3 text-meta text-content-secondary tabular-nums">
                        {formatTime(source.last_fetched_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`text-ui tabular-nums ${source.fetch_error_count > 0 ? 'text-critical-fg font-semibold' : 'text-content-muted'}`}>
                          {source.fetch_error_count}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`text-ui tabular-nums ${source.recent_items_7d > 0 ? 'text-content' : 'text-content-muted'}`}>
                          {source.recent_items_7d}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {filteredSources.length === 0 && (
              <div className="text-center py-8 text-body text-content-muted">
                No sources match the selected filter.
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="mt-8 text-center text-meta text-content-muted">
          <p>Sharks News Aggregator - Admin Panel</p>
        </div>
      </div>
    </main>
  );
}
