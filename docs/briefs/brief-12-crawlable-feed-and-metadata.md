# Brief 12 — Make the feed crawlable, and give it metadata

Plan items: **SEO-1 … SEO-11**. Source: DataForSEO audit of
`https://wplepla23gjn.nobgp.com/`, 2026-07-27.

**Ship as three PRs, one per session:**

| Phase | Scope | Items | Effort | Rebuild |
|-------|-------|-------|--------|---------|
| **A** | Correct `PUBLIC_SITE_URL` on the Pi and the docs that let it drift | SEO-11 | XS | api only |
| **B** | Server-render the feed, plus the structural content that comes with it | SEO-1 … SEO-4 | L | web |
| **C** | Metadata, discovery, and structured data | SEO-5 … SEO-10 | M | web |

Phase A is config-only and ships on its own today — it needs no web build and
fixes a live correctness bug in the published RSS feed.

Phase C does not depend on Phase B except for **SEO-9's `ItemList`**, which needs
server-rendered items to describe. If B slips, C can ship with `ItemList` held
back.

## Task

The site scores 94/100 on DataForSEO OnPage and 99/96/100/100 on Lighthouse, and
none of that reflects reality, because those tools grade the shell and the shell
is all a crawler receives. `web/app/page.tsx` is a `'use client'` component; every
cluster is fetched after hydration. The server response is **108 words** — header,
filter bar, footer — at a 4.3% text-to-HTML ratio.

Google has indexed the homepage (rank 1 for `site:nobgp.com sharks`) and chose
this as the snippet:

> "Sharks News Aggregator is an independent, unofficial project. Not affiliated
> with the NHL or the San Jose Sharks."

That is the footer disclaimer. There was no article content to draw from. The same
applies to GPTBot, ClaudeBot, PerplexityBot and Bing, none of which execute
JavaScript on arbitrary pages.

Make the feed crawlable, then give crawlers the metadata to make sense of it.

## Context

### What exists today

- `web/app/page.tsx` is `'use client'` (line 1). It owns filter state, reads and
  writes filters to the URL via `readFiltersFromUrl()` / `writeFiltersToUrl()`
  (`history.replaceState`), and fetches clusters through `ApiClient`
  (`web/app/api-client.ts`) against the BFF routes under `web/app/api/`.
- `web/app/layout.tsx:5` exports the **only** public `metadata` object. `/`,
  `/about`, `/legal` and `/submit` therefore all serve
  `<title>Sharks News Aggregator</title>` and the same 43-character description.
  There is no `metadataBase`, so Next cannot emit absolute URLs.
- `DEFAULT_SINCE = '24h'` (`web/app/lib/filters.ts:21`). The default view currently
  renders **8 stories**.
- BFF proxies exist for feed, entities, stats, cluster detail and submissions
  (`web/app/api/*/route.ts`). All use `cache: 'no-store'`. `INTERNAL_API_URL` comes
  from `web/app/api/config.ts`.
- `web/app/rss/route.ts` proxies the backend `/rss` with `revalidate = 300`.
- Ingest runs every **10 minutes** (`ingest_interval_minutes: int = 10`,
  `api/app/core/config.py:20`, scheduled at `api/app/tasks/celery_app.py:35`).
- `/admin*` correctly returns 401. `/api/*` is a public BFF surface.
- Security headers, CSP, mobile layout, heading hierarchy and ARIA are all clean —
  **do not regress these.** CSP is `connect-src 'self'`, which the client-side
  refetch still needs.

### Two dependencies that are not obvious

1. **`GET /entities` is alphabetical, not ranked** (`api/app/routers/feed.py:157`).
   It returns Adam Gaudette, Alexander Karmanov, Alexander Wennberg… — useless for
   a "players in the news" strip. SEO-2 needs a prominence ordering.
2. **There is no public sources endpoint.** `GET /sources` is admin-only
   (`api/app/routers/admin.py:59`, behind the 401). SEO-3 needs either a new public
   endpoint or a static list.

### What this brief deliberately does not do

- **No fix for legacy headline/link mismatches.** Verified 2026-07-27: cluster 4019
  was mismatched at 15:52 and correctly re-headlined by 16:15, so `df142f2` works on
  live clusters. Cluster 4003 ("Edmonton police to introduce involuntary detention
  detox" → a Hockey News article about NHL players, first seen 2026-07-22, and
  carrying a microsecond timestamp format no other cluster has) is pre-fix backlog.
  Owner's call: leave it. At a 24h window it ages out on its own.
