import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { TopicPage } from '../../components/TopicPage';
import { findPlayerTopic } from '../../lib/topics';
import { pageMetadata } from '../../lib/site';

/**
 * Player pages (TAG-4). Currently a single allowlisted player.
 *
 * `/player/[slug]` rather than a one-off `/macklin-celebrini` so adding a second
 * player later is one entry in `PLAYER_TOPICS` — no route to write, no URL to
 * migrate, and no risk of the shape being decided differently the second time.
 *
 * Caching matches the tag routes, including the absence of
 * `generateStaticParams` — it overrides `force-dynamic` and would prerender an
 * empty page into the image. See the note on the tag route.
 */
export const dynamic = 'force-dynamic';
export const fetchCache = 'default-cache';

export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const topic = findPlayerTopic(params.slug);
  if (!topic) return {};

  return pageMetadata({
    title: topic.title,
    description: topic.description,
    path: `/player/${topic.slug}`,
  });
}

export default function PlayerRoute({ params }: { params: { slug: string } }) {
  const topic = findPlayerTopic(params.slug);
  // Every entity in the database would otherwise be an indexable URL. 47 have
  // coverage and ~150 exist; publishing them all is programmatic SEO on a
  // domain with no backlinks. One page ships, Search Console decides the rest.
  if (!topic) notFound();

  return <TopicPage topic={topic} filter="entities" path={`/player/${topic.slug}`} />;
}
