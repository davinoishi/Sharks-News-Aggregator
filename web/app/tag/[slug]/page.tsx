import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { TopicPage } from '../../components/TopicPage';
import { findTagTopic } from '../../lib/topics';
import { pageMetadata } from '../../lib/site';

/**
 * Topic pages for the eight tags the feed applies (TAG-1).
 *
 * Same caching shape as the feed: `force-dynamic` skips the build-time
 * prerender (the API is unreachable inside the Docker build, so ISR would bake
 * an empty page into the image), while `fetchCache` keeps each fetch's own
 * revalidate so the Pi still sees one request per window, not one per visitor.
 *
 * Deliberately **no `generateStaticParams`**. It looks like useful
 * documentation of the closed set, but it wins over `force-dynamic`: the routes
 * build as `●` (prerendered) instead of `ƒ`, which re-creates the exact bug
 * fixed for the feed page in #121 — the API is unreachable during the Docker
 * build, so every topic page would ship an empty "nothing here in the last 30
 * days" snapshot baked into the image. `findTagTopic` is what enforces the
 * allowlist; `TAG_TOPICS` documents it.
 */
export const dynamic = 'force-dynamic';
export const fetchCache = 'default-cache';

export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const topic = findTagTopic(params.slug);
  if (!topic) return {};

  return pageMetadata({
    title: topic.title,
    description: topic.description,
    path: `/tag/${topic.slug}`,
  });
}

export default function TagRoute({ params }: { params: { slug: string } }) {
  const topic = findTagTopic(params.slug);
  // Allowlist, not pass-through: without this the route would mint an
  // indexable URL for any slug a crawler invented.
  if (!topic) notFound();

  return <TopicPage topic={topic} filter="tags" path={`/tag/${topic.slug}`} />;
}
