/**
 * Chip colouring for event types and tags.
 *
 * Replaces two overlapping rainbows: nine hand-picked Tailwind hue pairs for
 * event types, and ten X11 named colours (crimson, limegreen, hotpink,
 * blueviolet…) stored per-tag in the database. Neither encoded anything — two
 * stories could carry unrelated hues of identical loudness, and the chips
 * out-shouted the headline they annotated.
 *
 * Instead, a chip answers one question: how hard should a fan lean in?
 *
 *   speculation — reported talk, not fact. The thing fans actually chase.
 *   status      — a player's availability changed. Consequential.
 *   confirmed   — official, on the record.
 *   routine     — ordinary coverage. Most of the feed, deliberately quiet.
 *
 * The four tiers are separated by fill lightness (0.67 / 0.47 / 0.30 / 0.95) as
 * well as hue, so they survive greyscale and red-green colour vision
 * deficiency; and every chip renders its own label, so colour is never the only
 * code.
 *
 * Presentation lives here rather than in the database. `tags.display_color` is
 * still returned by the API and is now unused by the web client — nothing else
 * consumes it (RSS and BlueSky do not), so it can be dropped from the model
 * whenever the backend is next touched.
 */

export type Tier = 'speculation' | 'status' | 'confirmed' | 'routine';

const TIERS: Record<string, Tier> = {
  // Reported, unconfirmed — the loud tier, and the rarest.
  rumors: 'speculation',
  rumor: 'speculation',
  trade: 'speculation',

  // A player's availability changed.
  injury: 'status',
  waiver: 'status',

  // On the record.
  official: 'confirmed',
  signing: 'confirmed',
  recall: 'confirmed',

  // Ordinary coverage.
  game: 'routine',
  lineup: 'routine',
  prospect: 'routine',
  barracuda: 'routine',
  opinion: 'routine',
  other: 'routine',
};

/** Tier for an event type or tag name; unknown values stay quiet. */
export function tierFor(name: string | null | undefined): Tier {
  if (!name) return 'routine';
  return TIERS[name.trim().toLowerCase()] ?? 'routine';
}

const TIER_CLASS: Record<Tier, string> = {
  speculation: 'bg-chip-speculation text-chip-speculation-fg',
  status: 'bg-chip-status text-chip-status-fg',
  confirmed: 'bg-chip-confirmed text-chip-confirmed-fg',
  routine: 'bg-chip-routine text-chip-routine-fg ring-1 ring-inset ring-chip-routine-edge',
};

/** Tailwind classes for a chip, given an event type or tag name. */
export function chipClass(name: string | null | undefined): string {
  return TIER_CLASS[tierFor(name)];
}