- **No `searchParams`-driven server filtering, and no `/tag/*` routes.** Filters stay
  client-side. Real tag routes are follow-up work (see the end of this brief) and
  doing them half-way here makes both harder.
- **No custom domain.** Noted in the audit as the strategic ceiling; out of scope.

---

## Phase A — config correctness

### SEO-11 — `PUBLIC_SITE_URL` points at a dead host

- **Symptom.** `/rss` is served correctly (200, 50 items, sane cache headers) but its
  channel metadata says:
  ```xml
  <link>https://x2mq74oetjlz.nobgp.com</link>
  <atom:link href="https://x2mq74oetjlz.nobgp.com/rss" rel="self" type="application/rss+xml" />
  ```
  That host **404s**. Every feed reader, Bluesky mirror and aggregator ingesting this
  feed records a broken canonical origin, and `rel="self"` pointing at a 404 fails
  strict feed validation.
- **Cause.** `settings.public_site_url` (`api/app/core/config.py:17`, consumed at
  `api/app/routers/feed.py:198`) defaults to `http://localhost:3000` and is overridden
  by the Pi's `.env`, which still holds the dead host. Note `7cdcf34` did **not** fix
  this — it corrected docs plus `allowedDevOrigins` (dev-only). This is live config.
- **Why it drifted.** `docker-compose.pi.yml` never declares `PUBLIC_SITE_URL` (only
  `docker-compose.yml:83` does), and `.env.example:25` plus
  `docs/ARCHITECTURE.md:342` both still document the value as `localhost:3000`, so
  there is no recorded production value to check drift against.
- **Approach.**
  1. Set `PUBLIC_SITE_URL=https://wplepla23gjn.nobgp.com` in the Pi's `.env`.
  2. Declare it in `docker-compose.pi.yml` alongside `ALLOWED_ORIGINS` so the
     production value lives in version control, not only on the box.
  3. Update `.env.example:25` and `docs/ARCHITECTURE.md:342` to record the real
     production value rather than the localhost default.
  4. Restart `api` only. **No web rebuild.**
- **Verify.** `curl -s https://wplepla23gjn.nobgp.com/rss | head -20` shows both
  `<link>` and `atom:link href` on `wplepla23gjn.nobgp.com`; the feed still validates;
  item links are unchanged (they always pointed at real source URLs).

---

## Phase B — server-render the feed

### SEO-1 — Split `page.tsx` into a server shell and a client feed

- **Approach.** `web/app/page.tsx` becomes a **server component** that fetches the
  initial 24h cluster set at request time and passes it to a new
  `<FeedList initial={…}>` client child, which keeps all existing filter state,
  URL syncing and refetch-on-change behaviour untouched.
- **Fetch from the server, not through your own BFF.** The server component must call
  `INTERNAL_API_URL` directly (`web/app/api/config.ts`) over the docker network.
  Do **not** have it fetch its own `/api/feed` route — that is an extra hop, needs an
  absolute URL, and breaks during build. `ApiClient` (`web/app/api-client.ts`) is
  browser-oriented and uses relative URLs; either give it a server variant or call
  `fetch` directly in the page.
- **Window.** Server-render exactly the **24h default** (`DEFAULT_SINCE`), currently
  ~8 stories. Owner's decision: keep the 24h default rather than widening it. Do not
  render a wider set and hide the surplus — hidden content is discounted anyway, and
  it is not an honest pattern.
- **Revalidate.** `export const revalidate = 300`. Ingest is every 10 minutes, so
  nothing is ever more than half a cycle stale, and it matches `web/app/rss/route.ts`.
  This also turns the page into ISR, which **incidentally removes the
  `Cache-Control: no-store` header** the HTML currently ships — a free fix for a
  separate audit finding.
