import Link from 'next/link';
import { PLAYER_TOPICS, TAG_TOPICS } from '../lib/topics';

/**
 * "Browse by topic" (TAG-3).
 *
 * This is the internal-linking path that makes the topic routes discoverable.
 * Without it they are orphans that only the sitemap knows about — crawlable in
 * principle, but with no link equity and no way for a reader to find them.
 *
 * Every topic is listed, including ones that are quiet right now. A link that
 * disappears when its tag goes quiet in the offseason and reappears in October
 * is worse than one that leads to an honest "nothing this month" page: the
 * sitemap already handles the "don't advertise thin pages for crawling" part.
 */
export function TopicNav() {
  return (
    <nav aria-labelledby="browse-topics-heading" className="mb-4">
      <h2
        id="browse-topics-heading"
        className="text-label uppercase text-content-muted mb-2"
      >
        Browse by topic
      </h2>
      <ul className="flex flex-wrap justify-center items-center gap-x-3 gap-y-2.5">
        {TAG_TOPICS.map((topic) => (
          <li key={topic.slug}>
            <Link
              href={`/tag/${topic.slug}`}
              className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline"
            >
              {topic.label}
            </Link>
          </li>
        ))}
        {PLAYER_TOPICS.map((topic) => (
          <li key={topic.slug}>
            <Link
              href={`/player/${topic.slug}`}
              className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline"
            >
              {topic.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
