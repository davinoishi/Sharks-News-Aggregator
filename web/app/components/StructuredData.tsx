import { Cluster } from '../types';
import { Topic } from '../lib/topics';
import {
  AUTHOR_LINKS_URL,
  AUTHOR_NAME,
  BLUESKY_PROFILE_URL,
  SITE_DESCRIPTION,
  SITE_NAME,
  SITE_TITLE,
  SITE_URL,
  absoluteUrl,
} from '../lib/site';

/**
 * JSON-LD structured data (SEO-9).
 *
 * Stable `@id`s let the separate blocks reference each other, so crawlers read
 * one connected graph rather than four unrelated objects.
 *
 * **Deliberately no `NewsArticle` markup on feed items.** This site links out;
 * it does not host the reporting. Marking someone else's article up as if it
 * were ours would misrepresent authorship, and it is the kind of thing that
 * earns a manual action. `ItemList` of `ListItem`s pointing at the source URLs
 * is what the page honestly is: a list of links.
 */

const WEBSITE_ID = `${SITE_URL}/#website`;
const ORG_ID = `${SITE_URL}/#organization`;
const AUTHOR_ID = `${SITE_URL}/#author`;

// JSON-LD sits in a <script> block, so any "</script>" inside a string value
// would end it early. Escaping "<" closes that off; the rest is JSON already.
function serialise(data: unknown): string {
  return JSON.stringify(data).replace(/</g, '\\u003c');
}

function JsonLd({ data }: { data: unknown }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: serialise(data) }}
    />
  );
}

/**
 * Site-level identity, rendered on every page.
 *
 * `Organization` describes the site as a named project — not a company — with
 * the person who runs it as `founder`. The unofficial/unaffiliated status is
 * stated in the footer and on /legal; nothing here claims otherwise.
 */
export function SiteStructuredData() {
  return (
    <JsonLd
      data={{
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': 'WebSite',
            '@id': WEBSITE_ID,
            url: absoluteUrl('/'),
            name: SITE_NAME,
            description: SITE_DESCRIPTION,
            inLanguage: 'en-US',
            publisher: { '@id': ORG_ID },
          },
          {
            '@type': 'Organization',
            '@id': ORG_ID,
            name: SITE_NAME,
            url: absoluteUrl('/'),
            description:
              'An independent, unofficial San Jose Sharks news aggregator. ' +
              'Not affiliated with the NHL or the San Jose Sharks.',
            logo: {
              '@type': 'ImageObject',
              url: absoluteUrl('/favicon-512x512.png'),
              width: 512,
              height: 512,
            },
            founder: { '@id': AUTHOR_ID },
            sameAs: [BLUESKY_PROFILE_URL],
          },
          // Defined here rather than only on /about, because Organization.founder
          // references it from every page. Defining it on one page would leave
          // that reference dangling everywhere else.
          {
            '@type': 'Person',
            '@id': AUTHOR_ID,
            name: AUTHOR_NAME,
            description:
              'San Jose Sharks fan and the builder of Sharks News Aggregator.',
            url: absoluteUrl('/about'),
            sameAs: [AUTHOR_LINKS_URL],
          },
        ],
      }}
    />
  );
}

/** The feed itself: a collection page whose main entity is a list of links. */
export function FeedStructuredData({ clusters }: { clusters: Cluster[] }) {
  const items = clusters
    .filter((c) => c.top_url)
    .map((cluster, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: cluster.headline,
      url: cluster.top_url,
    }));

  return (
    <JsonLd
      data={{
        '@context': 'https://schema.org',
        '@type': 'CollectionPage',
        '@id': `${SITE_URL}/#webpage`,
        url: absoluteUrl('/'),
        name: SITE_TITLE,
        description: SITE_DESCRIPTION,
        inLanguage: 'en-US',
        isPartOf: { '@id': WEBSITE_ID },
        about: {
          '@type': 'SportsTeam',
          name: 'San Jose Sharks',
          sport: 'Ice hockey',
          memberOf: { '@type': 'SportsOrganization', name: 'National Hockey League' },
        },
        mainEntity: {
          '@type': 'ItemList',
          name: 'Latest San Jose Sharks stories',
          numberOfItems: items.length,
          itemListOrder: 'https://schema.org/ItemListOrderDescending',
          itemListElement: items,
        },
      }}
    />
  );
}

/**
 * A tag or player page: the same shape as the feed, scoped to one topic.
 *
 * `isPartOf` points at the site-wide `#website` node so the graph stays
 * connected rather than being an island per route. Still no `NewsArticle` —
 * these pages list other people's reporting, same as the homepage.
 */
export function TopicStructuredData({
  topic,
  path,
  clusters,
}: {
  topic: Topic;
  path: string;
  clusters: Cluster[];
}) {
  const items = clusters
    .filter((c) => c.top_url)
    .map((cluster, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: cluster.headline,
      url: cluster.top_url,
    }));

  return (
    <JsonLd
      data={{
        '@context': 'https://schema.org',
        '@type': 'CollectionPage',
        '@id': `${absoluteUrl(path)}#webpage`,
        url: absoluteUrl(path),
        name: topic.title,
        description: topic.description,
        inLanguage: 'en-US',
        isPartOf: { '@id': WEBSITE_ID },
        mainEntity: {
          '@type': 'ItemList',
          name: topic.heading,
          numberOfItems: items.length,
          itemListOrder: 'https://schema.org/ItemListOrderDescending',
          itemListElement: items,
        },
      }}
    />
  );
}

/** Who runs the site — the E-E-A-T signal /about already makes in prose. */
export function AuthorStructuredData() {
  return (
    <JsonLd
      data={{
        '@context': 'https://schema.org',
        '@type': 'ProfilePage',
        '@id': `${SITE_URL}/about#webpage`,
        url: absoluteUrl('/about'),
        isPartOf: { '@id': WEBSITE_ID },
        // The Person itself is defined once in the site-wide graph; this points
        // at it so there is a single canonical author node, not two that a
        // consumer has to reconcile.
        mainEntity: { '@id': AUTHOR_ID },
      }}
    />
  );
}
