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

---

# Round 2 review (external, 2026-06-15)

A second full review (Kimi) of the post-brief-1–9 codebase. Strengths confirmed:
SSRF guard, hashed-IP rate limiting, fail-closed admin auth, restricted prod CORS,
required secrets, auto-migrations, structured logging, nightly backups, pipeline
monitoring. The findings below are the **backlog for future tasks** — new ID
namespace `R2-*` so they don't collide with the S/C/P/Q/U/O ids above. Priorities
use the reviewer's matrix where given, otherwise High→P1, Medium→P2, Low→P3.

## R2 priority backlog

| ID | Pri | Area | Item |
|----|-----|------|------|
| R2-F1 | **P0** | Functionality | `ingest_html`/`ingest_api` are stubs that mark live `html`/`twitter`/`reddit` sources "broken" every cycle — false alerts. Skip or give them a distinct non-broken status. |
| R2-S1 | **P0** | Security | `ALLOWED_ORIGINS: "*"` in `docker-compose.pi.yml` — pin to the real public origin. |
| R2-O3 | **P1** | Operations | No backup integrity verification — add `gzip -t` per run + periodic test-restore. |
| R2-F2 | **P1** | Functionality | CapWages scrape is brittle and silently destructive — add structural + roster-size validation before deleting entities, and alert on failure. |
| R2-S7 | P1 | Security | BlueSky `atproto` re-authenticates on every `health_check()` — cache the session. |
| R2-O1 | P1 | Operations | No log aggregation/forwarding off the Pi — ship logs to a central store. |
| R2-F5 | P2 | Functionality | BlueSky posts only the oldest cluster per 15-min run — add a priority queue/batching. |
| R2-F3 | P2 | Functionality | No dedup across `/submit/link` and scheduled ingest — check submissions vs pending/raw_items. |
| R2-F4 | P2 | Functionality | `source_count` is incremented but never decremented after 30-day variant purge — derive by query. |
| R2-S2 | P2 | Security | Admin API key shared between Next.js proxy and API — consider rotation / asymmetric (JWT). |
| R2-S3 | P2 | Security | No request-body size limit on `/submit/link` — add a max length/middleware cap. |
| R2-S4 | P2 | Security | `fetch_guarded` does not pin sockets to the validated IP (TOCTOU) — pin via httpx transport or smokescreen. |
| R2-O4 | P2 | Operations | Redis password embedded in connection URL leaks to logs/crashes — use Redis ACLs / explicit auth. |
| R2-O2 | P2 | Operations | Backup runs an always-on `sleep` loop, not cron — move to cron (container or host). |
| R2-O5 | P2 | Operations | `task_time_limit=3600` too generous for RSS ingest — tighten per task type. |
| R2-U1 | P2 | Usability | No full-text search — Postgres `tsvector` or lightweight index. |
| R2-U2 | P2 | Usability | No dark mode — Tailwind `dark:` variants + toggle. |
| R2-U3 | P2 | Usability | "Load more" only — add page numbers / URL-synced infinite scroll for deep links. |
| R2-A4 | P2 | Architecture | No circuit breaker on OpenRouter calls — add one to avoid cascading failures. |
| R2-S5 | P3 | Security | Replace custom `safeEqual` in `middleware.ts` with `crypto.timingSafeEqual`. |
| R2-S6 | P3 | Security | Add CSP headers in `next.config.js`. |
| R2-O6 | P3 | Operations | No `deploy.resources.limits` in compose — cap CPU/mem so a runaway worker can't starve the Pi. |
| R2-O7 | P3 | Operations | `restart: unless-stopped` everywhere can restart-loop under disk/mem pressure — add `on-failure` + delay. |
| R2-U4 | P3 | Usability | No keyboard shortcuts (`j/k`, `/`, `?`). |
| R2-U5 | P3 | Usability | No PWA/offline support — service worker + manifest. |
| R2-U6 | P3 | Usability | RSS feed lacks `<lastBuildDate>` and `<ttl>`. |
| R2-U7 | P3 | Usability | No Open Graph / Twitter Card meta tags. |
| R2-F6 | P3 | Functionality | `entities_agg` ARRAY duplicates the `ClusterEntity` junction — derive it to avoid drift. |
| R2-F7 | P3 | Functionality | No dedup of BlueSky posts by content hash — re-created clusters could repost. |
| R2-F8 | P3 | Functionality | `cleanup_bogus_entities` uses Postgres-only regex `~ '[a-zA-Z]'` — abstract for portability. |
| R2-A1 | P3 | Architecture | Add API versioning (`/v1/...`). |
| R2-A2 | P3 | Architecture | Consider async SQLAlchemy for the API layer. |
| R2-A3 | P3 | Architecture | Add OpenAPI/Swagger tags. |
| R2-A5 | P3 | Architecture | Add distributed tracing (OpenTelemetry) RSS→enrich→cluster→post. |

