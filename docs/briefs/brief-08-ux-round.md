# Brief 08 — Frontend UX round

Plan items: **U1–U6** (see `docs/IMPROVEMENT_PLAN.md`). Depends on brief 04
(keyset cursor) being merged for U1; everything else is independent.

## Task

Make the feed fully browsable (pagination), add player filtering, make
headlines clickable, smooth out loading states, publish an RSS feed of the
aggregator, and do a mobile/contrast pass.

## Context

- Frontend: Next.js 14 App Router, Tailwind, all client-side in
  `web/app/page.tsx` (state + fetching), `web/app/components/ClusterCard.tsx`,
  `web/app/components/FilterBar.tsx`, `web/app/api-client.ts`. Data flows
  through Next.js proxy routes in `web/app/api/`.
- Backend `/feed` supports `tags`, `entities` (comma-separated slugs), `since`,
  `limit`, `cursor` and returns `{clusters, cursor, has_more}`. After brief 04
  the cursor is an opaque keyset token. Entity data is already in every
  cluster payload (`entities: [{id, name, slug, type}]`).
- `ApiClient.getFeed` ignores `cursor`/`has_more`; the page fetches 50 and
  stops (U1). FilterBar offers only tags + time window (U2). Headlines are
  plain text; users must click "View sources" then a link (U3). Every filter
  change blanks the list behind a spinner; errors render raw
  `Failed to fetch feed: <statusText>` (U4). No RSS output exists (U5).
  Header tagline uses fixed `ml-20`; tag chip colors are `tag.color + '20'`
  background with `tag.color` text — contrast unverified; no dark mode (U6).
- The deployed site is used primarily on phones.

## Requirements

1. **U1 — Load more:** append-style pagination using `cursor`/`has_more`
   ("Load more" button is sufficient; infinite scroll optional). Filter
   changes reset pagination. Keep `limit` at 50.
2. **U2 — Player/entity filtering:**
   - Entity chips on cluster cards become clickable → sets the entity filter.
   - FilterBar shows the active entity filter with a clear (×) control and a
     searchable entity picker. Backend: add a small public
     `GET /entities?query=` endpoint (the query helper
     `search_entities_by_name` already exists in `api/app/core/queries.py`)
     plus a Next.js proxy route — this is the one backend change allowed in
     this brief.
   - Reflect tag/entity/since filters in the URL query string so filtered
     views are shareable/bookmarkable.
3. **U3 — Clickable headlines + a11y:** headline links to the top-ranked
   source (first variant by the existing official→press→other ordering;
   fetch detail lazily on click or include a `top_url` — prefer whatever
   avoids an extra request before navigation, document the choice). Record
   the click via `recordClusterClick`. Expand buttons get `aria-expanded`
   and visible focus styles; cards remain keyboard-navigable.
4. **U4 — Loading/error polish:** keep previous results visible (dimmed)
   while refetching instead of blanking; skeleton cards on first load;
   friendly error copy with a retry button (no raw statusText). Adopting SWR
   or React Query is allowed but not required — judge by whether it reduces
   code.
5. **U5 — RSS output:** backend `GET /rss` (RSS 2.0, latest ~50 clusters:
   headline, link to top source, pubDate=last_seen_at, category=event_type)
   + Next.js proxy at `/rss` with `Content-Type: application/rss+xml` and
   ~5-minute caching. Add `<link rel="alternate" type="application/rss+xml">`
   in `layout.tsx` and a footer link.
6. **U6 — Visual pass:** fix the `ml-20` tagline alignment on narrow screens;
   replace the alpha-suffix tag coloring with a scheme that guarantees
   readable contrast (e.g. fixed light bg + dark text per tag hue, or
   compute luminance); verify the layout at 360px width. Dark mode is
   optional — only if `prefers-color-scheme` support is cheap; do not build
   a toggle.

## Out of scope

- Backend feed query internals (brief 04), auth (brief 01).
- The admin UI.
- New pages, accounts, comments, or notifications.

## Verification

- `npm run build` and `npx tsc --noEmit` pass; CI green.
- Manual walkthrough against `docker compose up` (or preview):
  - Scroll → Load more appends without duplicates; switching filters resets.
  - Click a player chip → feed filters; URL contains the filter; reload
    preserves it; × clears it.
  - Click a headline → opens the top source in a new tab; click recorded.
  - Throttle network → skeletons on first load, stale-while-refetch on
    filter change, friendly error + retry when API is stopped.
  - `curl localhost:3001/rss` → valid RSS (validate with an RSS validator or
    `xmllint`); feed readers can subscribe.
  - 360px viewport: header, cards, filter bar all usable; tag chips readable.
- Keyboard-only pass: tab to a card, expand sources, open a link.

## Deliverable

Branch `improve/08-ux`, PR against `main` with before/after screenshots
(desktop + 360px mobile). Update the status table in
`docs/IMPROVEMENT_PLAN.md`.
