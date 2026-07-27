# Brief 13 — Crawlable tag routes, and one player page

Plan items: **TAG-1 … TAG-6**. Follows brief 12, which made the feed crawlable
and gave it metadata but left every filtered view collapsing into the homepage.

**Ships as one PR.** Web-only — the feed API already supports everything needed
(`/feed?tags=…&since=30d` and `/feed?entities=…&since=30d`), so no API, worker
or beat rebuild.

## Task

Brief 12 canonicalised `?tags=trade&since=7d` into the bare homepage. That was
correct at the time — those URLs were client-side filter state, not pages — but
it means the site has exactly **four** indexable URLs, and none of them targets a
topic. Give the tags real routes, link them, and put them in the sitemap.

Then test entity pages with a single instance rather than 150.

## Context

### What exists today

- `web/app/page.tsx` is a server component that fetches the 24h window and hands
  it to `FeedList` (`web/app/components/FeedList.tsx`), which owns filter state,
  pagination, expansion and URL sync.
- `web/app/components/FilterBar.tsx` renders tag chips as `<button>`s that mutate
  client state. Time window options are 24h/7d/30d, default 24h
  (`web/app/lib/filters.ts`).
- `web/app/sitemap.ts` lists four URLs. `web/app/lib/site.ts` holds every piece
  of site identity; `pageOpenGraph()` exists because Next replaces rather than
  merges a child's `openGraph`.
- `web/app/lib/server-api.ts` wraps server-side reads, each degrading to
  `null`/`[]` rather than throwing.
- The feed API already accepts `tags`, `entities` and `since`. **No API change is
  needed for this brief.**

### Measured before designing (2026-07-27, offseason)

Clusters per tag:

| Tag | 30d | 7d | 24h |
|---|---|---|---|
| Rumors | 100+ | 16 | 1 |
| Signing | 100+ | 9 | 0 |
| Trade | 91 | 9 | 1 |
| Game | 45 | 11 | 0 |
| Barracuda | 25 | 4 | 0 |
| Lineup | 6 | 3 | 0 |
| Injury | 5 | 1 | 0 |
| Waiver | 1 | 0 | 0 |

Rumors ∩ Trade = 49 clusters — roughly half each way, so they are related but
genuinely distinct topics, not duplicates of each other.

Macklin Celebrini: **65 clusters in 30d**, 2.6× the next player (Jacob Trouba,
25) and second only to the team entity itself.

### Decisions already taken — do not re-litigate

- **30-day window on these pages.** At 24h every tag except Rumors and Trade
  would be empty. These are archives, not the live feed.
- **Thin-content gating is dynamic, never a hardcoded skip list.** Waiver, Injury
  and Lineup are thin *in July* — they are precisely the tags that spike
  October–April. A static exclusion would be wrong by opening night.
- **Tag chips stay `<button>`s.** The progressive-enhancement option (real
  anchors intercepted client-side) was considered and **rejected as not worth the
  complexity**; a footer "Browse by topic" list gets crawlability, internal links
  and sitemap entries for a fraction of the work. Revisit only with evidence.
- **One player page, Celebrini only.** 47 entities have 30-day coverage and ~150
  exist. That is programmatic-SEO scale and the pattern Google scrutinises
  hardest. Ship one, measure in Search Console, then decide with evidence.
- **No `tags_mode=all` on the API.** "sharks trade rumors" (1,900/mo, KD 23) is
  the target keyword, but Trade and Rumors are separate tags and the feed does
  ANY-of. `/tag/trade` serves that intent honestly — 54% of trade-tagged clusters
  already carry Rumors. The AND-semantics version stays available later if GSC
  says it is worth an API change.
- **No paginated URLs.** SSR the first 50, client "Load more", self-canonical.
  Avoids an entire category of pagination SEO problems on pages that top out
  around 100 items.

---

## TAG-1 — `/tag/[slug]`

- **Approach.** One dynamic route, **allowlisted to the eight known tag slugs**
  (`rumors`, `trade`, `injury`, `lineup`, `signing`, `waiver`, `game`,
  `barracuda`). Anything else `notFound()`s. An allowlist rather than a
  pass-through is what stops the route from minting an unbounded number of
  indexable URLs from arbitrary input.
- Server-render the 30-day set, `dynamic = 'force-dynamic'` +
  `fetchCache = 'default-cache'` for the same reason the homepage uses them (see
  `[[web-ssr-caching]]` — plain ISR bakes an empty page into the image).
- Per-tag title, description and `pageOpenGraph()`. Self-canonical.
  `/tag/trade` is written to target "San Jose Sharks trade news and rumors".
