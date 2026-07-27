/**
 * Brand strings that are safe in both server and client components.
 *
 * Kept out of `site.ts` on purpose: that module reads `process.env` at module
 * scope, so importing it from a `'use client'` file would pull env-reading code
 * into the browser bundle, where `PUBLIC_SITE_URL` resolves to `undefined` and
 * `SITE_URL` would silently read `http://localhost:3000`. Nothing client-side
 * uses it today, but shipping a constant that is wrong in the browser is a trap
 * for whoever reaches for it next.
 */

/** Alt text for the crest, wherever it appears. */
export const LOGO_ALT = 'Sharks News Aggregator Logo';
