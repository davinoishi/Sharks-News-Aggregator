# Improvement Plan — Archive of completed work

Everything here is **done**. It lives outside `IMPROVEMENT_PLAN.md` so that file
shows only open work, and here so the record survives: what was found, what
shipped, and which PR carries it.

Kept rather than deleted for two reasons. The findings register below defines the
IDs (`S1`, `C1`, `P3`…) that the brief files in `docs/briefs/` still reference, so
deleting it would leave those briefs pointing at nothing. And "was this ever
looked at, and what did we decide?" is a question worth being able to answer
without archaeology through git history.

**Open work lives in [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).**

---

# Round 1 — full codebase review (2026-06-10), briefs 1–9

Nine briefs covering security, correctness, performance, usability, code quality
and operations. **All complete and merged to `main` (2026-06-12.)**

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

---

# Round 2 (external, Kimi, 2026-06-15) — P0/P1 items

The four P0/P1 findings from the round-2 review. All merged and deployed to
production (pi5-ai2) on 2026-06-15 — verified live: migration `0003` applied, the
pinned CORS origin echoes, and the backup `verify` test-restore passed.

The remaining `R2-*` items (P1–P3) are still open and stay in
[IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).

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

# Other completed R2 items

Closed later, outside the P0/P1 push:

| ID | Item | Where it shipped |
|----|------|------------------|
| R2-S6 | Add CSP headers in `next.config.js` | Shipped with the web UI work; `next.config.js` now sets a full Content-Security-Policy plus the surrounding security-header set. |
| R2-U7 | Open Graph / Twitter Card meta tags | Brief 12, SEO-8 ([#123](https://github.com/davinoishi/Sharks-News-Aggregator/pull/123), [#128](https://github.com/davinoishi/Sharks-News-Aggregator/pull/128)) |

---

# Brief 12 — Make the feed crawlable, and give it metadata (2026-07-27)

[brief-12-crawlable-feed-and-metadata.md](briefs/brief-12-crawlable-feed-and-metadata.md)
— from a DataForSEO audit of the live site.

The feed page was `'use client'`, so the server response was **108 words**:
header, filter bar, footer, no stories. Google indexed the homepage and chose the
footer disclaimer as its snippet, because that was the only prose available.
GPTBot, ClaudeBot, PerplexityBot and Bing saw the same shell.

| Phase | Scope | Items | PR |
|-------|-------|-------|----|
| A | Correct `PUBLIC_SITE_URL`, which had drifted to a host that 404s | SEO-11 | [#120](https://github.com/davinoishi/Sharks-News-Aggregator/pull/120) |
| B | Server-render the feed; player chips, named sources, expanded intro | SEO-1 … SEO-4 | [#121](https://github.com/davinoishi/Sharks-News-Aggregator/pull/121) |
| C | metadataBase, per-page metadata, canonical, OG/Twitter, JSON-LD, robots, sitemap, llms.txt | SEO-5 … SEO-10 | [#123](https://github.com/davinoishi/Sharks-News-Aggregator/pull/123) |

Follow-ups: [#122](https://github.com/davinoishi/Sharks-News-Aggregator/pull/122)
(corrected a wrong caching instruction in the brief),
[#124](https://github.com/davinoishi/Sharks-News-Aggregator/pull/124) (`PUBLIC_SITE_URL`
as a build arg — three pages would have shipped `localhost` canonicals),
[#125](https://github.com/davinoishi/Sharks-News-Aggregator/pull/125) (title 70→54
chars, crest alt text, GSC verification),
[#126](https://github.com/davinoishi/Sharks-News-Aggregator/pull/126) (duplicate
`Cache-Control` on the discovery files).

Measured: server-rendered words 108 → 286, `h2` headlines 0 → 8, indexable URLs
4 → 5, DataForSEO OnPage score 94.15 → **100**.

---

# Brief 13 — Crawlable tag routes, and one player page (2026-07-27)

[brief-13-crawlable-tag-and-player-routes.md](briefs/brief-13-crawlable-tag-and-player-routes.md)
— [#127](https://github.com/davinoishi/Sharks-News-Aggregator/pull/127).

`/tag/[slug]` for the eight tags and `/player/[slug]` for one player, both
allowlisted; `ClusterList` extracted from `FeedList`; "Browse by topic" nav;
sitemap entries gated on a live 30-day cluster count of 10.

Follow-ups: [#128](https://github.com/davinoishi/Sharks-News-Aggregator/pull/128)
(subpages were sending the site's Twitter card, not their own),
[#129](https://github.com/davinoishi/Sharks-News-Aggregator/pull/129)
(`history.replaceState(null, …)` wiped the App Router's routing state, so Back
changed the URL and left the previous page rendered — a bug that predated the tag
routes and which they exposed).

Indexable URLs 5 → 10.

**Left open by this work:** the relevance gap it exposed — see `RM-2` in
[IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md). 27–32% of `/tag/trade` and
`/tag/rumors` are headlines about other teams.
