/**
 * Typefaces.
 *
 * Two families, chosen against the crest (an athletic, all-caps newsprint
 * wordmark) and against the product's first principle: a fan should be caught
 * up in a minute.
 *
 * - Oswald (display): condensed newsprint/scoreboard grotesque. Beyond tone,
 *   it is functional here — a condensed face fits noticeably more headline per
 *   line at 360px, which is the width most of this site is read at.
 * - IBM Plex Sans (text): neutral but not anonymous, engineered for small
 *   sizes, with real tabular figures for the counters and timestamps.
 *
 * Both are self-hosted by `next/font` into the build output (no runtime request
 * to a font CDN, so the site's `font-src 'self'` CSP is satisfied unchanged),
 * subset to latin, and given a metric-compatible fallback so swapping in the
 * real face does not shift layout.
 */
import { IBM_Plex_Sans, Oswald } from 'next/font/google';

// Variable weight axis (200–700): one file covers every display weight.
export const display = Oswald({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-display',
});

export const text = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  display: 'swap',
  variable: '--font-text',
});
