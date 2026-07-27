import Image from 'next/image';
import Link from 'next/link';
import { FeedList } from './components/FeedList';
import { SourceList } from './components/SourceList';
import { FeedStructuredData } from './components/StructuredData';
import { DEFAULT_SINCE } from './lib/filters';
import { LOGO_ALT } from './lib/branding';
import { formatLastScan, isoDateTime } from './lib/dates';
import {
  fetchInitialFeed,
  fetchLastScanAt,
  fetchProminentEntities,
  fetchPublicSources,
  fetchSiteStats,
} from './lib/server-api';

/**
 * Feed page — a server component (SEO-1).
 *
 * This used to be `'use client'`, which meant the server response was the
 * header, the filter bar and the footer: 108 words, no stories. Google indexed
 * it and picked the footer disclaimer as the snippet, because that was the only
 * prose on the page. AI crawlers, which do not execute JavaScript, saw the same
 * thing.
 *
 * The shell and the first page of stories are now rendered here; `FeedList`
 * adopts them and owns everything interactive from that point on.
 *
 * ---
 *
 * Rendered per request, with the *data* cached rather than the page.
 *
 * The obvious setup — plain ISR via `export const revalidate` — is wrong here.
 * Next prerenders the page at build time, and inside the Docker build the API
 * is unreachable, so the image would ship an HTML file containing "No news
 * items found". Every deploy would then serve that empty page to whoever
 * arrived first, until the first revalidation replaced it. Verified: a build
 * with a reachable backend bakes the stories straight into
 * `.next/server/app/index.html`.
 *
 * `force-dynamic` skips the build-time prerender, and `fetchCache` keeps each
 * fetch's own `next: { revalidate }` honoured — without it, `force-dynamic`
 * downgrades every fetch to `no-store` and each visitor would hit the Pi.
 * Rendering is cheap; the network call is the thing worth caching.
 */
export const dynamic = 'force-dynamic';
export const fetchCache = 'default-cache';

export default async function Home() {
  // One round of parallel reads. Each degrades to null/[] rather than throwing,
  // so a backend hiccup costs content, not the page.
  const [feed, suggestedEntities, sources, siteStats, lastScanAt] = await Promise.all([
    fetchInitialFeed(DEFAULT_SINCE),
    fetchProminentEntities(DEFAULT_SINCE),
    fetchPublicSources(),
    fetchSiteStats(),
    fetchLastScanAt(),
  ]);

  const lastScanLabel = formatLastScan(lastScanAt);

  return (
    <main className="min-h-screen bg-canvas">
      <FeedStructuredData clusters={feed?.clusters ?? []} />
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        <header className="mb-8">
          <div className="flex items-center gap-3 sm:gap-4 mb-2">
            {/* Eager and high-priority because it is above the fold —
                lazy-loading it delayed the header paint. */}
            <Image
              src="/logo.png"
              alt={LOGO_ALT}
              width={64}
              height={64}
              priority
              className="object-contain w-12 h-12 sm:w-16 sm:h-16 flex-shrink-0"
            />
            <div>
              <h1 className="font-display text-masthead uppercase text-content">
                Sharks News Aggregator
              </h1>
              {lastScanLabel && lastScanAt && (
                <p className="text-meta text-content-muted mt-1 tabular-nums">
                  Last scan:{' '}
                  <time dateTime={isoDateTime(lastScanAt)}>{lastScanLabel}</time>
                </p>
              )}
            </div>
          </div>
          <p className="text-body text-content-secondary mt-3 max-w-[62ch]">
            Every San Jose Sharks story in one place, so you can catch up in a
            minute instead of working through a dozen feeds. We check official
            team channels, beat writers and fan blogs every ten minutes, group
            reports of the same story together, and link straight to the
            original reporting — trades, signings, injuries, line changes,
            prospects and Barracuda news included.
          </p>
          <p className="text-body text-content-secondary mt-3 max-w-[62ch]">
            Built by a Sharks fan for Sharks fans. It is missing news from
            popular X(Twitter) feeds because the X API costs $ to access. This
            feed is also published to{' '}
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

        <FeedList
          initialClusters={feed?.clusters ?? []}
          initialCursor={feed?.cursor ?? null}
          initialHasMore={feed?.has_more ?? false}
          initialFetchFailed={feed === null}
          suggestedEntities={suggestedEntities}
        />

        <footer className="mt-12 pt-8 border-t border-edge text-center text-meta text-content-muted">
          {siteStats && (
            <p className="mb-3 tabular-nums">
              {siteStats.page_views.toLocaleString()} visits ·{' '}
              {siteStats.total_stories.toLocaleString()} stories tracked ·{' '}
              {siteStats.total_sources} sources
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

          <SourceList sources={sources} />

          <p className="max-w-[60ch] mx-auto">
            Sharks News Aggregator is an independent, unofficial project. Not affiliated with the
            NHL or the San Jose Sharks.
          </p>
        </footer>
      </div>
    </main>
  );
}
