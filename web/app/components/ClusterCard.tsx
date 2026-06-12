'use client';

import { Cluster, Entity } from '../types';
import { ApiClient } from '../api-client';
import { tagChipStyle } from '../lib/tagColor';

interface ClusterCardProps {
  cluster: Cluster;
  onExpand?: (id: number) => void;
  isExpanded?: boolean;
  onEntityClick?: (entity: Entity) => void;
  activeEntitySlug?: string | null;
}

// Threshold for showing trending indicator
const TRENDING_THRESHOLD = 5;

export function ClusterCard({
  cluster,
  onExpand,
  isExpanded,
  onEntityClick,
  activeEntitySlug,
}: ClusterCardProps) {
  const formattedDate = new Date(cluster.last_seen_at).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  const eventTypeColors: Record<string, string> = {
    trade: 'bg-blue-100 text-blue-800',
    injury: 'bg-red-100 text-red-800',
    lineup: 'bg-green-100 text-green-800',
    recall: 'bg-purple-100 text-purple-800',
    waiver: 'bg-yellow-100 text-yellow-800',
    signing: 'bg-indigo-100 text-indigo-800',
    prospect: 'bg-pink-100 text-pink-800',
    game: 'bg-orange-100 text-orange-800',
    opinion: 'bg-gray-100 text-gray-800',
    other: 'bg-gray-100 text-gray-600',
  };

  const eventTypeClass = eventTypeColors[cluster.event_type] || eventTypeColors.other;
  const isTrending = cluster.click_count >= TRENDING_THRESHOLD;

  const handleLinkClick = () => {
    // Record the click (fire and forget); default link behavior continues.
    ApiClient.recordClusterClick(cluster.id);
  };

  const focusRing =
    'focus:outline-none focus-visible:ring-2 focus-visible:ring-[#006D75] focus-visible:ring-offset-1';

  return (
    <div className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow bg-white">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h2 className="text-lg sm:text-xl font-semibold text-gray-900 mb-2">
            {cluster.top_url ? (
              <a
                href={cluster.top_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={handleLinkClick}
                className={`hover:text-[#006D75] hover:underline rounded ${focusRing}`}
              >
                {cluster.headline}
              </a>
            ) : (
              cluster.headline
            )}
          </h2>

          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className={`px-2 py-1 rounded text-xs font-medium capitalize ${eventTypeClass}`}>
              {cluster.event_type}
            </span>

            {cluster.tags
              .filter((tag) => tag.name.toLowerCase() !== cluster.event_type.toLowerCase())
              .map((tag) => (
                <span
                  key={tag.id}
                  className="px-2 py-1 rounded text-xs font-medium"
                  style={tagChipStyle(tag.color)}
                >
                  {tag.name}
                </span>
              ))}
          </div>

          {cluster.entities.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {cluster.entities.map((entity) => {
                const isActive = activeEntitySlug === entity.slug;
                return (
                  <button
                    key={entity.id}
                    type="button"
                    onClick={() => onEntityClick?.(entity)}
                    aria-pressed={isActive}
                    title={`Filter by ${entity.name}`}
                    className={`text-xs px-2 py-1 rounded-full transition-colors ${focusRing} ${
                      isActive
                        ? 'bg-[#006D75] text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {entity.name}
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span>{formattedDate}</span>
            <span>
              {cluster.source_count} {cluster.source_count === 1 ? 'source' : 'sources'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isTrending && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800" title={`${cluster.click_count} clicks`}>
              <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
              </svg>
              Trending
            </span>
          )}
          {cluster.source_count > 0 && (
            <button
              onClick={() => onExpand?.(cluster.id)}
              aria-expanded={!!isExpanded}
              className={`px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded transition-colors ${focusRing}`}
            >
              {isExpanded ? 'Hide sources' : 'View sources'}
            </button>
          )}
        </div>
      </div>

      {isExpanded && cluster.variants && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Sources:</h3>
          <div className="space-y-2">
            {cluster.variants.map((variant) => (
              <a
                key={variant.variant_id}
                href={variant.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={handleLinkClick}
                className={`block p-3 bg-gray-50 hover:bg-gray-100 rounded transition-colors ${focusRing}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900">{variant.title}</p>
                    <p className="text-xs text-gray-500 mt-1">
                      {variant.source_name} • {new Date(variant.published_at).toLocaleString()}
                    </p>
                  </div>
                  <svg
                    className="w-4 h-4 text-gray-400 flex-shrink-0 mt-1"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                    />
                  </svg>
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
