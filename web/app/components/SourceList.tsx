import { PublicSource } from '../types';

interface SourceListProps {
  sources: PublicSource[];
}

// Order the categories deliberately rather than however the API happened to
// return them: official channels first, then press, then everything else.
const CATEGORY_ORDER = ['official', 'press', 'other'] as const;

const CATEGORY_LABELS: Record<string, string> = {
  official: 'Official',
  press: 'Press',
  other: 'Blogs & other',
};

/**
 * The outlets the feed aggregates, named (SEO-3).
 *
 * The footer used to say "Powered by RSS feeds from official sources and
 * trusted media outlets" and name none of them. For an aggregator — a site
 * whose entire value rests on where its material comes from — that is the one
 * claim readers have most reason to want substantiated, and it was the one
 * thing the page would not say.
 *
 * Rendered server-side, so the outlet names are in the HTML rather than behind
 * a fetch. Falls back to the old sentence if the source list is unavailable,
 * because a footer that silently loses a paragraph reads as broken.
 */
export function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) {
    return (
      <p className="mb-2">
        Powered by RSS feeds from official sources and trusted media outlets.
      </p>
    );
  }

  const grouped = CATEGORY_ORDER.map((category) => ({
    category,
    label: CATEGORY_LABELS[category] ?? category,
    items: sources.filter((s) => s.category === category),
  })).filter((group) => group.items.length > 0);

  // Any category the API grows later still gets published rather than silently
  // dropped from the list.
  const known = new Set<string>(CATEGORY_ORDER);
  const extras = sources.filter((s) => !known.has(s.category));
  if (extras.length > 0) {
    grouped.push({
      category: 'other',
      label: CATEGORY_LABELS.other,
      items: extras,
    });
  }

  return (
    <section className="mb-4 max-w-[70ch] mx-auto" aria-labelledby="sources-heading">
      <h2 id="sources-heading" className="text-label uppercase text-content-muted mb-2">
        Sources we aggregate
      </h2>
      <dl className="space-y-1.5">
        {grouped.map((group) => (
          <div key={group.category} className="sm:flex sm:gap-2 sm:justify-center">
            <dt className="text-content-muted sm:flex-shrink-0">{group.label}:</dt>
            <dd className="text-content-muted">
              {group.items.map((source, i) => (
                <span key={`${source.name}-${i}`}>
                  {i > 0 && ', '}
                  <a
                    href={source.base_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-action hover:underline"
                  >
                    {source.name}
                  </a>
                </span>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
