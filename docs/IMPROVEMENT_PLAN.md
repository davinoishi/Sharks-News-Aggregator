# Sharks News Aggregator — Improvement Plan

This plan is the result of a full codebase review (2026-06-10) covering security,
correctness, performance, usability, code quality, and operations. Work is packaged
into nine self-contained briefs in `docs/briefs/`, each scoped to a single PR.

**How to use:** start a fresh agent session, point it at exactly one brief file, and
have it deliver a branch + PR against `main`. Do not combine briefs in one session.
Each brief contains its own context, requirements, out-of-scope list, and
verification steps.

## Execution order

| # | Brief | Items | Effort | Depends on |
|---|-------|-------|--------|------------|
| 1 | [brief-01-admin-auth-and-rate-limiting.md](briefs/brief-01-admin-auth-and-rate-limiting.md) | S1, S3 | M | — (do first) |
| 2 | [brief-02-ssrf-submit-link.md](briefs/brief-02-ssrf-submit-link.md) | S2 | S–M | — |
| 3 | [brief-03-docker-hardening-and-hygiene.md](briefs/brief-03-docker-hardening-and-hygiene.md) | S4, S5 | S | — |
| 4 | [brief-04-feed-query-fixes.md](briefs/brief-04-feed-query-fixes.md) | C1, P1, P2, P3 | M | — |
| 5 | [brief-05-ci-pipeline.md](briefs/brief-05-ci-pipeline.md) | Q2 | S–M | — (do early) |
| 6 | [brief-06-test-suite.md](briefs/brief-06-test-suite.md) | Q1 | L | Brief 5 |
| 7 | [brief-07-refactors.md](briefs/brief-07-refactors.md) | Q3, Q4, C2, C3, C6 | L | Briefs 5, 6 |
| 8 | [brief-08-ux-round.md](briefs/brief-08-ux-round.md) | U1–U6 | M–L | Brief 4 |
| 9 | [brief-09-ops-and-observability.md](briefs/brief-09-ops-and-observability.md) | O1, O2, O3, C4, C5 | M | — |

Effort scale (Opus-class agent): **S** = under ~1 hour, **M** = 1–3 hours,
**L** = multi-session / a day or more.

### Sequencing rules

- Briefs 1–3 (security) ship before any UX work. The admin surface is effectively
  exposed today.
- Brief 5 (CI) lands first or in parallel with brief 1 so every later PR gets checks.
- Brief 6 (tests) **must** merge before brief 7 (refactors) starts.
- Briefs 1 and 7 both touch `api/app/main.py`; merge one before starting the other.
- Briefs 2, 3, 4, 9 are independent and can run in parallel sessions if they stay on
  separate branches.

## Architecture context (read before any brief)

- **Stack:** FastAPI + SQLAlchemy + Celery (`api/`), Next.js 14 App Router (`web/`),
  Postgres 16, Redis 7, all via `docker-compose.yml`. Deployed on a Raspberry Pi 5
  behind a nobgp tunnel.
- **Proxy design:** the browser never talks to FastAPI. All requests go through
  Next.js API routes (`web/app/api/*/route.ts`) which forward to
  `INTERNAL_API_URL` (the `api` container). Consequence: **FastAPI never sees the
  real client IP** — `request.client.host` is the Next.js container or tunnel IP.
- **Pipeline:** Celery Beat → `ingest_all_sources` (RSS, every 10 min) →
  `enrich_raw_item` (entity extraction, LLM relevance/classification via OpenRouter,
  clustering) → clusters served by `/feed`. A BlueSky bot posts new clusters.
- **LLM:** OpenRouter (`api/app/services/openrouter.py`) with keyword fallback;
  relevance check fails open (approves) on LLM errors by design.
- **No tests, no CI workflows exist today** (only dependabot).

## Findings register

The full review report follows. IDs (S1, C1, …) are referenced by the briefs.

### Security

- **S1 — Admin auth is broken-or-open.** `check_admin_access()` in
  `api/app/main.py` trusts `request.client.host` against an IP allowlist with broad
  defaults (`192.168.0.0/24`, `10.0.0.0/8`). Behind the Next.js proxy the backend
  only ever sees the proxy IP, so the allowlist is either always-deny or
  always-allow. The Next.js admin proxy (`web/app/api/admin/sources/route.ts`)
  forwards with no credential, so if the container IP is allowlisted, every visitor
  to `/admin/sources` is an admin.
- **S2 — SSRF via `/submit/link`.** Submitted URLs are fetched server-side by the
  submissions worker with no scheme/host/IP validation.
- **S3 — Rate limiting keyed on the wrong IP.** `/submit/link` limits by
  `request.client.host` — all users share the proxy IP (10/hour site-wide).
  `/metrics/pageview` and `/cluster/{id}/click` have no limits at all and can be
  spammed to fake trending.
- **S4 — Postgres (5432) and password-less Redis (6379) published to the host/LAN**
  in `docker-compose.yml`.