## R2 P0/P1 implementation plan

Four items. R2-F1 and R2-S1 are independent and ship first (this branch).
R2-O3 builds on the now-merged backup service (`infra/backup/backup.sh`, brief 09).
R2-F2 is independent.

### R2-F1 (P0) — Stop unimplemented ingest methods alarming as "broken"

- **Problem.** The DB seed contains sources with `ingest_method` `html`, `twitter`,
  `reddit`. Every 10 min `ingest_all_sources` → `ingest_source`
  (`api/app/tasks/ingest.py`) dispatches them to `ingest_html`/`ingest_api`, which
  force `fetch_error_count >= 3`, so the admin view reports them `broken`. These are
  not broken — the method is simply unsupported. Brief 07 (C3) deliberately replaced
  the old silent no-op with this, so the fix adds a *distinct* state, not a revert.
- **Approach.** Add `SourceStatus.UNSUPPORTED`; exclude it from `get_active_sources`
  so it is never scheduled; stop bumping `fetch_error_count`; admin health reports
  it distinctly from `broken`. Migration flips existing non-RSS-method sources.
- **Verify.** A `ingest_method=HTML` source is not returned by `get_active_sources`,
  never reaches the broken threshold, and shows as `unsupported` in the admin summary.

### R2-S1 (P0) — Pin Pi CORS to the real public origin

- **Problem.** `docker-compose.pi.yml` sets `ALLOWED_ORIGINS: "*"`, fed into
  `CORSMiddleware` with `allow_credentials=True` — a spec-invalid, CSRF-prone combo.
  The browser only talks to the Next.js proxy, so FastAPI needs only the public origin.
- **Approach.** Pin to `https://wplepla23gjn.nobgp.com`; document in `.env.example`.
- **Verify.** A foreign `Origin` gets no `Access-Control-Allow-Origin`; the real one is echoed.

### R2-O3 (P1) — Backup integrity verification

- Build on `infra/backup/backup.sh`: `gzip -t` per run (fail loudly on corruption) +
  weekly test-restore into a throwaway DB with a sanity query; alert on failure.

### R2-F2 (P1) — Harden CapWages roster sync

- `fetch_capwages_roster` (`api/app/tasks/sync_roster.py`) keys off literal HTML
  markers and silently returns `None` / partially parses, then `remove_departed_players`
  wipes entities. Add structural validation + roster size-band/delta guard that aborts
  before any deletion, and alert (reuse brief 09 alerting) instead of `print`.

## R2 status tracking

All four R2 P0/P1 items are merged to `main` and deployed to production
(pi5-ai2) on 2026-06-15 — verified live: migration `0003` applied, the pinned
CORS origin echoes, and the backup `verify` test-restore passed.

| ID | Pri | Status | PR |
|----|-----|--------|----|
| R2-F1 | P0 | merged + deployed | [#70](https://github.com/davinoishi/Sharks-News-Aggregator/pull/70) |
| R2-S1 | P0 | merged + deployed | [#70](https://github.com/davinoishi/Sharks-News-Aggregator/pull/70) |
| R2-O3 | P1 | merged + deployed | [#71](https://github.com/davinoishi/Sharks-News-Aggregator/pull/71) |
| R2-F2 | P1 | merged + deployed | [#72](https://github.com/davinoishi/Sharks-News-Aggregator/pull/72) |
