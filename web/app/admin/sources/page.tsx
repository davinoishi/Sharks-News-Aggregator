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
      active: 'bg-green-100 text-green-800',
      broken: 'bg-red-100 text-red-800',
      stale: 'bg-yellow-100 text-yellow-800',
      disabled: 'bg-gray-200 text-gray-500',
      unknown: 'bg-gray-100 text-gray-600',
    };
    return (
      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${styles[health] || styles.unknown}`}>
        {health}
      </span>
    );
  };

  const categoryBadge = (category: string) => {
    const styles: Record<string, string> = {
      official: 'bg-blue-100 text-blue-800',
      press: 'bg-purple-100 text-purple-800',
      other: 'bg-gray-100 text-gray-600',
    };
    return (
      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${styles[category] || styles.other}`}>
        {category}
      </span>
    );
  };

  const filteredSources = data?.sources.filter((s) => {
    if (filter === 'all') return true;
    return s.health === filter;
  }) || [];

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto p-4 md:p-8">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">RSS Sources</h1>
              <p className="text-sm text-gray-500 mt-1">
                Admin view of all configured news sources
              </p>
            </div>
            <Link
              href="/"
              className="text-sm text-blue-600 hover:underline"
            >
              Back to Feed
            </Link>
          </div>
        </div>

        {/* Summary Cards */}
        {data && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <p className="text-2xl font-bold text-gray-900">{data.total}</p>
              <p className="text-sm text-gray-500">Total Sources</p>
            </div>
            <div className="bg-white rounded-lg border border-green-200 p-4">
              <p className="text-2xl font-bold text-green-700">{data.healthy}</p>
              <p className="text-sm text-gray-500">Healthy</p>
            </div>
            <div className="bg-white rounded-lg border border-red-200 p-4">
              <p className="text-2xl font-bold text-red-700">{data.broken}</p>
              <p className="text-sm text-gray-500">Broken</p>
            </div>
            <div className="bg-white rounded-lg border border-yellow-200 p-4">
              <p className="text-2xl font-bold text-yellow-700">
                {data.sources.filter((s) => s.health === 'stale').length}
              </p>
              <p className="text-sm text-gray-500">Stale</p>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <p className="text-2xl font-bold text-gray-500">
                {data.sources.filter((s) => s.health === 'disabled').length}
              </p>
              <p className="text-sm text-gray-500">Disabled</p>
            </div>
          </div>
        )}

        {/* Filter Tabs */}
        <div className="flex gap-2 mb-4">
          {(['all', 'active', 'broken', 'stale', 'disabled'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                filter === f
                  ? 'bg-gray-900 text-white'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
              {data && f !== 'all' && (
                <span className="ml-1 text-xs opacity-70">
                  ({data.sources.filter((s) => s.health === f).length})
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Loading */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="mt-4 text-gray-600">Loading sources...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800">
              <strong>Error:</strong> {error}
            </p>
            <button
              onClick={loadSources}
              className="mt-2 text-sm text-red-600 hover:text-red-700 underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Sources Table */}
        {!loading && !error && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Source</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Category</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Health</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Last Fetch</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase">Errors</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase">Items (7d)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredSources.map((source) => (
                    <tr
                      key={source.id}
                      className={`hover:bg-gray-50 ${source.health === 'broken' ? 'bg-red-50/30' : ''}`}
                    >
                      <td className="px-4 py-3">
                        <div>
                          <p className="font-medium text-gray-900 text-sm">{source.name}</p>
                          {source.feed_url && (
                            <p className="text-xs text-gray-400 truncate max-w-xs" title={source.feed_url}>
                              {source.feed_url}
                            </p>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">{categoryBadge(source.category)}</td>
                      <td className="px-4 py-3">{healthBadge(source.health)}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {formatTime(source.last_fetched_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`text-sm font-mono ${source.fetch_error_count > 0 ? 'text-red-600 font-medium' : 'text-gray-400'}`}>
                          {source.fetch_error_count}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`text-sm font-mono ${source.recent_items_7d > 0 ? 'text-gray-900' : 'text-gray-400'}`}>
                          {source.recent_items_7d}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {filteredSources.length === 0 && (
              <div className="text-center py-8 text-gray-500">
                No sources match the selected filter.
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="mt-8 text-center text-xs text-gray-400">
          <p>Sharks News Aggregator - Admin Panel</p>
        </div>
      </div>
    </main>
  );
}