- **S5 — Hygiene:** 403 bodies echo client IPs; admin key compared with `==`
  (timing); no security headers in `next.config.js`; raw submitter IPs stored.

### Correctness & reliability

- **C1 — Duplicate clusters in filtered feeds.** `build_feed_query()` in
  `api/app/core/queries.py` joins `ClusterTag`/`ClusterEntity` with `.in_()` —
  a cluster matching two requested tags appears twice and inflates `count()`.
- **C2 — Naive `datetime.utcnow()` everywhere**; deprecated, and the cause of
  scattered `.replace(tzinfo=None)` patches.
- **C3 — Stub endpoints:** `/admin/candidate-sources` returns hardcoded empties,
  approve/reject return 501; `ingest_html`/`ingest_api` are TODO stubs.
- **C4 — `print()` instead of logging** throughout Celery tasks.
- **C5 — LLM pipeline fragility:** fail-open is silent (no alert/metric);
  `_parse_llm_approved()` in `main.py` string-matches stored JSON.
- **C6 — Alembic installed but unused**; schema managed by raw SQL init files,
  a manual migration file, and ad-hoc scripts.

### Performance

- **P1 — N+1 queries:** `format_cluster_for_feed` lazy-loads tags/entities per
  cluster; `/admin/validations`, `/admin/bluesky/posts`, `/admin/sources` issue
  per-row queries.
- **P2 — Full `count()` on every `/feed` request** just to compute `has_more`;
  `feed_cache` model exists but is never used (only cleaned).
- **P3 — "Cursor" is a stringified offset**; shifting clusters cause skips/dupes.

### Usability

- **U1 —** Frontend ignores `has_more`/`cursor`; users can never see past 50 stories.
- **U2 —** Entity (player) filtering exists in the API but has no UI.
- **U3 —** Headlines aren't links; no `aria-expanded` on expanders.
- **U4 —** Filter changes blank the list behind a spinner; raw error strings shown.
- **U5 —** No published RSS/Atom feed of the aggregated clusters.
- **U6 —** Fixed `ml-20` misaligns on mobile; tag colors via `color + '20'` alpha
  can fail contrast; no dark mode.

### Code quality

- **Q1 —** Zero tests. Highest-value targets: URL normalization/dedup, clustering,
  feed filters, `parse_since_parameter`, LLM JSON parsing.
- **Q2 —** No CI workflows; Dependabot PRs merge unchecked.
- **Q3 —** `main.py` is 1,126 lines; admin auth is a manual call per endpoint
  (auth-bypass-by-omission risk) instead of a FastAPI dependency.
- **Q4 —** `enrich.py` is 1,240 lines mixing extraction, classification, clustering.

### Operations

- **O1 —** Production compose bind-mounts source and runs `watchfiles` reloaders.
- **O2 —** No automated Postgres backups; Pi SD card is the only copy.
- **O3 —** Nothing watches `/health` or alerts on stale `last_scan_at` / broken
  sources.

## Status tracking

**All nine briefs are complete and merged to `main`** (2026-06-12).

Security briefs 1–3 were integrated and conflict-resolved on one branch (brief S)
and shipped via the integration PR
[#55](https://github.com/davinoishi/Sharks-News-Aggregator/pull/55), which
**superseded** the individual PRs #52/#53/#54.

| Brief | Status | PR |
|-------|--------|----|
| 1 | ✅ merged | [#52](https://github.com/davinoishi/Sharks-News-Aggregator/pull/52) via [#55](https://github.com/davinoishi/Sharks-News-Aggregator/pull/55) |
| 2 | ✅ merged | [#53](https://github.com/davinoishi/Sharks-News-Aggregator/pull/53) via [#55](https://github.com/davinoishi/Sharks-News-Aggregator/pull/55) |
| 3 | ✅ merged | [#54](https://github.com/davinoishi/Sharks-News-Aggregator/pull/54) via [#55](https://github.com/davinoishi/Sharks-News-Aggregator/pull/55) |
| 4 | ✅ merged | [#60](https://github.com/davinoishi/Sharks-News-Aggregator/pull/60) |
| 5 | ✅ merged | [#61](https://github.com/davinoishi/Sharks-News-Aggregator/pull/61) |
| 6 | ✅ merged | [#62](https://github.com/davinoishi/Sharks-News-Aggregator/pull/62) |
| 7 | ✅ merged | [#63](https://github.com/davinoishi/Sharks-News-Aggregator/pull/63) |
| 8 | ✅ merged | [#65](https://github.com/davinoishi/Sharks-News-Aggregator/pull/65) |
| 9 | ✅ merged | [#66](https://github.com/davinoishi/Sharks-News-Aggregator/pull/66) |

### Follow-ups after the briefs

| Change | PR |
|--------|----|
| Exclude the synthetic "User Submissions" source from ingestion + the brief-09 health check (it was tripping `/health` → `degraded`) | [#67](https://github.com/davinoishi/Sharks-News-Aggregator/pull/67) |
