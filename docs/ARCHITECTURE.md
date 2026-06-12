# Sharks News Aggregator - Technical Architecture

This document provides a high-level overview of the Sharks News Aggregator tech stack, architecture, and how the system works.

## Production Deployment

The application runs on a **Raspberry Pi 5** (pi5-ai2) with public access via noBGP proxy.

| Service | Public URL | Local URL (on Pi) |
|---------|------------|-------------------|
| Web App | https://x2mq74oetjlz.nobgp.com | http://localhost:3001 |
| API | https://tz2k2lxwodrv.nobgp.com | http://localhost:8001 |
| BlueSky | https://bsky.app/profile/sjsharks-news.bsky.social | N/A |

## Tech Stack Overview

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | Next.js 14 (React) | Server-side rendered web interface |
| API | FastAPI (Python) | REST API for feed and submissions |
| Task Queue | Celery | Async task processing (ingestion, enrichment) |
| Scheduler | Celery Beat | Periodic task scheduling |
| Message Broker | Redis | Task queue message broker |
| Database | PostgreSQL 16 | Primary data store |
| Containerization | Docker Compose | Container orchestration |
| Public Proxy | noBGP | HTTPS access to Pi-hosted services |

---

## Docker Containers

The application runs as 7 Docker containers orchestrated by Docker Compose.
`docker-compose.yml` is the **production base**; environments are overlays:

| Use | Command |
|-----|---------|
| Production (generic) | `docker compose up -d` |
| Local development (hot-reload) | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` |
| Pi (pi5-ai2, ports 3001/8001) | `docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d` |

The base is production-shaped (no source bind mounts, no auto-reload, plain
`celery` workers). The dev overlay adds bind mounts + `--reload`/`watchfiles`
and publishes Postgres/Redis on loopback. See [SETUP_GUIDE.md](SETUP_GUIDE.md).

### 1. `db` (PostgreSQL)
- **Image:** `postgres:16`
- **Port:** 5432
- **Purpose:** Primary database storing all application data
- **Key Tables:**
  - `sources` - RSS feeds and news sources
  - `raw_items` - Unprocessed articles from feeds
  - `story_variants` - Processed articles with extracted entities
  - `clusters` - Grouped stories (same event, multiple sources)
  - `entities` - Players (synced daily from CapWages), coaches, teams
  - `tags` - Content classification (Trade, Injury, Rumors, etc.)
  - `submissions` - User-submitted links and their processing status
  - `candidate_sources` - New domains proposed from submissions (admin review)
  - `validation_logs` - Per-item relevance decisions (keyword/LLM, audit trail)
  - `bluesky_posts` - BlueSky post tracking (posted, failed, skipped)
  - `site_metrics` - Key/value counters (page views, `llm_failopen_count`, alert dedup state)
- **Backups:** the `backup` container takes a nightly `pg_dump` to `./backups/`
  (see [BACKUP_RESTORE.md](BACKUP_RESTORE.md)).

### 2. `redis` (Redis)
- **Image:** `redis:7`
- **Port:** 6379
- **Purpose:** Message broker for Celery task queue
- **Databases:**
  - DB 1: Celery broker (task messages)
  - DB 2: Celery result backend (task results)

### 3. `api` (FastAPI)
- **Port:** 8000 (dev) / 8001 (Pi production)
- **Purpose:** REST API server handling HTTP requests
- **Entry Point:** `uvicorn app.main:app` (a thin composition root; routes live
  in `app/routers/`, see [File Structure](#file-structure))
- **Public endpoints:**
  - `GET /health` - Health check; `last_scan_at` + `degraded` flag (O3)
  - `GET /feed` - Main news feed (filtered, keyset-paginated via `cursor`/`has_more`)
  - `GET /cluster/{id}` - Cluster details with all source links
  - `GET /entities?query=` - Entity (player) search for the filter UI
  - `GET /rss` - RSS 2.0 feed of the latest clusters
  - `GET /stats` - Site-wide counters
  - `POST /submit/link` - User link submissions (SSRF-guarded, rate-limited)
  - `POST /metrics/pageview`, `POST /cluster/{id}/click` - anonymous counters
- **Admin endpoints** (`/admin/*`, all behind `require_admin` — API-key header
  injected by the Next.js proxy): source health, validation logs/stats,
  BlueSky post history, LLM health.

### 4. `worker` (Celery Worker)
- **Purpose:** Executes async tasks (ingestion, enrichment)
- **Command:** `celery -A app.tasks.celery_app:celery worker`
- **Key Tasks:**
  - `ingest_source` - Fetch RSS feeds
  - `enrich_raw_item` - Process articles, extract entities, cluster
  - `process_submission` - Handle user-submitted links
  - `sync_sharks_roster` - Sync player entities from CapWages
  - `purge_old_items` / `cleanup_bogus_entities` - Housekeeping
  - `monitor_pipeline_health` - Flag stale ingest / broken sources, alert (O3)
  - `post_new_clusters` / `retry_failed_posts` - BlueSky posting

### 5. `beat` (Celery Beat)
- **Purpose:** Schedules periodic tasks
- **Command:** `celery -A app.tasks.celery_app:celery beat`
- **Scheduled Tasks:**
  | Task | Frequency | Description |
  |------|-----------|-------------|
  | `ingest_all_sources` | Every 10 minutes | Fetch RSS from all approved sources |
  | `post_new_clusters` | Every 15 minutes | Post new clusters to BlueSky |
  | `retry_failed_posts` | Hourly | Retry failed BlueSky posts |
  | `monitor_pipeline_health` | Every 30 minutes | Detect stale ingest / broken sources, alert (O3) |
  | `sync_sharks_roster` | Daily | Sync roster from CapWages (~77 players) |
  | `purge_old_items` | Daily | Remove items older than 30 days |

### 6. `web` (Next.js)
- **Port:** 3000 (dev) / 3001 (Pi production)
- **Purpose:** Frontend web application. The browser never talks to FastAPI
  directly — Next.js API routes (`web/app/api/*`) proxy to the `api` container.
- **Dynamic API Detection:** Automatically detects local vs. noBGP access
- **Key Pages:**
  - `/` - Main feed: tag + entity filters, "Load more" pagination, clickable headlines
  - `/submit` - Public link submission form
  - `/admin`, `/admin/sources`, `/admin/view` - Admin views (HTTP Basic gated)
  - `/about`, `/legal` - About + terms/privacy
  - `/rss` - RSS 2.0 feed (proxied from the API)

### 7. `backup` (Postgres)
- **Image:** `postgres:16` (reuses the client tools)
- **Purpose:** Nightly `pg_dump` of the database to the host-mounted `./backups/`
  with 14-day retention. See [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INGESTION FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────┐         ┌──────────┐         ┌──────────┐
    │  Celery  │ timer   │  Celery  │  task   │  Celery  │
    │   Beat   │────────▶│  Broker  │────────▶│  Worker  │
    │          │         │ (Redis)  │         │          │
    └──────────┘         └──────────┘         └────┬─────┘
                                                   │
                                                   ▼
                                         ┌─────────────────┐
                                         │ ingest_all_     │
                                         │ sources()       │
                                         └────────┬────────┘
                                                  │
                         ┌────────────────────────┼────────────────────────┐
                         ▼                        ▼                        ▼
                ┌────────────────┐       ┌────────────────┐       ┌────────────────┐
                │ ingest_source  │       │ ingest_source  │       │ ingest_source  │
                │ (NHL.com RSS)  │       │ (SJHN RSS)     │       │ (PHR RSS)      │
                └───────┬────────┘       └───────┬────────┘       └───────┬────────┘
                        │                        │                        │
                        └────────────────────────┼────────────────────────┘
                                                 ▼
                                        ┌────────────────┐
                                        │   raw_items    │
                                        │   (table)      │
                                        └───────┬────────┘
                                                │
                                                ▼
                                        ┌────────────────┐
                                        │ enrich_raw_    │
                                        │ item()         │
                                        └───────┬────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    ▼                           ▼                           ▼
           ┌────────────────┐          ┌────────────────┐          ┌────────────────┐
           │ Relevance      │          │ Entity         │          │ Event Type     │
           │ Check          │          │ Extraction     │          │ Classification │
           └───────┬────────┘          └───────┬────────┘          └───────┬────────┘
                   │                           │                           │
                   │    (skip if irrelevant)   │                           │
                   ▼                           ▼                           ▼
                                        ┌────────────────┐
                                        │ Clustering     │
                                        │ Algorithm      │
                                        └───────┬────────┘
                                                │
                         ┌──────────────────────┴──────────────────────┐
                         ▼                                             ▼
                ┌────────────────┐                            ┌────────────────┐
                │ Create new     │                            │ Add to existing│
                │ cluster        │                            │ cluster        │
                └───────┬────────┘                            └───────┬────────┘
                        │                                             │
                        └─────────────────────┬───────────────────────┘
                                              ▼
                                     ┌────────────────┐
                                     │   clusters     │
                                     │ story_variants │
                                     │   (tables)     │
                                     └────────────────┘
```

---

## Key Processes

### 1. RSS Ingestion (`api/app/tasks/ingest.py`)

**Function:** `ingest_all_sources()`
- Triggered every 10 minutes by Celery Beat
- Queries approved sources via `get_active_sources()` (the synthetic
  "User Submissions" source is excluded — it is not a fetchable feed)
- Spawns parallel `ingest_source()` tasks

**Function:** `ingest_rss()`
- Fetches RSS feed using `feedparser`
- Creates `raw_item` records for new articles
- Deduplicates by URL hash
- Triggers `enrich_raw_item()` for each new item

### 2. Enrichment (`api/app/tasks/enrich.py` → `api/app/enrichment/`)

`enrich.py` is a thin Celery orchestrator (brief 07); the logic lives in
`app/enrichment/`: `entities.py` (extraction), `classify.py` (relevance +
event/tag classification), `clustering.py` (similarity + match-or-create),
`teams.py` (NHL opponent table).

**Function:** `enrich_raw_item()`
1. **Relevance Check** - Filters out non-Sharks content from general feeds
2. **Token Normalization** - Extracts keywords for clustering
3. **Entity Extraction** - Finds player/coach mentions
4. **Event Classification** - Categorizes as trade/injury/game/etc.
5. **Clustering** - Matches to existing cluster or creates new one
6. **Tagging** - Assigns tags (Rumors, Trade, Injury, Game, etc.)

**Relevance** (`enrichment/classify.py`): keyword check ("Sharks", "Barracuda",
"SAP Center" + known player/coach entities) with optional LLM (OpenRouter)
adjudication. On an LLM error the check **fails open to keyword matching** and
increments the `llm_failopen_count` metric (C5). Sources can opt out via
`skip_relevance_check` metadata.

**Function:** `match_or_create_cluster()` (`enrichment/clustering.py`)
- Calculates similarity score: `S = 0.55*E + 0.35*T + 0.10*K`
  - E = Entity overlap (excluding team entities)
  - T = Token Jaccard similarity
  - K = Event type compatibility
- Match threshold: S >= 0.62

### 3. API Request Flow (`api/app/main.py` + `api/app/routers/`)

```
Browser Request
      │
      ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Next.js   │───▶│   FastAPI   │───▶│  PostgreSQL │
│   (web)     │    │   (api)     │    │   (db)      │
└─────────────┘    └─────────────┘    └─────────────┘
      │                   │
      │◀──────────────────┘
      ▼
   Browser
```

### 4. Clustering Algorithm

Stories are grouped when they cover the same event from multiple sources:

1. **Time Window** - Only consider clusters from last 72 hours (24h for games)
2. **Entity Match** - Must share player/coach entities (team entity excluded)
3. **Token Similarity** - Jaccard similarity of normalized keywords
4. **Event Compatibility** - Same or compatible event types

**Thresholds:**
- Entity overlap: >= 0.50
- Token similarity (no entities): >= 0.40
- Overall score: >= 0.62

---

## Database Schema (Key Tables)

### sources
```sql
- id, name, category (official/press/other)
- feed_url, ingest_method (rss/html/api)
- status (approved/rejected)
- metadata (JSON: skip_relevance_check, etc.)
```

### raw_items
```sql
- id, source_id, original_url, canonical_url
- raw_title, raw_description
- published_at, ingest_hash (for deduplication)
```

### story_variants
```sql
- id, raw_item_id, source_id
- title, url, published_at
- tokens[], entities[], event_type
```

### clusters
```sql
- id, headline, event_type
- first_seen_at, last_seen_at
- tokens[], entities_agg[]
- source_count, status
```

### entities
```sql
- id, name, slug, entity_type (player/coach/team/staff)
```

### tags
```sql
- id, name, slug, display_color
- (Trade, Injury, Lineup, Recall, Waiver, Signing, Prospect, Game, Barracuda, Rumors, Opinion)
```

---

## Configuration

### Environment Variables

See [`.env.example`](../.env.example) for the full list. Highlights:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection string (required) |
| `CELERY_BROKER_URL` | - | Redis broker URL (required) |
| `REDIS_PASSWORD` | - | Redis password (required; `--requirepass`) |
| `ADMIN_API_KEY` | - | Admin auth key the Next.js proxy injects (required; empty ⇒ admin denied) |
| `ADMIN_PANEL_PASSWORD` | - | HTTP Basic password gating `/admin` (required) |
| `INGEST_INTERVAL_MINUTES` | 10 | RSS fetch frequency |
| `MAX_ARTICLE_AGE_DAYS` | 7 | Reject articles older than this many days |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowed origins (`*` on the Pi) |
| `PUBLIC_SITE_URL` | `http://localhost:3000` | Site URL for RSS channel metadata |
| `LOG_LEVEL` | `INFO` | Logging verbosity (C4) |
| `ALERT_WEBHOOK_URL` | (empty) | Webhook for degraded-pipeline alerts (O3) |
| `OPENROUTER_API_KEY` | (empty) | Enables LLM relevance/classification |

### Configurable Thresholds (`api/app/core/config.py`)
```python
cluster_similarity_threshold = 0.62
entity_overlap_threshold = 0.50
token_similarity_threshold = 0.40
ingest_interval_minutes = 10
max_article_age_days = 7
submission_rate_limit_per_ip = 10
```

---

## File Structure

```
sharks-news-aggregator/
├── api/                      # Backend API
│   ├── alembic/              # Database migrations (see docs/MIGRATIONS.md)
│   └── app/
│       ├── main.py           # Thin FastAPI composition root (wires routers)
│       ├── routers/          # Route modules: health, feed, submit, metrics, admin
│       ├── schemas.py        # Pydantic request/response models
│       ├── dependencies.py   # require_admin, real-client-IP, rate limits
│       ├── utils.py          # Shared helpers (parse_since, parse_llm_approved)
│       ├── core/
│       │   ├── config.py        # Settings & thresholds
│       │   ├── database.py      # DB connection
│       │   ├── queries.py       # Feed query builders
│       │   ├── db_utils.py      # DB helpers + site-metric counters
│       │   ├── health_checks.py # Shared pipeline-health check (O3)
│       │   ├── logging_config.py# LOG_LEVEL-aware logging (C4)
│       │   ├── constants.py     # Cross-module constants
│       │   └── url_guard.py     # SSRF guard for submitted links
│       ├── models/           # SQLAlchemy models (source, cluster, …, site_metrics)
│       ├── enrichment/       # entities, classify, clustering, teams
│       ├── tasks/            # Celery tasks
│       │   ├── celery_app.py    # Celery config & beat schedule
│       │   ├── ingest.py        # RSS fetching
│       │   ├── enrich.py        # Orchestrates app/enrichment/*
│       │   ├── sync_roster.py   # Daily roster sync from CapWages
│       │   ├── maintenance.py   # Purge, cleanup, pipeline-health monitor
│       │   ├── submissions.py   # User-submitted links
│       │   └── bluesky.py       # BlueSky posting
│       ├── scripts/          # Management scripts
│       └── tests/ (api/tests)# pytest suite (brief 06)
├── web/                      # Frontend (Next.js App Router)
│   └── app/
│       ├── page.tsx          # Main feed page
│       ├── submit/           # Public submission page
│       ├── admin/            # Admin views (Basic-auth gated)
│       ├── rss/route.ts      # RSS proxy
│       ├── api/              # Server-side proxy routes → INTERNAL_API_URL
│       └── components/       # React components
├── infra/
│   ├── postgres/init/        # DB bootstrap SQL
│   └── backup/backup.sh      # Nightly pg_dump loop
├── docker-compose.yml        # Production base
├── docker-compose.dev.yml    # Dev overlay (bind mounts + hot-reload)
├── docker-compose.pi.yml     # pi5-ai2 overlay (ports 3001/8001)
├── .github/workflows/        # CI (lint + tests + build) and security verify
└── initial_sources.csv       # Seed data for sources
```

---

## External Integrations

1. **RSS Feeds** - Primary content source (via the feedparser library)
2. **CapWages** - Daily roster sync for entity database (full organization: NHL + AHL + reserves)
3. **OpenRouter** - LLM relevance/classification (Gemma), with keyword fallback
4. **BlueSky** - Auto-posts new clusters to [@sjsharks-news.bsky.social](https://bsky.app/profile/sjsharks-news.bsky.social)
5. **rss.app** - Twitter feed conversion (Friedman, LeBrun)
6. **noBGP** - HTTPS proxy for public access to Pi-hosted services

---

## Security Considerations

- **Admin auth (S1):** all `/admin/*` routes require an API key the Next.js
  proxy injects; the `/admin` pages are additionally behind HTTP Basic. The
  backend fails closed if `ADMIN_API_KEY` is unset.
- **SSRF guard (S2):** user-submitted URLs are validated (scheme/host/IP,
  redirect hops, body size) before the worker fetches them.
- **Rate limiting (S3):** proxy-aware (real client IP via trusted
  `X-Forwarded-For`) on `/submit/link` and the public counter endpoints.
- **Network isolation (S4):** Postgres/Redis are not published to the host in
  production; Redis requires a password.
- **Hygiene (S5):** security headers in `next.config.js`, constant-time admin
  key comparison, SHA-256-hashed submitter IPs (no raw IPs stored).
- Relevance filtering prevents content injection from general feeds.
- HTTPS via noBGP proxy; `restart: unless-stopped` on all containers.
