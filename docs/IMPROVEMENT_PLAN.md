# Sharks News Aggregator — Improvement Plan

This plan is the result of a full codebase review (2026-06-10) covering security,
correctness, performance, usability, code quality, and operations. Work is packaged
into nine self-contained briefs in `docs/briefs/`, each scoped to a single PR.
Later reviews and feature work append to this file; see
[brief 10](#brief-10--mcp-interface-for-agent-access-planned-2026-07-25),
[brief 11](#brief-11--richer-public-metrics-without-cookies-planned-2026-07-25),
[brief 12](#brief-12--make-the-feed-crawlable-and-give-it-metadata-planned-2026-07-27) and
[brief 13](#brief-13--crawlable-tag-routes-and-one-player-page-planned-2026-07-27)
for the current planned work.

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
| R2-U1 | P2 | Usability | No full-text search — Postgres `tsvector` or lightweight index. **→ scoped in [brief 10](briefs/brief-10-mcp-interface.md), phase A.** |
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

---

# Round 3 review (external, Qwen, 2026-07-23)

A third review of the codebase. It re-confirmed the strong security/ops posture and
correctly flagged that most of its suggestions already live in the `R2-*` backlog or
`RM-1`. The items below are the ones **not already tracked** — new ID namespace
`R3-*`. These are captured for completeness; **not all will be executed** (several are
larger product bets or lower-value). Priorities are the reviewer's impact rating
mapped High→P1/P2, Medium→P2/P3, plus judgment; nothing here is P0.

**Already covered — not re-listed** (mapped to existing IDs): full-text search
(R2-U1), Bluesky batch posting (R2-F5), Threads via RSSHub (RM-1), dark mode (R2-U2),
OG/Twitter cards (R2-U7), PWA (R2-U5), keyboard shortcuts (R2-U4), infinite scroll
(R2-U3), RSS `<lastBuildDate>`/`<ttl>` (R2-U6), SSRF IP pinning (R2-S4), body-size
limit (R2-S3), admin key rotation/JWT (R2-S2), Redis ACLs (R2-O4), `timingSafeEqual`
(R2-S5), keyset pagination (P3), `feed_cache` usage (P2), async SQLAlchemy (R2-A2),
tighten Celery time limits (R2-O5), `deploy.resources.limits` (R2-O6),
`restart: on-failure` (R2-O7), Bluesky session caching (R2-S7), log aggregation
off-Pi (R2-O1), API versioning (R2-A1), OpenRouter circuit breaker (R2-A4),
OpenTelemetry (R2-A5), derive `source_count` by query (R2-F4), dedup `entities_agg`
(R2-F6), CSP headers (R2-S6).

## R3 backlog

| ID | Pri | Area | Item |
|----|-----|------|------|
| R3-O1 | **P1** | Operations | Automated **off-device** backups. `docs/BACKUP_RESTORE.md` documents rsync/rclone but it's manual — add a nightly `rclone copy ./backups remote:sharks-backups/` to the backup script. Pi hardware failure is the single biggest data-loss risk. |
| R3-A1 | P2 | Code quality | Remove `db_data_export.sql` from the repo root — a stale SQL dump is a data-leak risk and bloats clones. Move to private backup or `.gitignore` it. |
| R3-S1 | P2 | Security | Add `pip-audit -r requirements.txt` as a CI step to catch newly-disclosed CVEs in pinned deps. |
| R3-S2 | P2 | Security | Rate-limit the unauthenticated `GET /rss` per-IP (reuse the existing in-memory limiter) to prevent scraping abuse. |
| R3-P1 | P2 | Performance | Explicit SQLAlchemy pool tuning (`pool_size`, `max_overflow`, `pool_pre_ping=True`) — defaults (5, no pre-ping) leave stale connections after idle on the Pi. |
| R3-O2 | P2 | Operations | External uptime monitoring (UptimeRobot / healthchecks.io) pointed at `/api/health`; wire the `degraded` flag to a phone notification. |
| R3-O3 | P2 | Operations | Automated deploy pipeline — GitHub Actions (or self-hosted runner) on merge to `main`: `git pull && docker compose build && docker compose up -d`. Removes manual Pi deploys. |
| R3-T1 | P2 | Testing | End-to-end pipeline integration test: seed a mock RSS source → ingest → assert enrichment → assert clustering → assert `/feed` returns it. |
| R3-T2 | P2 | Testing | Frontend component tests (Vitest + `@testing-library/react`) for `FilterBar`, `ClusterCard`, entity picker — currently zero frontend tests. |
| R3-F1 | P2 | Feature | Push notifications on new high-priority clusters (trades/injuries/signings) via ntfy.sh — one HTTP POST from the Bluesky task or a parallel task. |
| R3-O4 | P3 | Operations | Healthcheck for the `web` container (`wget -q --spider http://localhost:3000/`) so Docker can auto-restart a hung Next.js. |
| R3-O5 | P3 | Operations | Multi-stage Docker build for the API image — compile lxml/psycopg wheels in a builder stage, copy to a clean runtime image (~200MB smaller). |
| R3-P2 | P3 | Performance | Redis-cache hot read queries (`/entities?query=`, roster list) with ~5-min TTL — they change daily at most. |
| R3-P3 | P3 | Performance | Batch queued LLM classifications into one OpenRouter prompt ("classify these N headlines") to cut API calls/latency. |
| R3-S3 | P3 | Security | Add CSP `report-uri`/`report-to` + a `/csp-report` endpoint for visibility into violations (extends R2-S6). |
| R3-A2 | P3 | Code quality | Extract a thin `services/` layer (`feed_service`, `cluster_service`) so routers stop calling enrichment/clustering directly — easier unit testing. |
| R3-A3 | P3 | Code quality | Enforce Pydantic v2 `model_config = ConfigDict(from_attributes=True)` + strict validation across response schemas to catch shape mismatches at dev time. |
| R3-U1 | P3 | Usability | ~~Relative timestamps ("2h ago" / "Yesterday") via `date-fns` `formatDistanceToNow`.~~ **Conflicts with brief 12.** Once the feed is server-rendered under ISR, a relative string computed server-side is stale on arrival and mismatches on hydrate; brief 12 deliberately moves the one remaining relative string to an absolute datetime. If this is ever revived it must be a client-only effect over a server-rendered `<time datetime>`, never a server-rendered string. |
| R3-U2 | P3 | Usability | Source credibility tier indicators (official 🏒 / press 📰 / blog ✍️) to help gauge reliability at a glance. |
| R3-U3 | P3 | Usability | Cluster "Breaking"/🔥 importance badge when `source_count >= 4` or a trade/injury within the last ~2h. |
| R3-T3 | P3 | Testing | Load test `/feed` (k6/locust, ~50 concurrent) to validate the Pi under concurrency. |
| R3-T4 | P3 | Testing | Contract/snapshot test for the OpenRouter JSON response shape so parser breakage surfaces loudly. |
| R3-T5 | P3 | Testing | Mutation testing (`mutmut`) on `enrichment/clustering.py` — the core IP — to confirm tests catch logic bugs. |
| R3-F2 | P3 | Feature | "Around the League" secondary feed/tab for non-Sharks NHL news that passes a broader relevance filter (league-wide sources already ingested). |
| R3-F3 | P3 | Feature | Podcast/video source ingestion — YouTube RSS (Sharks TV, NHL Network) + podcast feeds, tagged `video`/`audio` for filtering. |
| R3-F4 | P3 | Feature | Lightweight user preferences (localStorage, no auth) — star players, mute tags, "my feed" defaults. Full accounts a later step. |
| R3-F5 | P3 | Feature | Game-day mode — pinned "Game Day" card with score/period/live links from the NHL API (`api-web.nhle.com`) during Sharks games. |
| R3-F6 | P3 | Feature | Weekly digest email — Celery Beat (Sunday PM) compiling top clusters into an HTML email via aiosmtplib / Resend / Mailgun. |
| R3-F7 | P3 | Feature | Multi-team support — abstract the "Sharks" filter into a configurable `team_slug` so the pipeline can serve any NHL team; opens a multi-tenant path. Largest bet here. |

The reviewer's own "top 3 next gaps": full-text search (already R2-U1), dark mode +
PWA (already R2-U2 / R2-U5), and off-Pi backups + deploy pipeline (R3-O1 / R3-O3).

---

# Brief 10 — MCP interface for agent access (planned, 2026-07-25)

[brief-10-mcp-interface.md](briefs/brief-10-mcp-interface.md) — the first brief
written after the 01–09 set. Goal: let LLM agents fetch, search, and drill into
the feed over the Model Context Protocol.

The MCP wrapper itself is thin; the cost is in the prerequisites. Full-text
search does not exist (**R2-U1**), and the feed response withholds fields agents
need — `clusters.llm_summary` is never serialised, there is no public `/tags`
route, and `/feed` cannot filter by `event_type`.

Ships as **two PRs, one per session**:

| Phase | Scope | Items | Effort | Branch |
|-------|-------|-------|--------|--------|
| A | Postgres FTS + feed ergonomics (backend only, useful on its own) | R2-U1, MCP-1 | M–L | `improve/10a-search` |
| B | Read-only stdio MCP server (6 tools) over the Phase A surface | MCP-2, MCP-3 | M | `improve/10b-mcp` |
| C | Remote transport + auth — **deferred, not to be built yet** | MCP-4, MCP-5 | — | — |

Phase A must merge before Phase B starts. Phase C stays deferred: the API has no
public port today (only `web` is published and tunnelled), and exposing an
unauthenticated MCP endpoint over this data would need a real shared-state rate
limiter — the in-memory one in `api/app/dependencies.py` is per-process and
wired only to the metrics routes (cf. R3-S2).

| ID | Area | Item |
|----|------|------|
| MCP-1 | Usability | Expose `llm_summary` in the feed payload; add `event_type` and `until` filters to `/feed`; route the existing `get_tag_distribution()` as `GET /tags`. |
| MCP-2 | Feature | Read-only stdio MCP server in a standalone `mcp/` package — `search_news`, `get_feed`, `get_story`, `list_players`, `list_tags`, `get_status`. Hand-written tools, not auto-generated from `/openapi.json` (that would expose every `/admin/*` route). |
| MCP-3 | Feature | Response budgeting — default limit 10 / cap 25, compact rendering rather than raw JSON echo. The main way an MCP server ships badly is by flooding the agent's context. |
| MCP-4 | Architecture | *(deferred)* Remote transport — streamable-HTTP MCP on FastAPI published via noBGP, or an MCP route in Next.js reusing the proxy pattern. |
| MCP-5 | Security | *(deferred, blocks MCP-4)* Bearer-token auth + Redis-backed rate limiting before anything MCP is publicly reachable. |

Write tools and all `/admin/*` tools are out of scope by decision — read-only v1.

---

# Brief 11 — Richer public metrics, without cookies (planned, 2026-07-25)

[brief-11-public-metrics.md](briefs/brief-11-public-metrics.md) — expand the
three-figure footer strip (`web/app/page.tsx:324`) into a real set of public
metrics while keeping the no-cookie, no-consent-banner posture.

Most of the value needs **no new collection at all**: `clusters.click_count` is
already written by `/cluster/{id}/click` and read by nothing, and
`validation_logs`, `cluster_entities`, and `story_variants` support a
most-mentioned-player / top-source / screened-vs-published set straight out of
the existing schema.

Ships as **two PRs, one per session**:

| Phase | Scope | Items | Effort | Branch |
|-------|-------|-------|--------|--------|
| A | Derived stats + `/stats` caching + footer redesign. Zero new collection. | MET-1, MET-2, MET-3 | M | `improve/11a-derived-stats` |
| B | Cookie-free collection: daily rollups, referrer hosts, filter popularity, RSS/Bluesky counts | MET-4 … MET-7 | M–L | `improve/11b-metrics-collection` |

| ID | Area | Item |
|----|------|------|
| MET-1 | Usability | Expand `/stats`: stories 24h/7d, top story by `click_count`, most-mentioned entity, event-type breakdown, top source, screened-vs-published, median time-to-surface, entities tracked, last updated. All derived from existing tables. |
| MET-2 | Performance | Cache `/stats` in Redis (~5 min TTL). It is called on every page load and MET-1 turns it into ~9 aggregates on a Pi. Must serve stale rather than 500 — stats are decorative and must not take the feed down. |
| MET-3 | Usability | Two-line footer strip, null-safe, no layout shift. A dedicated `/stats` page is explicitly out of scope. |
| MET-4 | Operations | New `metric_daily` table `(key, day, value)` — `site_metrics` has no date dimension, so "visits today" is impossible today. Lifetime counters stay as they are. |
| MET-5 | Usability | Referrer **hosts** only, read from `document.referrer` client-side — the beacon's own `Referer` header is the site itself, so server-side reading yields 100% self-referrals. Top ~5 published only. |
| MET-6 | Usability | Filter popularity from `tags=`/`entities=` usage on `/feed`. |
| MET-7 | Usability | RSS subscriber estimate from feed-reader User-Agents; Bluesky follower count via the existing atproto client (reuse a cached session — cf. R2-S7). |

**Privacy constraints are requirements, not guidance:** no cookies, no
device storage of any kind, no fingerprinting, no third-party analytics, and
**no per-visitor identifier — including hashed or daily-rotating ones.**
Cookie-free unique visitors (the Plausible/Fathom daily-salted-IP pattern) was
considered and **explicitly rejected**, so a later session doesn't add it as a
helpful extra. Phase B must also update `web/app/legal/page.tsx` §6.2, which
currently promises the policy will be updated if analytics are ever added.

---

# Brief 12 — Make the feed crawlable, and give it metadata (planned, 2026-07-27)

[brief-12-crawlable-feed-and-metadata.md](briefs/brief-12-crawlable-feed-and-metadata.md)
— from a DataForSEO audit of the live site, 2026-07-27.

`web/app/page.tsx` is `'use client'`, so every cluster is fetched after hydration and
the server response is **108 words** (header, filter bar, footer) at a 4.3%
text-to-HTML ratio. Google has indexed the homepage — rank 1 for
`site:nobgp.com sharks` — and chose the **footer disclaimer** as the snippet, because
there was no article content to draw from. The same applies to GPTBot, ClaudeBot,
PerplexityBot and Bing, none of which execute JavaScript on arbitrary pages.

The 94/100 OnPage score and the 99/96/100/100 Lighthouse row are both grading the
shell. The shell is genuinely excellent; it is also all a crawler receives.

Ships as **three PRs, one per session**:

| Phase | Scope | Items | Effort | Rebuild | Branch |
|-------|-------|-------|--------|---------|--------|
| A | Correct `PUBLIC_SITE_URL` and the docs that let it drift | SEO-11 | XS | api restart | `improve/12a-public-site-url` |
| B | Server-render the feed + the structural content that comes with it | SEO-1 … SEO-4 | L | web + api | `improve/12b-ssr-feed` |
| C | Metadata, discovery, structured data | SEO-5 … SEO-10 | M | web | `improve/12c-metadata` |

Phase A is config-only, ships on its own, and fixes a live correctness bug in the
published RSS. Phase C depends on B only for SEO-9's `ItemList`; the rest can ship
independently.

| ID | Area | Item |
|----|------|------|
| SEO-1 | Usability | Split `page.tsx` into a server shell + `<FeedList initial>` client child. Fetch `INTERNAL_API_URL` directly server-side (not via the site's own BFF route). Shipped as `dynamic = 'force-dynamic'` + `fetchCache = 'default-cache'` with per-fetch `revalidate = 300`, **not** plain ISR — ISR prerenders at build time, when the API is unreachable, and would ship an empty feed in the image. Does **not** fix the HTML's `Cache-Control: no-store` (an earlier note here claimed it would). |
| SEO-2 | Usability | Server-render ~15–20 players-in-the-news as clickable filter chips. **Blocked on** adding a prominence ordering to `GET /entities` (`api/app/routers/feed.py:157`), which is alphabetical today — Adam Gaudette first, forever. |
| SEO-3 | Usability | Name the source outlets server-side. Needs a **new public `GET /sources`** (name, `base_url`, category — explicit field whitelist); the admin endpoint at `api/app/routers/admin.py:59` stays behind its 401. |
| SEO-4 | Usability | Expand the header paragraph to state the goal plainly. A paragraph, not a wall — SEO-1…3 supply the bulk of the new indexable text. |
| SEO-5 | Operations | `web/app/robots.ts` + `web/app/sitemap.ts`. Both currently 404. Disallow `/admin` and `/api`; `lastmod` on `/` from the newest cluster. |
| SEO-6 | Usability | `metadataBase` + per-page `metadata` for `about`/`legal`/`submit` — all four pages currently share one 22-char title and one 43-char description from `web/app/layout.tsx:5`. Base URL as **one exported constant**. |
| SEO-7 | Usability | Canonical tags; `/` canonicalises to the bare origin so filter query strings collapse. |
| SEO-8 | Usability | Open Graph + Twitter Card, and one **static** 1200×630 image from `Logos/`. Currently a shared link on Bluesky — the project's live distribution channel — renders no card at all. |
| SEO-9 | Usability | JSON-LD: `WebSite` + `Organization` sitewide, `CollectionPage`/`ItemList` on `/`, `Person` for Davin on `/about`. |
| SEO-10 | Operations | Static `web/public/llms.txt`. |
| SEO-11 | Operations | `PUBLIC_SITE_URL` on the Pi still holds `x2mq74oetjlz.nobgp.com`, which **404s**, so `/rss` publishes a dead origin in `<link>` and `atom:link rel="self"`. Also declare it in `docker-compose.pi.yml` and record the real value in `.env.example:25` + `docs/ARCHITECTURE.md:342`. |

**Decisions already taken — do not re-litigate in a later session:**

- **24h window stays the default.** Server-render exactly what the UI shows (~8
  stories). Rendering a wider set and hiding the surplus was considered and
  **rejected** — hidden content is discounted anyway, and it is not honest.
- **Absolute datetimes, not relative strings.** `formatLastScanTime()`
  (`web/app/page.tsx:106-110`) becomes an absolute datetime. Separately, card dates
  (`web/app/components/ClusterCard.tsx:25`) already are absolute but pass no
  `timeZone`, so server and client disagree — pin `America/Los_Angeles`. Wrap both in
  `<time datetime>`; the feed currently contains **zero** `<time>` elements.
- **No `NewsArticle` markup per item.** The site links out rather than hosting;
  claiming article markup for someone else's reporting misrepresents authorship.
- **Legacy headline/link mismatches are out of scope.** Verified 2026-07-27 that
  `df142f2` works on live clusters (4019 self-corrected within ~20 min); cluster 4003
  is pre-fix backlog and ages out of a 24h window on its own.
- **Static OG image, not dynamic `opengraph-image.tsx`**, for now.
- **No custom domain.** `wplepla23gjn.nobgp.com` is the strategic ceiling on any
  organic result — zero referring domains, unbrandable, shared root — but that is a
  separate decision, not part of this brief.

**Follow-up this brief deliberately sets up:** crawlable `/tag/*` routes. Filters stay
client-side here and SEO-7 makes filter URLs non-indexable, which is only acceptable
because real tag pages are next. `sharks trade rumors` is **1,900 searches/month at
difficulty 23, +125% YoY** (DataForSEO Labs, US/en) — the most winnable term available,
and the Trade and Rumors tags already exist. Pair it with Google Search Console: at one
indexed page and zero backlinks, GSC is the only way to see whether any of this moved.

---

# Brief 13 — Crawlable tag routes, and one player page (planned, 2026-07-27)

[brief-13-crawlable-tag-and-player-routes.md](briefs/brief-13-crawlable-tag-and-player-routes.md)
— the follow-up brief 12 deliberately set up.

Brief 12 canonicalised `?tags=trade&since=7d` into the bare homepage. Correct at
the time (those URLs were client filter state, not pages), but it leaves the site
with **four** indexable URLs, none targeting a topic. `sharks trade rumors` is
1,900/mo at difficulty 23 and +125% YoY, and the Trade and Rumors tags already
exist.

Ships as **one PR**, web-only — the feed API already accepts `tags`, `entities`
and `since`, so no API/worker/beat rebuild.

| ID | Area | Item |
|----|------|------|
| TAG-1 | Usability | `/tag/[slug]`, allowlisted to the eight known tags (anything else 404s — an allowlist is what stops the route minting unbounded indexable URLs). 30-day window, `force-dynamic` + `fetchCache`, per-tag metadata, self-canonical. |
| TAG-2 | Code quality | Extract `ClusterList` from `FeedList` so tag/player pages reuse the list + pagination instead of copying it. |
| TAG-3 | Usability | "Browse by topic" footer nav linking every new route — without it they are orphans only the sitemap knows about. |
| TAG-4 | Usability | `/player/[slug]` allowlisted to `macklin-celebrini` only. 65 clusters/30d, 2.6× the next player. Targets the realistic long tail, **not** the 135k/mo navigational head term. |
| TAG-5 | Operations | Sitemap entries gated on a live ≥10 cluster count. Below threshold the page still renders and stays linked, it is just not advertised. Count cheaply via `limit=10` and test for ten. |
| TAG-6 | Usability | `CollectionPage`/`ItemList` JSON-LD on the new routes, `isPartOf` the existing `#website` node. Still no `NewsArticle`. |

**Decisions already taken — do not re-litigate:**

- **30-day window.** At 24h every tag but Rumors and Trade is empty.
- **Thin-content gating is dynamic, never a hardcoded skip list.** Waiver, Injury
  and Lineup are thin *in July* and are exactly the tags that spike Oct–Apr.
- **Tag chips stay `<button>`s.** Progressive-enhancement anchors were considered
  and rejected as not worth the complexity; footer links get crawlability,
  internal linking and sitemap entries for far less work.
- **One player page.** 47 entities have coverage and ~150 exist — that is
  programmatic scale and the pattern Google scrutinises hardest. Measure first.
- **No `tags_mode=all`.** `/tag/trade` serves the "trade rumors" intent honestly;
  54% of trade-tagged clusters already carry Rumors.
- **No paginated URLs.** SSR 50 + client "Load more" + self-canonical.

---

# Roadmap / backlog

Deferred items, specified well enough to execute later without re-research.

### RM-2 — Relevance: a Sharks player's name admits an article about another team

*Found 2026-07-27 while verifying brief 13. Highest-value open item — it is a
content-quality problem, and the topic pages just raised its cost.*

**The mechanism.** `check_sharks_relevance()`
(`api/app/enrichment/classify.py:65`) approves an article if either:

1. the title contains a Sharks keyword (`sharks`, `barracuda`, `sap center`…), or
2. the title mentions **any** non-team Sharks entity — a player, coach or staff
   member.

Rule 2 is the leak. It admits an article on the strength of a name appearing in
the title, with no test of what the article is *about*. That is usually right,
and it is badly wrong for recently-acquired players: Darnell Nurse, Jacob Trouba,
Yaroslav Askarov and Alex Nedeljkovic all carry heavy ongoing coverage from
their **former** teams' media, and every one of those articles passes.

**Measured 2026-07-27** (30-day window; "headline names another NHL team and
does not mention San Jose"):

| Page | Clusters | Off-team | Rate |
|---|---|---|---|
| `/tag/rumors` | 100 | 32 | **32%** |
| `/tag/trade` | 90 | 24 | **27%** |
| `/tag/game` | 45 | 7 | 16% |
| `/tag/signing` | 100 | 10 | 10% |
| Homepage, 24h | 10 | 0 | **0%** |

Representative failures, each admitted solely by rule 2:

- *"3 Reasons the Oilers Got Better This Offseason"* — entity: Darnell Nurse
- *"4 Early PTO Targets the Maple Leafs Should Consider"* — entity: Alex Nedeljkovic
- *"Calgary Flames Still Fielding Trade Calls On Two Players"* — entity: Jacob Trouba

**Why it matters more now.** On the homepage an off-team story is noise, and the
24-hour default keeps the rate near zero. A topic page makes an explicit promise
in its `<h1>` and `<title>` — "San Jose Sharks Trade News & Rumors" — and then
fills a quarter to a third of the page with Oilers and Maple Leafs content. That
is the kind of intent mismatch that costs the ranking the page was built for.

Note the homepage's 0% is a window artifact, not evidence the filter is fine: the
30-day window covers July's Nurse/Trouba acquisition coverage, and 24 hours in the
offseason simply does not contain much.

**Start by reading data that already exists, not by building.** Production runs
`LLM_EVALUATION_MODE=true` (`docker-compose.pi.yml`), which per
`validate_sharks_relevance()` (`classify.py:109`) means **keyword always decides
and the LLM only logs a comparison**. Every disagreement is already recorded in
`validation_logs` with `keyword_matched` alongside the LLM verdict. So the first
task is a query, not a feature: on the off-team clusters above, did the LLM
already disagree with the keyword check? If it did, most of the fix is flipping
one env var that is already implemented and already being measured.

**Options, roughly in order of cost:**

1. **Promote the LLM to decision mode** (`LLM_EVALUATION_MODE=false`). Already
   built, with keyword fallback on error. Cost: an LLM call per candidate item
   on a paid model — check the rate against `openrouter` spend first. Only worth
   it if the eval logs show the LLM actually catches these.
2. **Tighten rule 2**: require a player entity *plus* a second signal — a Sharks
   keyword anywhere in the title, or the absence of another NHL team's name.
   Cheap, deterministic, no per-item cost. Risk: rejects genuine "Sharks acquire
   X from Edmonton" stories, which name both teams. Needs the both-teams case
   handled explicitly.
3. **Keep admitting them, but label and segregate.** Add an `off-team` or
   "Around the NHL" classification, show it on the homepage, and exclude it from
   team topic pages and the RSS feed. Keeps coverage the aggregator arguably
   should have while stopping topic pages from breaking their promise. Largest
   change; probably the best end state.

**Verify with:** the measurement script pattern above — pull each tag feed at
30d and count headlines naming another NHL team without naming San Jose. Target
is materially under 10% on `/tag/trade` and `/tag/rumors` without losing
genuine two-team trade stories.

**Correction to the record:** the original SEO audit (2026-07-27) said "roughly
half the surfaced items are off-topic", based on eyeballing eight stories in the
default view. The measured figure is 10–32% depending on the page, and the
failure has a specific mechanism rather than being general noise. The audit
number was an impression; these are counts.

### RM-1 — Threads accounts as sources via self-hosted RSSHub

*Deferred by decision 2026-07-19 (documented, not implemented). Feasibility
verified live that day.*

- **Goal.** Ingest NHL-insider Threads accounts — first candidate
  [@kevweekes](https://www.threads.com/@kevweekes) (Kevin Weekes posts breaking
  news there; he has no Bluesky presence). Complements the Bluesky mirror
  sources added 2026-07-19 (sources 30–32: notfriedgehnic / notpierrevlebrun /
  notfrankseravalli, plain `bsky.app/profile/<handle>/rss` feeds).
- **Why not direct.** Threads has no native RSS. Its ActivityPub/fediverse
  sharing would be the clean path, but it is opt-in per account and
  `@kevweekes` has it disabled (webfinger for `kevweekes@threads.net` → 404,
  checked 2026-07-19; re-check occasionally — it's a profile toggle). The
  official Threads API is OAuth-scoped to one's own content, not arbitrary
  public profiles.
- **Verified approach.** Self-hosted [RSSHub](https://docs.rsshub.app)'s
  `/threads/:user` route returns clean RSS **unauthenticated** (verified
  2026-07-19 against `@kevweekes`: real titles, `threads.com/t/...` links,
  correct pubDates; feedparser handles it; items carry titles so the #99
  title-derivation fallback isn't even needed).
- **Implementation sketch.**
  1. Add an `rsshub` service to the compose files (`diygod/rsshub`, multi-arch
     incl. arm64, ~640MB image — a pull, not a build, so no eMMC build risk on
     the Pi). Point its cache at the existing `redis` service. No public port;
     it only needs to be reachable from the worker network.
  2. Add sources with `ingest_method=rss`,
     `feed_url=http://rsshub:1200/threads/<user>`,
     `base_url=https://www.threads.com/@<user>`, category `press`, relevance
     check ON (league-wide content; low accept ratio is expected and correct).
  3. Candidates: `kevweekes`; check whether Chris Johnston and Darren Dreger
     are active on Threads (neither is on Bluesky as of 2026-07).
- **Caveats.** This is scraping Meta — same fragility class as rss.app/Nitter.
  When Meta changes markup, the route 5xxs, `fetch_error_count` climbs, and the
  brief-09 health check flags the source as broken (that is the desired
  signal). Fix is usually pulling a newer RSSHub image. Weekes posts in bursts
  (a few/month, season-heavy), so a quiet source is normal.
- **Verify.** `curl http://rsshub:1200/threads/kevweekes` returns RSS from the
  Pi; the source ingests without errors; a non-hockey post is dropped by the
  relevance filter; a Sharks-relevant post lands on a card with a real title.
