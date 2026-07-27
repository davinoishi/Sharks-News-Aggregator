'use client';

import { Cluster, Entity } from '../types';
import { ApiClient } from '../api-client';
import { chipClass } from '../lib/taxonomy';
import { formatFeedDate, formatSourceDate, isoDateTime } from '../lib/dates';

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
  const formattedDate = formatFeedDate(cluster.last_seen_at);

  const isTrending = cluster.click_count >= TRENDING_THRESHOLD;

  const handleLinkClick = () => {
    // Record the click (fire and forget); default link behavior continues.
    ApiClient.recordClusterClick(cluster.id);
  };

  const focusRing =
    'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-1 focus-visible:ring-offset-surface';

  return (
    <div className="border border-edge rounded-lg p-4 hover:shadow-md transition-shadow bg-surface">
      {/* On phones the actions drop below the story so the headline gets the
          full column width — sharing the row with them left long headlines
          wrapping one or two words at a time. */}
      <div className="flex flex-col sm:flex-row items-start justify-between gap-2 sm:gap-4">
        <div className="flex-1 min-w-0 w-full">
          <h2 className="font-display text-headline text-content mb-2">
            {cluster.top_url ? (
              <a
                href={cluster.top_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={handleLinkClick}
                className={`hover:text-action hover:underline rounded-md ${focusRing}`}
              >
                {cluster.headline}
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            ) : (
              cluster.headline
            )}
          </h2>

          {/* Taxonomy reads as small caps labels, not as competing headlines:
              letterspacing disperses their visual mass so the eye still lands
              on the headline first. */}
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className={`px-2 py-1 rounded-md text-chip uppercase ${chipClass(cluster.event_type)}`}>
              {cluster.event_type}
            </span>

            {cluster.tags
              .filter((tag) => tag.name.toLowerCase() !== cluster.event_type.toLowerCase())
              .map((tag) => (
                <span
                  key={tag.id}
                  className={`px-2 py-1 rounded-md text-chip uppercase ${chipClass(tag.name)}`}
                >
                  {tag.name}
                </span>
              ))}
          </div>

          {/* Player and coach names stay in mixed case — they are proper nouns
              and the reader's main scan anchor, so recognizability beats the
              all-caps treatment given to taxonomy above. `leading-4` holds each
              pill at its previous height (and so its touch target) while the
              name itself gains a size step. */}
          {cluster.entities.length > 0 && (
            <div className="flex flex-wrap gap-x-2 gap-y-3 mb-3">
              {cluster.entities.map((entity) => {
                const isActive = activeEntitySlug === entity.slug;
                return (
                  <button
                    key={entity.id}
                    type="button"
                    onClick={() => onEntityClick?.(entity)}
                    aria-pressed={isActive}
                    title={`Filter by ${entity.name}`}
                    className={`tap-40 text-meta font-medium leading-4 px-2.5 py-1.5 rounded-full transition-colors ${focusRing} ${
                      isActive
                        ? 'bg-action text-on-action ring-1 ring-inset ring-action'
                        : 'bg-control text-control-fg ring-1 ring-inset ring-control-edge hover:bg-control-hover'
                    }`}
                  >
                    {entity.name}
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex items-center gap-4 text-meta text-content-muted tabular-nums">
            {/* Freshness is the whole premise of the feed, so the date is
                machine-readable and not just painted on. */}
            <time dateTime={isoDateTime(cluster.last_seen_at)}>{formattedDate}</time>
            <span>
              {cluster.source_count} {cluster.source_count === 1 ? 'source' : 'sources'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0 w-full sm:w-auto justify-start sm:justify-end">
          {isTrending && (
            <span className="inline-flex items-center px-2 py-1 rounded-md text-chip uppercase bg-trending text-trending-fg">
              <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
              </svg>
              Trending
              <span className="sr-only">, {cluster.click_count} clicks</span>
            </span>
          )}
          {cluster.source_count > 0 && (
            <button
              onClick={() => onExpand?.(cluster.id)}
              aria-expanded={!!isExpanded}
              // No side padding on phones, where the control sits on its own
              // row and should align with the story text; padded (and kept on
              // one line) from sm up, where it shares the row with the headline.
              className={`px-0 sm:px-3 py-1 text-ui sm:whitespace-nowrap text-action hover:bg-action-quiet rounded transition-colors ${focusRing}`}
            >
              {isExpanded ? 'Hide sources' : 'View sources'}
            </button>
          )}
        </div>
      </div>

      {isExpanded && cluster.variants && (
        <div className="mt-4 pt-4 border-t border-edge">
          <h3 className="text-label uppercase text-content-muted mb-3">Sources:</h3>
          <div className="space-y-2">
            {cluster.variants.map((variant) => (
              <a
                key={variant.variant_id}
                href={variant.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={handleLinkClick}
                className={`block p-3 bg-surface-sunken hover:bg-edge rounded-md transition-colors ${focusRing}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-ui text-content">{variant.title}</p>
                    <p className="text-meta text-content-muted mt-1 tabular-nums">
                      {variant.source_name} •{' '}
                      <time dateTime={isoDateTime(variant.published_at)}>
                        {formatSourceDate(variant.published_at)}
                      </time>
                      <span className="sr-only"> (opens in a new tab)</span>
                    </p>
                  </div>
                  <svg
                    className="w-4 h-4 text-content-muted flex-shrink-0 mt-1"
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