- A one-sentence intro above the list saying what the page collects and how often
  it updates, so the page is not purely a list of other people's headlines.
- **Empty state matters more here than on the homepage.** A thin tag in the
  offseason must read as "nothing this month" with a link back to the full feed,
  never as a broken page.
- **Verify.** All eight render; an unknown slug 404s; headlines appear in `curl`
  output; canonical is self, not the homepage.

## TAG-2 — Extract `ClusterList`

`FeedList` currently owns FilterBar + list + pagination together. Tag and player
pages want the list and pagination without the filter bar.

- **Approach.** Extract the list, skeletons, error, empty state and "Load more"
  into a `ClusterList` client component taking initial data plus a fixed filter
  set. `FeedList` keeps filter state and renders `ClusterList`; the new routes
  render it directly.
- **Do not** duplicate the list markup into the new routes — three copies of the
  pagination logic is how they drift apart.
- **Verify.** Homepage behaviour is unchanged: server markup adopted without a
  refetch, filters still work, URL still syncs.

## TAG-3 — "Browse by topic" footer nav

- **Approach.** A nav section in the footer linking all eight tag pages and the
  player page. This is the internal-linking path that makes the routes
  discoverable — without it they are orphans that only the sitemap knows about.
- Rendered on every page, so any entry point reaches them.
- **Verify.** Links present in server HTML on `/`, `/about`, `/legal`, `/submit`.

## TAG-4 — `/player/[slug]`, allowlisted to Celebrini

- **Approach.** Same shape as TAG-1, allowlist of exactly one:
  `macklin-celebrini`. Using `/player/[slug]` rather than a one-off
  `/macklin-celebrini` means adding a second player later is a one-line change
  with no URL migration.
- Title targets the realistic terms, not the head term. "macklin celebrini"
  (135k/mo, KD 44) is navigational and owned by NHL.com, ESPN and Wikipedia — it
  is **not** the target. "macklin celebrini contract" (1,300/mo, +212% YoY) and
  freshness-driven long tail are.
- **Care with a real person's page.** It aggregates third-party reporting about a
  living individual, exactly as the homepage does. State plainly that it collects
  published reporting and links to sources. Invent no biographical facts — the
  site holds a name, a slug and an entity type, nothing else. Any `Person` schema
  stays to what is verifiable.
- **Verify.** Renders with Celebrini's stories; any other slug 404s.

## TAG-5 — Sitemap entries, gated on live volume

- **Approach.** Add tag and player routes to `web/app/sitemap.ts`, each included
  only when its 30-day cluster count clears a threshold (**10**). Below it the
  page still renders and stays linked — it is simply not advertised for crawling
  until it has something to say.
- **Cheap counting trick:** request `?tags=<slug>&since=30d&limit=10` and test
  whether ten came back. That answers "≥10?" exactly, without a count endpoint or
  a 100-item payload, and keeps the sitemap's nine extra backend calls small on a
  Pi.
- `changeFrequency: 'daily'`, priority below the homepage.
- **Verify.** Rumors/Trade/Signing/Game/Barracuda and the player page appear
  today; Waiver/Injury/Lineup do not; all nine still return 200.

## TAG-6 — JSON-LD on the new routes

- **Approach.** `CollectionPage` + `ItemList` per page, reusing the pattern in
  `web/app/components/StructuredData.tsx`, with `isPartOf` pointing at the
  existing `#website` node so the graph stays connected.
- Still **no `NewsArticle`** — the site links out rather than hosting.
- **Verify.** Parses; no dangling `@id`s (walk referenced ids against defined
  ones, as in brief 12).

---

## Deploy notes

Web-only: `build web` then `up -d web`. Recent builds run ~40s.

`PUBLIC_SITE_URL` is already passed as both a build arg and a runtime env
(#124) — the new routes' canonicals depend on the build arg, since any page that
is not `force-dynamic` bakes its metadata at build time.

## After this brief

- **Relevance is now the blocker, not SEO.** Measured after deploying: 27% of
  `/tag/trade` and 32% of `/tag/rumors` are headlines naming another NHL team and
  not San Jose, admitted because a Sharks player's name appears in the title.
  A page promising "San Jose Sharks Trade News & Rumors" that is a quarter Oilers
  content will not hold a ranking it wins. See **RM-2** in
  `docs/IMPROVEMENT_PLAN.md` — start by querying `validation_logs`, where the
  shadow-mode LLM has already been recording its disagreements with the keyword
  check.
- Watch Search Console for which tag pages get impressions before building more.
- If the player page earns its keep, extend the allowlist — that is now a
  one-line change, by design.
- `tags_mode=all` for a dedicated `/tag/trade-rumors`, only if the data asks.