- **Timestamps — two separate hydration problems, both resolved by decision.**
  1. `formatLastScanTime()` (`web/app/page.tsx:106-110`, rendered at `:216`) produces
     a relative string ("Last scan: 3 minutes ago"). Computed server-side and then
     ISR-cached for 5 minutes, it would be wrong on arrival and mismatch on hydrate.
     **Owner's decision: render an absolute datetime instead.** No client effect, no
     `suppressHydrationWarning`, no staleness — the string is simply true whenever it
     was rendered.
  2. Card dates are **already** absolute (`web/app/components/ClusterCard.tsx:25`),
     but `toLocaleString('en-US', …)` is passed **no `timeZone`**, so the server
     formats in the container's zone (UTC) and the browser in the viewer's. That
     mismatch survives fixing (1). Pin `timeZone: 'America/Los_Angeles'` — it is
     deterministic across server and client, and team-local time is the right frame
     for a Sharks feed regardless.
  - Wrap both in `<time datetime={isoString}>`. That is one line each and closes the
    audit's "no machine-readable dates" finding at the same time: the rendered feed
    currently contains **zero** `<time>` elements, on a site whose entire premise is
    freshness.
- **Empty-state parity.** The server render must produce the same "no stories in this
  window" state the client does, or an empty 24h window ships a blank page to
  crawlers.
- **Verify.** `curl -s https://…/ | grep -c '<h2'` returns the story count — not 0.
  Word count via DataForSEO OnPage climbs well above 108 with
  `low_content_rate` cleared. Filters still work with JS on, and the URL still
  round-trips `?tags=`/`?since=`/`?entities=`.

### SEO-2 — Server-render players-in-the-news chips

The player filter is currently an empty text input with no names in the HTML at all.

- **Approach.** Replace it with (or precede it with) a server-rendered strip of the
  ~15–20 entities currently appearing in the feed, as real clickable filter chips.
  Keep the free-text search for everything else.
- **Blocked on ranking.** `GET /entities` is alphabetical. Add an ordering parameter
  (e.g. `?order_by=cluster_count&limit=20`) to `api/app/routers/feed.py:157`, derived
  from entity↔cluster joins over the same window as the feed. Alphabetical would put
  Adam Gaudette permanently first, which is neither useful nor accurate.
- **Why this shape and not prose.** The audit explicitly recommends *against* a static
  paragraph listing player names. Boilerplate keyword lists that never change and are
  not tied to content are what Google's spam policy targets. The same names as
  functional, clickable UI are unimpeachable — and a populated chip strip is better
  UX than a blank search box.
- **Verify.** Player names appear in `curl` output. Clicking a chip filters the feed
  exactly as typing the name does today.

### SEO-3 — Name the sources

The footer says "Powered by RSS feeds from official sources and trusted media
outlets" and names none of them. For an aggregator, the source list is the single
strongest E-E-A-T signal available, and it is currently invisible.

- **Approach.** Add a public `GET /sources` returning only non-sensitive fields
  (name, `base_url`, category) for active sources — the admin endpoint at
  `api/app/routers/admin.py:59` stays as-is behind auth. Render the outlet names
  server-side, either in the footer or on a dedicated `/sources` page linked from it.
- **Alternative if you want zero API surface:** a static list built from
  `initial_sources.csv`. Zero risk, but it goes stale silently, which is how the
  `PUBLIC_SITE_URL` bug happened. Prefer the endpoint.
- **Do not expose** `feed_url`, credentials, error counts, or anything else from the
  admin shape. Whitelist fields explicitly rather than filtering a full model.
- **Verify.** Outlet names appear in `curl` output. `/sources` returns no field the
  admin UI treats as private.

### SEO-4 — Expand the intro copy

- **Approach.** Extend the header paragraph in `page.tsx` to state the goal plainly —
  one place to check all the latest Sharks news, updated every 10 minutes, links
  straight to original reporting. Borrow the voice from `web/app/about/page.tsx`,
  which already does this well ("Built by a Sharks fan for Sharks fans").
- **Keep the honesty.** The existing note about missing X/Twitter coverage stays; it
  is a trust signal, not a weakness.
- **Do not pad.** SEO-1 through SEO-3 supply the bulk of the new indexable text. This
  item is a paragraph, not a wall.

---

## Phase C — metadata, discovery, structured data

### SEO-5 — `robots.txt` and `sitemap.xml`

Both currently 404, and there is no `app/robots.ts` or `app/sitemap.ts`.

- **Approach.** Add `web/app/robots.ts` (allow all; disallow `/admin` and `/api`;
  declare the sitemap) and `web/app/sitemap.ts` listing `/`, `/about`, `/legal`,
  `/submit`, with `lastmod` on `/` driven by the newest cluster's `last_seen_at`.
- **Verify.** Both return 200 with correct content types. `/admin` is disallowed.

