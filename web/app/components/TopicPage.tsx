import Image from 'next/image';
import Link from 'next/link';
import { ClusterList } from './ClusterList';
import { TopicStructuredData } from './StructuredData';
import { TopicNav } from './TopicNav';
import { LOGO_ALT } from '../lib/branding';
import { Topic, TOPIC_SINCE } from '../lib/topics';
import { fetchTopicFeed } from '../lib/server-api';

interface TopicPageProps {
  topic: Topic;
  /** Which feed filter this page is — tags or entities. */
  filter: 'tags' | 'entities';
  /** Path of this page, for canonical/JSON-LD. */
  path: string;
}

/**
 * Shared rendering for `/tag/[slug]` and `/player/[slug]`.
 *
 * Both are the same page with a different filter, so they share one
 * implementation — the alternative is two files that slowly disagree about
 * headings, empty states and structured data.
 */
export async function TopicPage({ topic, filter, path }: TopicPageProps) {
  const feed = await fetchTopicFeed(filter, topic.slug, TOPIC_SINCE);
  const clusters = feed?.clusters ?? [];

  return (
    <main className="min-h-screen bg-canvas">
      <TopicStructuredData topic={topic} path={path} clusters={clusters} />
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        <header className="mb-8">
          <Link href="/" className="flex items-center gap-4 mb-4 hover:opacity-80">
            <Image
              src="/logo.png"
              alt={LOGO_ALT}
              width={48}
              height={48}
              priority
              className="object-contain"
            />
            <span className="font-display text-wordmark uppercase text-content">
              Sharks News Aggregator
            </span>
          </Link>

          <h1 className="font-display text-masthead uppercase text-content">
            {topic.heading}
          </h1>
          <p className="text-body text-content-secondary mt-3 max-w-[62ch]">
            {topic.intro}
          </p>
        </header>

        <ClusterList
          initialClusters={clusters}
          initialCursor={feed?.cursor ?? null}
          initialHasMore={feed?.has_more ?? false}
          initialFetchFailed={feed === null}
          query={{ [filter]: topic.slug, since: TOPIC_SINCE }}
          activeEntitySlug={filter === 'entities' ? topic.slug : null}
          // A topic page holds no filter state, so entity chips hand off to the
          // feed filtered by that entity rather than rendering as buttons that
          // look interactive and do nothing.
          navigateEntitiesToFeed
          emptyState={
            // Worded as "quiet", not "broken". Several tags are genuinely empty
            // in the offseason and fill up from October; a reader landing here
            // in July should understand that, not assume the site is down.
            <div className="bg-surface border border-edge rounded-lg p-8 text-center">
              <p className="text-body text-content-secondary mb-1">
                Nothing here in the last 30 days.
              </p>
              <p className="text-meta text-content-muted max-w-[50ch] mx-auto">
                This topic is quiet right now — that is normal in the offseason.
                The full feed is still moving.
              </p>
              <Link
                href="/"
                className="tap-44 mt-4 inline-flex items-center px-4 py-2 rounded-md bg-action text-on-action text-ui hover:bg-action-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
              >
                Go to the full feed
              </Link>
            </div>
          }
        />

        {/* Topic-to-topic links keep every topic page one hop from every other,
            so crawl depth stays at 2 from the homepage rather than fanning out
            into a set of leaves that only the sitemap connects. */}
        <footer className="mt-12 pt-8 border-t border-edge text-center text-meta text-content-muted">
          <TopicNav />
          <p className="text-ui">
            <Link
              href="/"
              className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline"
            >
              &larr; All Sharks news
            </Link>
          </p>
        </footer>
      </div>
    </main>
  );
}
