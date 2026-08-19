# Sharks News Aggregator — Improvement Plan

**Open work only.** Completed items live in
[IMPROVEMENT_PLAN_ARCHIVE.md](IMPROVEMENT_PLAN_ARCHIVE.md) — round-1 briefs 1–9,
the round-2 P0/P1 push, and briefs 12–13, together with the findings register
that defines the `S1`/`C1`/`P3` IDs the older brief files reference.

**How to use:** start a fresh agent session, point it at exactly one brief file,
and have it deliver a branch + PR against `main`. Do not combine briefs in one
session. Each brief carries its own context, requirements, out-of-scope list and
verification steps.

## What's open, at a glance

| | Item | Where |
|---|------|-------|
| **Next up, brief written** | `RM-4` — clustering: unrelated stories land on the same card | [below](#rm-4--clustering-unrelated-stories-land-on-the-same-card) · [brief 14](briefs/brief-14-cluster-merge-precision.md) |
| Open | `RM-2` — relevance: a Sharks player's name admits an article about another team | [below](#rm-2--relevance-a-sharks-players-name-admits-an-article-about-another-team) |
| Open, one attempt reverted | `RM-3` — relevance: "Sharks" is not a hockey word | [below](#rm-3--relevance-sharks-is-not-a-hockey-word) |
| Planned brief | Brief 10 — MCP interface for agent access | [below](#brief-10--mcp-interface-for-agent-access-planned-2026-07-25) |
| Planned brief | Brief 11 — richer public metrics, without cookies | [below](#brief-11--richer-public-metrics-without-cookies-planned-2026-07-25) |
| Backlog | `R2-*` — round-2 review leftovers (P1–P3) | [below](#r2-backlog-open-items) |
| Backlog | `R3-*` — round-3 review (P1–P3) | [below](#r3-backlog) |
| Deferred | `RM-1` — Threads via self-hosted RSSHub | [below](#rm-1--threads-accounts-as-sources-via-self-hosted-rsshub) |

`RM-4` is first because it silently loses stories the pipeline already fetched,
enriched and got *right*. A mis-clustered article is not merely noise like an
off-team story — it is hidden behind a "View sources" control on a card the
reader has no reason to open, so a reader who has finished with that storyline
never sees it at all. `RM-2` and `RM-3` decide **whether an article belongs in
the feed**; `RM-4` decides **which card it lands on** once it does.

`RM-2` remains ahead of the remaining SEO work: the topic pages shipped in
brief 13 make an explicit promise in their `<h1>`, and a page that is a third
Oilers content will not hold a ranking it wins.

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
**Status note (2026-07-27):** the line above about tests and CI is no longer
true — brief 5 added CI and brief 6 the test suite. The API suite is 252 tests
with a Postgres job; `web` runs lint + build. Treat the rest of this section as
current.

---

# Round 2 review (external, Kimi, 2026-06-15)

The P0/P1 items from this review are done — see the archive. What remains is the
P1–P3 backlog below. ID namespace `R2-*`; priorities use the reviewer's matrix
where given, otherwise High→P1, Medium→P2, Low→P3.

## R2 backlog (open items)

| ID | Pri | Area | Item |
|----|-----|------|------|
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
| R2-O6 | P3 | Operations | No `deploy.resources.limits` in compose — cap CPU/mem so a runaway worker can't starve the Pi. |
| R2-O7 | P3 | Operations | `restart: unless-stopped` everywhere can restart-loop under disk/mem pressure — add `on-failure` + delay. |
| R2-U4 | P3 | Usability | No keyboard shortcuts (`j/k`, `/`, `?`). |
| R2-U5 | P3 | Usability | No PWA/offline support — service worker + manifest. |
| R2-U6 | P3 | Usability | RSS feed lacks `<lastBuildDate>` and `<ttl>`. |
| R2-F6 | P3 | Functionality | `entities_agg` ARRAY duplicates the `ClusterEntity` junction — derive it to avoid drift. |
| R2-F7 | P3 | Functionality | No dedup of BlueSky posts by content hash — re-created clusters could repost. |
| R2-F8 | P3 | Functionality | `cleanup_bogus_entities` uses Postgres-only regex `~ '[a-zA-Z]'` — abstract for portability. |
| R2-A1 | P3 | Architecture | Add API versioning (`/v1/...`). |
| R2-A2 | P3 | Architecture | Consider async SQLAlchemy for the API layer. |
| R2-A3 | P3 | Architecture | Add OpenAPI/Swagger tags. |
| R2-A5 | P3 | Architecture | Add distributed tracing (OpenTelemetry) RSS→enrich→cluster→post. |
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
OG/Twitter cards (R2-U7 — **since completed**, see archive), PWA (R2-U5), keyboard shortcuts (R2-U4), infinite scroll
(R2-U3), RSS `<lastBuildDate>`/`<ttl>` (R2-U6), SSRF IP pinning (R2-S4), body-size
limit (R2-S3), admin key rotation/JWT (R2-S2), Redis ACLs (R2-O4), `timingSafeEqual`
(R2-S5), keyset pagination (P3), `feed_cache` usage (P2), async SQLAlchemy (R2-A2),
tighten Celery time limits (R2-O5), `deploy.resources.limits` (R2-O6),
`restart: on-failure` (R2-O7), Bluesky session caching (R2-S7), log aggregation
off-Pi (R2-O1), API versioning (R2-A1), OpenRouter circuit breaker (R2-A4),
OpenTelemetry (R2-A5), derive `source_count` by query (R2-F4), dedup `entities_agg`
(R2-F6), CSP headers (R2-S6 — **since completed**, see archive).
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

## Decided against

Kept so they are not re-proposed as helpful extras.

- **R3-U1 — relative timestamps ("2h ago") via `date-fns`.** Incompatible with the
  server-rendered feed: a relative string computed server-side is stale on arrival
  and mismatches on hydrate. Brief 12 deliberately moved the one remaining relative
  string to an absolute datetime. If revived it must be a client-only effect over a
  server-rendered `<time datetime>`, never a server-rendered string.
- **Cookie-free unique visitors** (the Plausible/Fathom daily-salted-IP pattern) —
  rejected under brief 11's privacy constraints; see that section.
- **MCP write tools and `/admin/*` tools** — out of scope by decision; read-only v1.

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

# Roadmap / backlog

Deferred items, specified well enough to execute later without re-research.

### RM-4 — Clustering: unrelated stories land on the same card

*Found 2026-08-19 from a reader report: the card "Macklin Celebrini Card Auction
Nears $500K & It's Not Done" also held two articles about The Athletic's NHL
pipeline rankings. Scoped for execution in
[brief 14](briefs/brief-14-cluster-merge-precision.md).*

**Why this ranks above the relevance work.** An off-team story (RM-2) is visible
noise the reader can skip. A mis-clustered story is an *invisible* loss: variant
titles live behind the "View sources" control
(`web/app/components/ClusterCard.tsx:146`), so a reader who is done with the
card-auction storyline never expands it and never learns the pipeline rankings
came out. The pipeline is doing the expensive work — fetch, relevance, entity
extraction, LLM classification — correctly, and then filing the result where
nobody looks.

**The correct failure direction is over-splitting.** A duplicate card costs the
reader one redundant glance. A wrong merge costs them the story. Any tuning
under this item is to be judged asymmetrically: prefer a new cluster whenever the
evidence for merging is not positive.

#### The mechanism (proven)

`calculate_similarity_score()` (`api/app/enrichment/clustering.py:478`) scores a
candidate pair as `0.55·E + 0.35·T + 0.10·K`, and `is_match()`
(`clustering.py:731`) merges at `S >= 0.62` behind an entity gate of `E >= 0.50`.
Two articles about the same player with the same event type therefore score
`0.55·1.0 + 0.35·0 + 0.10·1.0 = 0.65` and merge **while sharing no words at
all**. Reproduced against the reported card with the real functions:

```
'Macklin Celebrini Card Auction Nears $500K' vs 'San Jose Sharks are No. 1 in NHL Pipeline Rankings'
  T = 0.000   title_similarity = 0.212   shared title tokens = 0
  E = 1.00, K = 1.0  ->  S = 0.650  match = True
```

Nothing in the scoring asks whether the two articles are about the same *story*.
It asks whether they are about the same *person*, and `filter_team_entities()`
guarantees the surviving entities are exactly people — so `E` saturates at 1.0
for any two articles about a single-star cluster. The defect is worst precisely
where coverage is heaviest.

Compounding it, the entity's own name is counted **twice** — once in `E`, and
again in `T`, because "macklin"/"celebrini" are ordinary headline tokens. That is
why raising the token threshold cannot fix this: measured over real pairs, the
good merges bottom out at `T = 0.200` and the bad merges reach `T = 0.200`.
Removing entity-derived tokens from `T` separates them.

#### Contributing defects

- **The summary-name bypass has no topic gate** (`clustering.py:371`). A shared
  person name in two LLM summaries plus `K >= 0.5` merges outright, skipping the
  score entirely. Meanwhile `CLASSIFY_PROMPT_USER`
  (`api/app/services/openrouter.py:72`) instructs the model to lead every summary
  with the subject's full name, explicitly so that "two stories about the same
  person cluster together". The prompt and the matcher reinforce each other in
  the wrong direction.
- **Clusters never age out.** The candidate window filters on
  `Cluster.last_seen_at >= window_start` (`clustering.py:181`), and
  `update_cluster_metadata()` pushes `last_seen_at` forward on every join
  (`clustering.py:910`). "72 hours" means 72 hours since the *last* addition, not
  since the story broke, so a busy cluster is immortal.
- **The entity path is untested.** Every case in `api/tests/test_clustering.py`
  passes `entities=[]` (`_cluster`, line 57), so the 0.55-weight term that causes
  this bug is never exercised. `test_unrelated_stories_do_not_merge` uses
  different players *and* different event types, and passes trivially.

#### Measured 2026-08-19 (offseason, 225 clusters in the live feed)

Of the 35 clusters holding 3+ surviving variants, 5 have mean pairwise headline
token overlap below 0.15 — i.e. their members share almost no vocabulary:

| Cohesion | Span | Variants | Cluster |
|---|---|---|---|
| 0.032 | 46h | 4 | NHL Rumors: Sharks willing to offer Celebrini max contract |
| 0.041 | 157h | 6 | Connor McDavid Speaks Out On Darnell Nurse Trade |
| 0.111 | 179h | 10 | 'Mac is crazy': Leafs' McKenna on summer training with Celebrini |
| 0.135 | 130h | 7 | Macklin Celebrini Named IIHF Male Player of the Year |
| 0.143 | 127h | 8 | **Macklin Celebrini Card Auction Nears $500K** (the reported card) |

Cohesion alone does not catch everything — cluster 4055 scores 0.197 but holds
**116 variants across 435 hours**, having absorbed "5 Restricted Free Agents
Still Unsigned", "Cale Makar Extension Questions Emerge" and a fantasy-hockey
top-100 list into the Celebrini extension story. Size and span are the second
detector. The five largest clusters in the feed span 146–435 hours against event
windows of 24–72 hours.

Two illustrative contents:

- Cluster 3835 (`other`, entities `{Celebrini, Sharks}`) holds the Celebrini
  hometown-discount story alongside a Jason Robertson extension story, a
  Tarasenko free-agency story and John Marino signing with the Mammoth.
- Cluster 4003 (`trade`, entities `{Nurse, Sharks}`) holds the McDavid/Nurse
  reaction alongside **"Edmonton police to introduce involuntary detention
  detox"** — a non-hockey Edmonton Journal video. That item is *also* a relevance
  failure and belongs to RM-2/RM-3; it is listed here because it shows how far a
  magnet cluster reaches.

**Over-merging causes under-merging.** The pipeline-rankings story exists twice:
two copies inside the card-auction cluster (4152) and one in cluster 4188, which
is itself mixed (a Yahoo copy plus an unrelated SJHN Daily roundup). Variants are
absorbed by whichever magnet cluster they touch first, so the real story never
accumulates its own sources and never earns a card of its own.

#### Would a more capable LLM fix this? No — measured 2026-08-19

The obvious question, asked because the production model
(`google/gemini-2.5-flash-lite`) was chosen on price. The answer is no, and for
this defect a stronger model is **marginally worse**. The two mis-merged
articles, scored through the real functions under each LLM condition:

| Condition | `L` | `S` | Merges? |
|---|---|---|---|
| No summary (LLM off, or the call failed) | — | **0.650** | yes |
| Summaries that do *not* both lead with the person's name | 0.220 | 0.527 | **no — correct** |
| Summaries that *do* both lead with the person's name | 0.531 | **0.636** | yes |

The middle row is the finding: **a good summary already prevents this merge.**
The model is capable. What defeats it is our own prompt.

**`CLASSIFY_PROMPT_USER` (`api/app/services/openrouter.py:72`) is load-bearing in
the wrong direction.** It instructs the model to *"LEAD with that person's full
name … This lets two stories about the same person cluster together."* In a 5–10
word summary the name is a third of the text, so forcing it into both summaries
lifts `L` from 0.220 to 0.531 and carries the pair over the 0.62 bar. It also
makes `summary_name_match` fire, which merges outright regardless of score.

A more capable model follows that instruction *more* reliably, produces *more*
name-dominated summaries, and merges *more*. The instruction reads like a
feature; anyone touching clustering needs to know it is a cause of RM-4.

The merge is also overdetermined — the no-summary branch reaches 0.650 through
`0.55·E + 0.10·K` without consulting the LLM at all. No model choice affects that
path.

**The same conclusion holds for RM-2, for a different reason.** Its eval found
the LLM rejecting Nurse articles because it believes *"Darnell Nurse is an
Edmonton Oilers player and has no affiliation with the San Jose Sharks."* That is
a knowledge-cutoff failure, not a reasoning failure: no model at any price knows
about a trade made weeks ago. A stronger model returns the same wrong answer with
more confidence. RM-2 option 1 — feed the synced roster into the prompt — is the
fix, and it is free.

**Generalisation, worth holding onto:** the LLM failures in this codebase are
*grounding and prompt-design* failures, not capability failures. That is why
paying more per call does not move them.

#### Where model capability would actually pay

Two jobs are pure judgment over supplied text, needing no external knowledge —
where capability does convert into quality:

- **`low_value` detection.** The prompt is already a wall of hedged heuristics
  about schedule stubs, betting autopages and "player names are NOT reporting" —
  prompt complexity compensating for a weak model.
- **`story_key` generation** (brief 15). Producing a canonical topic slug is a
  harder abstraction than anything the model is asked for today, and it is the
  signal RM-4 ultimately depends on. If we upgrade anywhere, upgrade here.

#### Cost is not the constraint — measured, not assumed

Volume from our own logs: ~2,618 relevance + ~1,100 classify calls/month in the
offseason. Prompts are ~200 and ~647 tokens plus ~200 for the article. Projecting
3× for the season (~6M input, ~0.35M output per month):

| Model | Input $/M | Output $/M | Est. $/month, in-season |
|---|---|---|---|
| `gemini-2.5-flash-lite` (current) | ~0.10 | ~0.40 | **~$1** |
| Claude Haiku 4.5 | 1.00 | 5.00 | **~$8** |
| Claude Sonnet 5 | 3.00 | 15.00 | **~$23** |
| Claude Opus 5 | 5.00 | 25.00 | **~$39** |

The entire decision space is under $40/month; at 3× the volume estimate, top tier
is ~$120. **Select on accuracy, not price.** Claude figures are Anthropic list
rates (cached 2026-06-24) and OpenRouter may add margin; the Gemini figure is
approximate — verify both live per `[[openrouter-model]]`.

**Production has already run two models, sequentially.** The corpus frozen
2026-08-19 shows `google/gemma-4-26b-a4b-it` through 2026-07-24 and
`google/gemini-2.5-flash-lite` from 2026-07-23, so a month of real traffic was
scored by two different models and any rate computed over the whole window
averages them. Split on `llm_model` before drawing conclusions from
`validation_logs`.

It is **not** usable as an A/B — `raw_items` scored by more than one model: **0**.
The groups are different articles from different news weeks, so model and news
period are confounded. Replaying one frozen corpus through both (brief 16, EV-3)
is what would produce a real comparison.

Measuring accuracy needs a replay harness that does not exist yet, plus two
prerequisites: `validation_logs.llm_response` is `String(100)` and truncates the
JSON (already noted under RM-2), and `run_purge_old_items` deletes `raw_items`
after 30 days, so **an eval corpus must be frozen before it is purged** — and an
in-season corpus cannot exist until October. Scoped in brief 16.

#### Not yet attributed

The E+K hole above is proven by computation. The merge path taken by each
production cluster listed here is **not** known — `match_or_create_cluster()` has
six routes to a merge (syndication UUID, game identifier, title similarity,
strong containment, title name-match, score, summary name-match) and logs at
`debug`, which production does not retain. Instrumenting the decision is
therefore the first task of brief 14, not an afterthought: the remaining routes
get attributed with data rather than guessed at. This is the RM-3 lesson applied
in advance — see `[[relevance-change-seasonal-measurement]]`.

#### Scope split

- **[Brief 14](briefs/brief-14-cluster-merge-precision.md) — written, ready to
  execute.** Instrument the decision; require positive topical evidence for any
  merge; stop double-counting entity names; gate the summary-name bypass; bound
  cluster lifetime; test the entity path; split the existing bad clusters.
- **[Brief 15](briefs/brief-15-story-keys.md) — written.** The durable fix: have
  the classifier emit a canonical `story_key` topic slug in the JSON it already
  returns (zero extra LLM calls) and make story-key agreement the primary merge
  signal; retire the name-leading summary instruction that this item proved is a
  cause; a "Related stories" link between near-miss clusters to pay back the cost
  of splitting; surfacing variant headlines inline on the card; an oversized-
  cluster alert; and a pair-eval harness.
- **[Brief 16](briefs/brief-16-llm-eval-harness.md) — written.** The LLM replay
  harness and model bake-off, split out of brief 15 because it serves RM-2 and
  RM-3 equally, has its own prerequisites (widen `validation_logs.llm_response`,
  freeze a corpus before the 30-day purge), and is eval tooling rather than
  pipeline code.

Lexical similarity cannot separate "Celebrini's rookie card sold for $1.28M" from
"Celebrini tops the pipeline rankings" — the shared words *are* his name. Brief
14 blocks the zero-evidence merges, which is a strict improvement and kills the
reported bug; brief 15 is what actually decides the hard cases.

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

**Background.** Production runs `LLM_EVALUATION_MODE=true`
(`docker-compose.pi.yml`), which per `validate_sharks_relevance()`
(`classify.py:109`) means **keyword always decides and the LLM only logs a
comparison**. Every disagreement is recorded in `validation_logs` with
`keyword_matched` alongside the LLM verdict — so the obvious first question,
"would promoting the LLM fix this?", is answerable from a month of existing data
without building anything. It was, and the answer is no.

#### The eval data has been read (2026-07-27). Promoting the LLM will not fix this.

2,618 logged comparisons over a month (2026-06-26 → 07-27):

| keyword | LLM | count |
|---|---|---|
| approve | relevant | 1,070 |
| approve | **not** relevant | **25** |
| reject | **relevant** | **642** |
| reject | not relevant | 881 |

Flipping `LLM_EVALUATION_MODE=false` would remove **25** items a month (2.3% of
keyword approvals) and add **642** the keyword check currently rejects — a ~59%
increase in admitted volume. It makes the feed larger, not tighter, and does
essentially nothing for the 27–32% off-team rate.

**Worse, the LLM's rejections are right for the wrong reason.** Its stated
reasons on those 25:

> "Darnell Nurse is an Edmonton Oilers player and has no affiliation with the
> San Jose Sharks."

Nurse was traded *to* San Jose. The model is reasoning from stale training data,
and the reason it rejects those Oilers articles is that it does not believe Nurse
is a Shark at all. Promoted to decision mode it would also reject genuine
Sharks-Nurse coverage — trading a precision problem for a worse recall one, on
exactly the players currently generating the most news.

The 642 additions are the prompt behaving as written:
`RELEVANCE_PROMPT_USER` (`api/app/services/openrouter.py:23`) says approve "any
current **or former** Sharks/Barracuda player" and "REJECT **only** if … NO
meaningful connection". That is deliberately permissive, and it is what admits
Timo Meier, Joel Ward and Michael Bunting items.

**Two genuine keyword false positives the LLM caught for correct reasons**, worth
fixing regardless and independent of any LLM work:

- *"AEW Forbidden Door Explodes at SAP Center"* — the `sap center` keyword
  matches non-hockey events at the venue.
- *"Teal just hits different. 🔥 #sharks #nhl #hockey"* — hashtag-only YouTube
  descriptions match `sharks`.

**Revised options, best first:**

1. **Give the LLM roster ground truth, and narrow the prompt.** The system
   already syncs a current roster (`sync_sharks_roster`), so the model never
   needs to guess which team a player is on. State in the prompt that the listed
   entities *are* current Sharks as of a date, and reconsider "or former" — that
   clause is generating much of the +642. Then re-measure in evaluation mode
   before promoting anything. Cheapest change with the highest ceiling, and it
   keeps the existing shadow-mode safety net.
2. **Tighten keyword rule 2** deterministically: require a player entity *plus*
   a second signal — a Sharks keyword in the title, or no other NHL team named.
   No per-item cost. Must handle "Sharks acquire X from Edmonton", which names
   both teams and is exactly the story you most want to keep.
3. **Classify and segregate.** An `off-team` / "Around the NHL" label: shown on
   the homepage, excluded from topic pages and RSS. Largest change, probably the
   best end state, and it keeps coverage the aggregator arguably should have.
4. ~~Promote the LLM to decision mode as-is~~ — **ruled out by the data above.**

Note the tooling cost of answering this: `validation_logs.llm_response` is
`String(100)`, so the stored JSON is truncated and unparseable. The verdict has
to be recovered with a `LIKE '%"relevant": true%'` prefix match. Widening that
column (or storing the boolean separately) would make future analysis ordinary
SQL.

**Verify with:** the measurement script pattern above — pull each tag feed at
30d and count headlines naming another NHL team without naming San Jose. Target
is materially under 10% on `/tag/trade` and `/tag/rumors` without losing
genuine two-team trade stories.

**Correction to the record:** the original SEO audit (2026-07-27) said "roughly
half the surfaced items are off-topic", based on eyeballing eight stories in the
default view. The measured figure is 10–32% depending on the page, and the
failure has a specific mechanism rather than being general noise. The audit
number was an impression; these are counts.
### RM-3 — Relevance: "Sharks" is not a hockey word

*Found 2026-08-15 in the live feed. A keyword-only fix was written, merged
([#135](https://github.com/davinoishi/Sharks-News-Aggregator/pull/135)),
deployed, measured on prod, and **reverted the same day**. Read the "why it
failed" section before attempting this again.*

**The item.** "Longstaff agrees to new deal with Sharks - Yahoo Sport" — a Sale
Sharks **rugby union** story, on the feed, from the Google Alerts source.

**The mechanism.** Distinct from RM-2, which is about *which team*; this is
about *which sport*. `check_sharks_relevance()` treats bare `sharks` as
sufficient, in the same tier as `san jose sharks`. At least four pro clubs
carry the name (Sale and Cell C/Natal in rugby union, Cronulla-Sutherland in
the NRL, Jacksonville in arena football), and the Google Alerts source queries
the bare word. Prod runs `LLM_EVALUATION_MODE=true`, so the keyword check
decided and the LLM's — correct — rejection was logged and discarded.

#### The keyword-only attempt failed. Don't repeat it.

The reverted change split the keywords into strong (`san jose sharks`,
`barracuda`) and weak (bare `sharks`, the venues), requiring a second hockey
signal for the weak tier, plus a wrong-sport veto on rugby/NRL/cricket terms.

Measured on prod, 30 days, 1,902 items reaching the gate: **31 newly rejected,
of which only 3 were correct** — the rugby item and two great-white-shark
items. The other 28 were genuine Sharks news:

- "Sharks Hire Jeff Kealty as Assistant General Manager"
- "Sharks Re-Sign Graf", "Sharks sign top remaining free agent to 3-year deal"
- "Sharks GM Mike Grier completes substantial $12.75M move"
- "Sharks Midsummer Roster Projection: Defense"
- …and a dozen more of the same shape.

**Why the pre-merge measurement missed it — the trap to avoid.** The change was
validated against `db_data_export.sql`, which reported 1 newly-rejected item in
741. That snapshot is from **January, mid-season**, and the corroboration list
leaned on NHL opponent names — a signal that is in nearly every in-season
headline ("Rangers at Sharks game 50") and in almost no **offseason** one.
July/August coverage is contracts, hirings and roster projections: no opponent,
no city, no hockey vocabulary, on `sports.yahoo.com` URLs with no hockey marker.
**Any future relevance change must be measured over both an in-season and an
offseason window before it ships.**

**The deeper reason it can't work.** "Sharks Re-Sign Graf" (real) and "Longstaff
agrees to new deal with Sharks" (rugby) are structurally identical — club name,
a transfer, no hockey token, same publisher host. No title-or-URL heuristic
separates them, so no keyword list will.

#### Agreed fix: a narrow LLM sport-check

Ask the LLM one question — *is this article about ice hockey?* — and only on the
ambiguous tier (bare `sharks`, no roster entity, no other signal): roughly 31
items a month, so the cost is negligible.

This is **not** the option RM-2 ruled out. RM-2 rejected promoting the general
*relevance* prompt, which fails because the model's roster knowledge is stale —
it thinks Nurse is an Oiler. "Which sport is this?" has no such dependency: the
model tells rugby from hockey regardless of who plays where. Fail open to the
current keyword result on any LLM error, exactly as `validate_sharks_relevance`
already does.

Keep the wrong-sport veto idea as cheap insurance alongside it, but note it
would **not** have caught this item: the Longstaff title and URL carry no rugby
marker at all.

**Verify with:** a replay script over both a January and an August window,
printing every changed verdict for reading by eye. A count cannot tell a rugby
story from a Barracuda call-up — that is how the first attempt passed review.

**Also worth doing:** add negative terms to the Google Alerts query
(`Sharks -rugby -NRL -cricket`). Note that tightening it to
`"San Jose Sharks" OR "SJ Sharks"` was simulated and is **not** recommended: on
the January snapshot it dropped five real articles to remove two bad ones.

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
