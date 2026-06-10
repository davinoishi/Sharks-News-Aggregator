# Brief 04 — Feed query correctness and performance

Plan items: **C1, P1, P2, P3** (see `docs/IMPROVEMENT_PLAN.md`).

## Task

Fix duplicate clusters in filtered feeds, eliminate N+1 query patterns, drop the
per-request full count, and replace offset "cursors" with keyset pagination.

## Context

- Feed endpoint: `GET /feed` in `api/app/main.py` → `build_feed_query()` and
  `format_cluster_for_feed()` in `api/app/core/queries.py`.
- **C1 (bug):** `build_feed_query` does `query.join(ClusterTag).filter(ClusterTag.tag_id.in_(tag_ids))`
  (same pattern for entities). A cluster having 2+ of the requested tags is
  returned once per matching tag, and `query.count()` is inflated, corrupting
  pagination. Reproduce: two tags on one cluster, request `?tags=a,b`.
- **P1 (N+1):** `format_cluster_for_feed` reads `cluster.cluster_tags` /
  `cluster.cluster_entities` lazily — ~2 extra queries per cluster, ~100+ per
  page. An unused eager-load helper `get_cluster_with_details()` already exists
  in `queries.py`. Admin endpoints in `main.py` also do per-row queries:
  `/admin/validations` re-queries `RawItem` per log despite joining it,
  `/admin/bluesky/posts` queries `Cluster` per post, `/admin/sources` runs a
  count per source.
- **P2:** `/feed` runs `query.count()` on every request only to compute
  `has_more`. Also, a `feed_cache` model exists (`api/app/models/feed_cache.py`)
  and is cleaned hourly by `app/tasks/maintenance.py`, but nothing ever writes
  or reads it.
- **P3:** the feed "cursor" is a stringified offset. Clusters re-sort by
  `last_seen_at` as stories update, so offsets skip/duplicate entries between
  pages.
- The frontend (`web/app/api-client.ts`, `web/app/page.tsx`) currently sends no
  cursor and ignores `has_more` — you are free to change the cursor format, but
  keep the response shape `{clusters, cursor, has_more}`.

## Requirements

1. **C1:** rewrite tag/entity filters as `EXISTS` subqueries (preferred) or
   joins with `.distinct()` on the cluster. Semantics: a cluster matches if it
   has ANY of the requested tags AND ANY of the requested entities (current
   intended behavior). Also: when the requested slug list resolves to zero
   known tags/entities, return an **empty feed**, not an unfiltered one (the
   current code silently drops the filter — fix this and note it in the PR).
2. **P1:** eager-load tags+entities for the feed page in one or two queries
   (`selectinload`). Fix the three admin N+1s with joins/grouped aggregates.
3. **P2:** drop `count()`; fetch `limit + 1` rows and derive `has_more`.
   Either wire up `feed_cache` for the default (no-filter) feed page or delete
   the model + maintenance task — decide based on measured benefit on a Pi;
   deleting is acceptable, state the decision in the PR.
4. **P3:** keyset pagination on `(last_seen_at, id)` descending. Cursor =
   opaque base64 of `last_seen_at_iso:id`. Tolerate old numeric cursors
   gracefully (treat as no cursor) since clients may have them cached.
5. Tests (pytest, however the suite is organized when you start — create
   `api/tests/` if none exists): duplicate-tag cluster appears once; unknown
   slug returns empty; pagination walks the full set without skips/dupes while
   a cluster's `last_seen_at` changes mid-walk; query counts for a feed page
   are bounded (use SQLAlchemy event listener to count statements).

## Out of scope

- Frontend changes (brief 08 adds Load More using your cursor).
- Auth/rate limiting (brief 01), refactoring main.py (brief 07).
- Caching layers beyond the feed_cache decision above.

## Verification

- All tests pass (`pytest api/`).
- Manual: seed a cluster with two tags, `curl 'localhost:8001/feed?tags=x,y'`
  → cluster appears once.
- Log SQL (`echo=True` temporarily) for one `/feed` request → tag/entity loads
  are constant-count, not per-cluster.
- `/feed?limit=2` then follow `cursor` until `has_more=false` → union of pages
  equals the full set, no duplicates.

## Deliverable

Branch `improve/04-feed-queries`, PR against `main` with before/after query
counts for a 50-cluster page. Update the status table in
`docs/IMPROVEMENT_PLAN.md`.
