/**
 * The topic pages the site publishes, and the copy that goes on them.
 *
 * **These lists are allowlists, and that is the point.** `/tag/[slug]` and
 * `/player/[slug]` are dynamic routes; without a closed set to check against,
 * either would mint an indexable URL for any string a crawler invented. Anything
 * not listed here 404s.
 *
 * One definition feeds the routes, the "Browse by topic" nav and the sitemap, so
 * the three cannot drift out of sync.
 */

export interface Topic {
  /** URL segment and the API filter value. */
  slug: string;
  /** Nav label. */
  label: string;
  /** <h1> and the basis of the <title>. */
  heading: string;
  /** ~55-60 char page title (the layout appends the brand). */
  title: string;
  /** ~150-160 char meta description. */
  description: string;
  /** One sentence above the list, so the page is not purely other people's headlines. */
  intro: string;
}

/** The eight tags the feed applies. Order is the nav order. */
export const TAG_TOPICS: Topic[] = [
  {
    slug: 'trade',
    label: 'Trade',
    heading: 'San Jose Sharks Trade News & Rumors',
    title: 'San Jose Sharks Trade News & Rumors',
    description:
      'Every San Jose Sharks trade story and trade rumor from the last 30 days, ' +
      'gathered from beat writers, official channels and fan blogs.',
    intro:
      'Sharks trade news and trade rumors from the last 30 days. Reports of the ' +
      'same move are grouped together, and every headline links to the original ' +
      'reporting.',
  },
  {
    slug: 'rumors',
    label: 'Rumors',
    heading: 'San Jose Sharks Rumors',
    title: 'San Jose Sharks Rumors & Speculation',
    description:
      'The latest San Jose Sharks rumors from the last 30 days — trades, ' +
      'contracts and roster speculation, linked to the reporting behind them.',
    intro:
      'Sharks rumors from the last 30 days. Rumors are unconfirmed by ' +
      'definition — each one links to the original report so you can judge the ' +
      'source yourself.',
  },
  {
    slug: 'signing',
    label: 'Signings',
    heading: 'San Jose Sharks Signings & Contracts',
    title: 'San Jose Sharks Signings & Contract News',
    description:
      'San Jose Sharks signings, contract extensions and free agency news from ' +
      'the last 30 days, linked to the original reporting.',
    intro:
      'Sharks signings, extensions and free agency moves from the last 30 days.',
  },
  {
    slug: 'game',
    label: 'Games',
    heading: 'San Jose Sharks Game Coverage',
    title: 'San Jose Sharks Game Coverage & Recaps',
    description:
      'San Jose Sharks game previews, recaps and post-game coverage from the ' +
      'last 30 days, gathered from every outlet that covers the team.',
    intro: 'Sharks game previews, recaps and post-game reaction from the last 30 days.',
  },
  {
    slug: 'injury',
    label: 'Injuries',
    heading: 'San Jose Sharks Injury News',
    title: 'San Jose Sharks Injury News & Updates',
    description:
      'San Jose Sharks injury news and return timelines from the last 30 days, ' +
      'linked to the original reporting.',
    intro:
      'Sharks injury news from the last 30 days. Always check the linked source ' +
      'for the latest — injury reporting changes quickly.',
  },
  {
    slug: 'lineup',
    label: 'Lineup',
    heading: 'San Jose Sharks Lineup News',
    title: 'San Jose Sharks Lineup & Line Combinations',
    description:
      'San Jose Sharks lineup news, line combinations and roster moves from the ' +
      'last 30 days.',
    intro: 'Sharks lineup changes and line combinations from the last 30 days.',
  },
  {
    slug: 'waiver',
    label: 'Waivers',
    heading: 'San Jose Sharks Waiver News',
    title: 'San Jose Sharks Waiver Wire News',
    description:
      'San Jose Sharks waiver claims, waiver placements and related roster ' +
      'moves from the last 30 days.',
    intro: 'Sharks waiver activity from the last 30 days.',
  },
  {
    slug: 'barracuda',
    label: 'Barracuda',
    heading: 'San Jose Barracuda News',
    title: 'San Jose Barracuda (AHL) News & Prospects',
    description:
      'San Jose Barracuda news from the last 30 days — AHL results, call-ups ' +
      'and prospect development in the Sharks system.',
    intro:
      'San Jose Barracuda (AHL) news from the last 30 days, including prospect ' +
      'development and call-ups.',
  },
];

/**
 * Player pages. Deliberately **one** entry.
 *
 * 47 entities have 30-day coverage and roughly 150 exist. Publishing a page per
 * player is programmatic SEO at a scale Google scrutinises hardest, on a domain
 * with no backlinks — so this ships a single page for the most-covered player
 * (65 clusters in 30 days, 2.6x the next) and waits for Search Console to say
 * whether it earns its keep. Extending is a one-line change here, by design.
 *
 * The copy claims nothing biographical. The site stores a name, a slug and an
 * entity type; anything more would be invented.
 */
export const PLAYER_TOPICS: Topic[] = [
  {
    slug: 'macklin-celebrini',
    label: 'Macklin Celebrini',
    heading: 'Macklin Celebrini News & Rumors',
    title: 'Macklin Celebrini News, Rumors & Contract Updates',
    description:
      'Every Macklin Celebrini story from the last 30 days — contract news, ' +
      'rumors and game coverage, linked to the original reporting.',
    intro:
      'Published reporting that mentions Macklin Celebrini, from the last 30 ' +
      'days. Every headline links to its original source.',
  },
];

export function findTagTopic(slug: string): Topic | undefined {
  return TAG_TOPICS.find((t) => t.slug === slug);
}

export function findPlayerTopic(slug: string): Topic | undefined {
  return PLAYER_TOPICS.find((t) => t.slug === slug);
}

/** Window for every topic page. 24h would leave most of them empty. */
export const TOPIC_SINCE = '30d';

/**
 * Minimum 30-day clusters before a topic page is advertised in the sitemap.
 *
 * The page always renders and stays linked below this — it just isn't offered
 * for crawling until it has something to say. Applied against a live count
 * rather than a hardcoded skip list, because Waiver, Injury and Lineup are thin
 * in July and are exactly the tags that fill up from October.
 */
export const SITEMAP_MIN_CLUSTERS = 10;
