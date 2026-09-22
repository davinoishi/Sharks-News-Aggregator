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
 * **The font files are vendored into this repo** (`./fonts/`) and loaded with
 * `next/font/local`. They used to come from `next/font/google`, which fetches
 * from `fonts.googleapis.com` **at build time** — so a deploy could only
 * succeed while the builder had working internet to Google. On 2026-09-22 the
 * Pi's uplink degraded (4 of 5 requests to `fonts.googleapis.com` timed out,
 * successful connects taking 10–13s), `next/font` exhausted its three retries,
 * and `next build` failed with `ETIMEDOUT` — three times running, on a deploy
 * whose only change was a URL string. Nothing about the fonts had changed.
 * Vendoring the files removes Google from the build path entirely. The build
 * still needs the npm registry for `npm install`, so this does not make it
 * fully hermetic — it removes one of the two network dependencies, and the one
 * that was failing.
 *
 * Runtime behaviour is unchanged. `next/font` already self-hosted these into
 * the build output, so the site never requested a font CDN and `font-src
 * 'self'` is still satisfied; `adjustFontFallback` still derives a
 * metric-compatible fallback from the file, so swapping in the real face does
 * not shift layout.
 *
 * **What is in `./fonts/`, and how to refresh it.** Both files are the *latin*
 * subset, which is what `subsets: ['latin']` requested before, and both are
 * variable fonts — one file covers the whole weight axis, which is why three
 * IBM Plex Sans weights are one file and not three. To update, request the CSS
 * with a browser User-Agent (Google serves woff2 only to one), take the URL
 * from the `/* latin *\/` block, and keep the version in the filename:
 *
 *   curl -A "<a browser UA>" \
 *     'https://fonts.googleapis.com/css2?family=Oswald:wght@200..700&display=swap'
 *
 * Both faces are SIL Open Font License 1.1; the licences ship beside them in
 * `./fonts/`, which is what the OFL requires of a redistributed copy.
 */
import localFont from 'next/font/local';

// Variable weight axis 200–700 (the file's real `fvar` range): one file covers
// every display weight the type roles ask for.
export const display = localFont({
  src: './fonts/oswald-v57-latin.woff2',
  weight: '200 700',
  style: 'normal',
  display: 'swap',
  variable: '--font-display',
  adjustFontFallback: 'Arial',
});

// Variable weight axis 100–700. The site uses 400/500/600, but the range
// declared here is the one the file actually carries, so a new type role does
// not silently clamp to the nearest weight this comment happened to predict.
export const text = localFont({
  src: './fonts/ibm-plex-sans-v23-latin.woff2',
  weight: '100 700',
  style: 'normal',
  display: 'swap',
  variable: '--font-text',
  adjustFontFallback: 'Arial',
});
