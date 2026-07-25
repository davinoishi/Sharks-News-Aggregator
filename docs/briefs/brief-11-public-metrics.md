# Brief 11 — Richer public metrics, without cookies

Plan items: **MET-1 … MET-7** (see `docs/IMPROVEMENT_PLAN.md`).

**Ship as two PRs, one per session:**

| Phase | Scope | Items | Effort |
|-------|-------|-------|--------|
| **A** | Derived stats from data already in the DB + the footer redesign | MET-1, MET-2, MET-3 | M |
| **B** | New cookie-free collection: daily rollups, referrers, filter popularity, external counts | MET-4, MET-5, MET-6, MET-7 | M–L |

Phase A adds **no new data collection of any kind** and can merge on its own.
Phase B introduces new (still non-personal, still cookie-free) collection and
therefore also changes the privacy policy.

## Task

The feed footer publishes three numbers — visits, stories tracked, sources
(`web/app/page.tsx:324`). Expand that into a set of genuinely interesting public
metrics while keeping the site's no-cookie, no-consent-banner posture intact.

## Context

### What exists today

- `GET /stats` (`api/app/routers/metrics.py:14`) returns exactly three fields,
  modelled by `SiteStatsResponse` (`api/app/schemas.py:84`) and consumed by
  `web/app/types.ts:47` → rendered as one line at `web/app/page.tsx:324`.
- `site_metrics` (`api/app/models/site_metrics.py`) is a flat key→value counter
  table. **No date dimension**, so "visits today" is currently impossible.
  `page_views` is incremented by the beacon at `api/app/routers/metrics.py:44`;
  `total_stories` by the clustering path at `api/app/enrichment/clustering.py:799`.
- **`clusters.click_count` is already collected and surfaced nowhere.** It is
  written by `record_cluster_click()` (`api/app/routers/metrics.py:88`) and read
  by no endpoint. Free signal currently going in the bin.
- `validation_logs` holds every relevance decision with an indexed `created_at`
  (`api/app/models/validation_log.py:71`) — the raw material for a
  "screened vs published" ratio.
- `idx_clusters_status_last_seen ON clusters(status, last_seen_at DESC)` already
  exists (`infra/postgres/init/001_init.sql:134`), so time-windowed cluster
  aggregates have index coverage.

### The privacy position (this is the point of the brief)

Consent obligations attach to **storing or reading anything on the visitor's
device** and to **processing personal data** (IPs included). The site currently
avoids both, and `web/app/legal/page.tsx` §6.1–6.2 says so publicly, including
the commitment: *"If analytics are added in the future, this policy will be
updated."* Phase B must honour that.

Everything in this brief is designed so that **no visitor is ever identified,
counted individually, or distinguished from another visitor.** Only aggregate
counters and content-derived statistics.

---

## Phase A — derived stats (zero new collection)

### MET-1 — expand `/stats`

Keep `page_views`, `total_stories`, `total_sources` in the response — the
frontend depends on them and they are the only lifetime figures that survive
retention. Add:

| Field | Derivation |
|---|---|
| `stories_24h`, `stories_7d` | count of active clusters by `last_seen_at` |
| `top_story_24h` | max `clusters.click_count` in window → `{cluster_id, headline, click_count}` |
| `top_entity_7d` | `cluster_entities` join → `{name, slug, story_count}` |
| `event_type_breakdown_7d` | `clusters.event_type` group-by |
| `top_source_7d` | `story_variants.source_id` group-by → source name |
| `screened_30d`, `published_30d` | `validation_logs` total vs `result='approved'` |
| `median_minutes_to_surface` | `raw_items.published_at` → cluster creation, 7d median |
| `entities_tracked` | `entities` count |
| `last_updated_at` | reuse `check_pipeline_health(db).last_scan_at` |

### MET-2 — cache `/stats`

**Non-negotiable.** `/stats` is called on every page load and this turns it from
one trivial query into ~9 aggregates on a Raspberry Pi. Cache the whole payload
in Redis (already in the stack) with a ~5 minute TTL — this is R3-P2 applied to
a hotter endpoint. Serve stale on a Redis miss rather than 500ing; stats are
decorative and must never take the feed page down.

Note there is an unused `feed_cache` model in the codebase (flagged under P2).
Use Redis, not that table — do not resurrect it here.

### MET-3 — footer presentation

Stay with the single footer strip at `web/app/page.tsx:324`; **do not build a
dedicated `/stats` page** in this brief. Make it two compact lines, e.g.:

```
1,284 stories tracked · 33 sources · 47 players mentioned · updated 4 min ago
Today: 12 new stories · most read "…" · most mentioned: Celebrini
```

Requirements: every figure degrades gracefully to hidden when null (a fresh
database has no top story); no layout shift while `/stats` is in flight; keep
the existing muted footer styling; readable on mobile.

---

## Phase B — new collection (cookie-free)

### MET-4 — daily rollup table

New `metric_daily` table: `(key, day, value)`, unique on `(key, day)`, with an
Alembic migration following the existing `YYYYMMDD_NNNN_description.py`
convention. Write alongside the existing lifetime counters — do not replace
them — so `page_views` keeps its meaning.

Roll up at minimum: `page_views`, `cluster_clicks`. This is what makes
"visits today" and any future sparkline possible. Pure integers keyed by date;
no visitor dimension, now or later.

