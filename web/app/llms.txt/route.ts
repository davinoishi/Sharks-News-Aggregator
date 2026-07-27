import { absoluteUrl, BLUESKY_PROFILE_URL, SITE_NAME } from '../lib/site';

// Content changes only when the site's purpose does.
export const revalidate = 86400;

/**
 * llms.txt (SEO-10).
 *
 * The brief called for a static `public/llms.txt`. Serving it from a route
 * instead so the URLs come from the one `SITE_URL` constant — a static file
 * would need them hardcoded, which is the duplication that let SEO-11 drift
 * unnoticed for weeks. Still zero-maintenance, and it stays correct if the site
 * ever moves to a custom domain.
 *
 * This matters more here than on most sites: AI crawlers do not execute
 * JavaScript, and until the feed was server-rendered they saw a 108-word shell.
 * This file states plainly what the site is and where the machine-readable feed
 * lives.
 */
export async function GET() {
  const body = `# ${SITE_NAME}

> An independent, unofficial aggregator of San Jose Sharks (NHL) news and
> rumors. It collects reporting from official team channels, beat writers and
> fan blogs, groups multiple reports of the same story into one entry, and
> links out to the original source. It does not host or rewrite articles.

Not affiliated with the NHL or the San Jose Sharks.

## What it covers

San Jose Sharks trades, signings, injuries, line changes, waivers, game
coverage, prospects, and San Jose Barracuda (AHL) news.

## How it works

- Sources are polled every 10 minutes.
- Related reports are clustered into a single entry with one headline.
- Every entry links to the original reporting; the site hosts no article text.
- Stories are tagged (Rumors, Trade, Injury, Lineup, Signing, Waiver, Game,
  Barracuda) and associated with the players and coaches they mention.

## Pages

- [Feed](${absoluteUrl('/')}): the latest stories, default last 24 hours.
- [About](${absoluteUrl('/about')}): who built the site and why.
- [Terms and privacy](${absoluteUrl('/legal')}): terms of use and privacy policy.
- [Submit a link](${absoluteUrl('/submit')}): suggest a story the feed missed.

## Machine-readable

- [RSS feed](${absoluteUrl('/rss')}): the 50 most recent stories, RSS 2.0.
- [Bluesky](${BLUESKY_PROFILE_URL}): the same stories, posted as they land.

## Attribution

If you cite content from this site, please attribute the original publication
linked in the entry rather than this aggregator. The list of outlets it draws
from is published in the site footer.
`;

  return new Response(body, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'public, max-age=86400, s-maxage=86400',
    },
  });
}
