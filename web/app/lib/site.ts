/**
 * Single source of truth for the site's public identity.
 *
 * The base URL is read from `PUBLIC_SITE_URL` — **the same environment variable
 * the API already uses** for the RSS channel's `<link>` and `atom:self`. One
 * value drives canonical tags, Open Graph URLs, the sitemap, robots.txt, the
 * JSON-LD `@id`s and the feed metadata, so the two services cannot disagree
 * about where the site lives.
 *
 * That is a direct response to SEO-11: the published RSS advertised a dead host
 * for weeks because the URL was duplicated across six files and the deployed
 * value had nothing to be diffed against. Anything needing the site URL imports
 * it from here.
 *
 * The localhost default is for local dev only. Production sets the real value in
 * `docker-compose.pi.yml`.
 */

export const SITE_URL = (
  process.env.PUBLIC_SITE_URL || 'http://localhost:3000'
).replace(/\/+$/, '');

export const SITE_NAME = 'Sharks News Aggregator';

/** ~60 characters, and it actually contains the phrase people search for. */
export const SITE_TITLE =
  'San Jose Sharks News & Rumors, Updated Hourly | Sharks News Aggregator';

/** ~158 chars — past roughly 160 Google truncates mid-sentence. */
export const SITE_DESCRIPTION =
  'Every San Jose Sharks story in one place, updated every 10 minutes — ' +
  'trades, signings, injuries, prospects and Barracuda news, linked to the ' +
  'original reporting.';

/** Static 1200x630 card. See `scripts/generate-og-image.py`. */
export const OG_IMAGE_PATH = '/og-image.png';

export const AUTHOR_NAME = 'Davin';
export const AUTHOR_LINKS_URL = 'https://linktr.ee/davinoishi';
export const BLUESKY_PROFILE_URL =
  'https://bsky.app/profile/sjsharks-news.bsky.social';

/** Absolute URL for a site-relative path. */
export function absoluteUrl(path = '/'): string {
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

/**
 * Open Graph block for a subpage.
 *
 * Next merges `metadata` shallowly, so a page that declares its own
 * `openGraph` **replaces** the root one outright — including `images`. Writing
 * the block by hand on each page silently drops the card image, which is only
 * visible by inspecting a share preview. This re-applies the shared parts so
 * that can't happen.
 */
export function pageOpenGraph(options: {
  title: string;
  description: string;
  path: string;
}) {
  return {
    type: 'website' as const,
    siteName: SITE_NAME,
    locale: 'en_US',
    title: options.title,
    description: options.description,
    url: options.path,
    images: [
      {
        url: OG_IMAGE_PATH,
        width: 1200,
        height: 630,
        alt: `${SITE_NAME} — San Jose Sharks news and rumors in one feed`,
      },
    ],
  };
}