### MET-5 — referrer hosts

**Trap:** the pageview beacon POSTs to the Next.js proxy, so the request's own
`Referer` header is *your own page*. Reading it server-side yields 100% self-
referrals. The true value must be read client-side from `document.referrer` and
sent explicitly in the POST body.

- Store the **host only** — never the path, never the query string.
- Drop self-referrals and empty referrers (direct traffic → count as `direct`).
- Cap length, allowlist-normalise obvious variants (`m.facebook.com` →
  `facebook.com`), and store as a `metric_daily` key like `ref:bsky.app`.
- Publish only the top ~5; a long-tail referrer host with one hit is closer to
  identifying an individual visitor than an aggregate.

### MET-6 — filter popularity

Count `tags=` / `entities=` parameter usage on `/feed` into `metric_daily`
(`filter:tag:trade`). Requires bot filtering (below). Publish as "most-used
filter this week".

### MET-7 — external counts

- **RSS subscribers:** feed readers advertise counts in their User-Agent
  (`Feedly/1.0 (+http://...; 34 subscribers)`). Regex the UA on `/rss`, keep the
  max seen per reader per day, sum for a subscriber estimate.
- **Bluesky followers:** fetch via the existing atproto client on the Celery
  schedule, store in `site_metrics`. Reuse a cached session — do **not** add
  another auth-per-call (that is R2-S7, already an open complaint).

### Bot filtering

Server-side counting (MET-6, MET-7) is exposed to crawlers in a way the existing
JS beacon is not — the beacon is accidentally a decent bot filter because
crawlers don't execute it. Add one shared UA-denylist helper and apply it to
every server-side counter, or the numbers are fiction.

### Privacy policy update

Update `web/app/legal/page.tsx` §6.2 to describe exactly what is now counted:
aggregate page/click counts by day, referrer hosts, filter usage — no cookies,
no device storage, no visitor identifiers, no third-party analytics. The
existing "if analytics are added, this policy will be updated" line is a
promise; keep it accurate.

---

## Hard constraints (both phases)

1. **No cookies, no `localStorage`, no `sessionStorage`, no IndexedDB.** The
   consent rule is about device storage, not the word "cookie."
2. **No fingerprinting** — no canvas, screen-size, font, or UA-entropy hashing.
   This is the most consent-triggering technique there is.
3. **No per-visitor identifier, including hashed or rotating ones.** Unique
   visitors via a daily-rotating salted IP hash (the Plausible/Fathom pattern)
   was **considered and explicitly rejected** for this brief. Do not add it as a
   helpful extra.
4. **No third-party analytics** — no Google Analytics (consent-required in the
   EU even in cookieless mode), no hosted script tags of any kind.
5. **No new IP handling.** `hash_client_ip()` keeps its current rate-limiting
   role and gains no analytics role.
6. Nothing published at a granularity that could single out one visitor.

## Out of scope

- Unique visitors / sessions / bounce rate / time-on-page — all require either
  device storage or a visitor identifier.
- A dedicated `/stats` page or charts (MET-3 is the footer only).
- Geographic breakdown — needs IP geolocation, i.e. personal data processing.
- Per-source click-through analytics beyond the existing `click_count`.
- Backfilling historical daily rollups; `metric_daily` starts from deploy.
- Admin-facing dashboards (`/admin/*` already has its own stats).

## Verification

**Phase A**

- `cd api && PYTHONPATH=. pytest -q` passes; new aggregate tests run under the
  `requires_postgres` marker with the `pg_db` fixture (`api/tests/conftest.py`).
- `EXPLAIN ANALYZE` each new aggregate: confirm
  `idx_clusters_status_last_seen` is used and nothing does a sequential scan
  over `validation_logs`.
- Hit `/stats` twice; the second is served from Redis (verify by log or by
  timing). Stop Redis → `/stats` still returns, does not 500, and the feed page
  still renders.
- Seed an empty database → footer hides null figures rather than showing
  "null" or "0 stories".
- **Retention check:** confirm `total_stories` still shows the lifetime counter
  and not `COUNT(clusters)`. The 30-day purge
  (`api/app/tasks/maintenance.py:35`) means those differ by an order of
  magnitude, and silently swapping one for the other would look like data loss.

**Phase B**

- `alembic upgrade head` / `downgrade -1` both clean against a populated DB.
- Load the page from an external referrer → the correct host is recorded; load
  it via internal navigation → no self-referral row appears.
- Confirm no full referrer URL or query string is ever persisted
  (`grep` the stored keys).
- Curl `/rss` with a Feedly-style UA → subscriber count parsed; with a
  known-bot UA → not counted.
- DevTools → Application: **zero** cookies and zero storage entries after a
  full session including filtering and clicking through to a story.
- Privacy policy §6.2 matches what the code actually does.

## Deliverable

Two PRs against `main`, one per session:

- **Phase A** — branch `improve/11a-derived-stats`, PR with the `EXPLAIN
  ANALYZE` transcript and a screenshot of the new footer.
- **Phase B** — branch `improve/11b-metrics-collection`, PR with the migration,
  the DevTools storage screenshot showing nothing stored, and the privacy-policy
  diff.

Update the status table in `docs/IMPROVEMENT_PLAN.md`.