### SEO-6 — `metadataBase` and per-page metadata

- **Approach.** Add `metadataBase: new URL('https://wplepla23gjn.nobgp.com')` to
  `web/app/layout.tsx:5` — without it Next cannot emit absolute canonical or OG URLs.
  Then add `export const metadata` to `about`, `legal` and `submit`.
- **Homepage title.** Currently 22 characters and flagged `title_too_short`; it does
  not contain "San Jose Sharks" in any form people search. Target ~55–60 characters,
  e.g. *"San Jose Sharks News & Rumors, Updated Hourly | Sharks News Aggregator"* —
  trim to fit rather than shipping something Google truncates.
- **Single source of truth.** Put the base URL in one exported constant, not a literal
  repeated across `layout.tsx`, `sitemap.ts`, `robots.ts` and the JSON-LD. SEO-11
  exists because a URL was duplicated across six files.

### SEO-7 — Canonical tags

- **Approach.** Canonical on `/` points at the bare origin, so
  `?tags=trade&since=7d&entities=…` written by `writeFiltersToUrl()` collapses into
  the homepage. Static canonicals on the other three pages.
- **Known trade-off, accepted by owner:** filter URLs become non-indexable. Real
  `/tag/*` routes are the follow-up that makes them indexable properly.

### SEO-8 — Open Graph and Twitter Card

Currently absent everywhere. Sharing the site on Bluesky — the project's live
distribution channel — produces a bare link with no card.

- **Approach.** `openGraph` and `twitter` blocks in `layout.tsx` plus per-page
  overrides, and one **static** 1200×630 image built from the crest in `Logos/`,
  served from `web/public/`. Owner's decision: static for now, not a dynamic
  `opengraph-image.tsx`.
- **Verify.** Paste the URL into Bluesky and confirm the card renders with title,
  description and image.

### SEO-9 — JSON-LD

- **Approach.** `WebSite` + `Organization` sitewide; `CollectionPage` with an
  `ItemList` of the server-rendered clusters on `/`; `Person` for Davin on `/about`,
  linked as the site's author. Emit as `<script type="application/ld+json">`.
- **Do not use `NewsArticle` per item.** The site links out rather than hosting
  articles; claiming article markup for someone else's reporting misrepresents
  authorship and is the kind of thing that earns a manual action. `ItemList` of
  linked items is the honest shape.
- **`ItemList` depends on SEO-1.** If Phase B has not shipped, hold this one part back
  and ship the rest of C.
- **Verify.** Google Rich Results Test passes with no errors on `/` and `/about`.

### SEO-10 — `llms.txt`

- **Approach.** Static `web/public/llms.txt`: what the site is, what it covers, the
  10-minute update cadence, the RSS URL, the Bluesky mirror, and the
  independent/unofficial disclaimer.
- **Why static.** Zero maintenance, and it is the one thing that makes the site
  legible to AI crawlers regardless of render state.

---

## Deploy notes

Per `[[pi-deploy]]`: storage has been upgraded and recent deploys run **~3 minutes**,
so the historical ~90-minute eMMC ceremony does not apply. Standard flow —
backup → `git pull` → `docker compose -f docker-compose.yml -f docker-compose.pi.yml
build` → `up -d`.

- **Phase A** touches API config only: `.env` + `build api worker beat` is unnecessary,
  a restart suffices. No web rebuild.
- **Phases B and C** need a web rebuild. B also adds an API endpoint change (SEO-2's
  entity ordering, SEO-3's `/sources`) — remember `api`, `worker` and `beat` are three
  separate images, so "build the backend" means `build api worker beat`.
- **Prod drifts behind main.** First diagnostic after deploying: `git log --oneline -1`
  in `/opt/Sharks-News-Aggregator` against `origin/main`.

## After this brief

Not in scope, but this is the natural next step and the reason SEO-7's trade-off is
acceptable:

- **Crawlable tag routes.** `/tag/trade-rumors`, `/tag/injury`, `/tag/signing` as
  server-rendered pages with their own titles, descriptions, canonicals and sitemap
  entries. `sharks trade rumors` is **1,900 searches/month at difficulty 23 and +125%
  year over year** (DataForSEO Labs, US/en) — by a distance the most winnable term
  available, and the Trade and Rumors tags already exist.
- **Google Search Console.** With one indexed page and zero referring domains, GSC is
  the only way to see whether any of this actually moved indexation.
