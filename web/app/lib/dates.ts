/**
 * Date formatting for a server-rendered feed.
 *
 * Two rules here, both of which exist because the feed is now rendered on the
 * server and cached (SEO-1):
 *
 * 1. **Always pass a time zone.** `toLocaleString()` without one formats in the
 *    runtime's zone — UTC inside the container, the reader's zone in the
 *    browser. The two disagree, which React reports as a hydration mismatch and
 *    the reader sees as the timestamp changing after the page settles. Pinning
 *    the zone makes the server and client agree by construction. Team-local is
 *    the right frame for a Sharks feed anyway: "7:58 PM" should mean puck drop,
 *    not whatever that is where the reader happens to be sitting.
 *
 * 2. **No relative strings on the server.** "3 minutes ago" is computed from
 *    `Date.now()`, so under ISR it is frozen at render time and served for the
 *    whole revalidate window — wrong on arrival and wrong again on hydrate.
 *    Absolute datetimes are simply true whenever they were rendered.
 */

export const SITE_TIME_ZONE = 'America/Los_Angeles';

/** Card and feed timestamps: "Jul 27, 7:58 AM". */
export function formatFeedDate(value: string | Date): string {
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: SITE_TIME_ZONE,
  });
}

/** Source-list timestamps, which carry a year: "Jul 27, 2026, 7:58 AM". */
export function formatSourceDate(value: string | Date): string {
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: SITE_TIME_ZONE,
  });
}

/**
 * Last-scan label, e.g. "Jul 27, 7:58 AM PT".
 *
 * Explicitly not "3 minutes ago" — see rule 2 above. The zone suffix matters
 * here in a way it doesn't on cards: this is the one timestamp a reader checks
 * to decide whether the feed is current, so an ambiguous one is worse than
 * none.
 */
export function formatLastScan(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${formatFeedDate(date)} PT`;
}

/** Machine-readable value for a `<time dateTime>` attribute. */
export function isoDateTime(value: string | Date): string | undefined {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}
