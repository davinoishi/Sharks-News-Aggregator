# Sharks News Aggregator - Technical Architecture

This document provides a high-level overview of the Sharks News Aggregator tech stack, architecture, and how the system works.

## Tech Stack Overview

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | Next.js 14 (React) | Server-side rendered web interface |
| API | FastAPI (Python) | REST API for feed and submissions |
| Task Queue | Celery | Async task processing (ingestion, enrichment) |
| Scheduler | Celery Beat | Periodic task scheduling |
| Message Broker | Redis | Task queue message broker |
| Database | PostgreSQL 16 | Primary data store |
| Containerization | Docker Compose | Local development orchestration |

---

## Docker Containers

The application runs as 6 Docker containers orchestrated by `docker-compose.yml`:

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

### 2. `redis` (Redis)
- **Image:** `redis:7`
- **Port:** 6379
- **Purpose:** Message broker for Celery task queue
- **Databases:**
  - DB 1: Celery broker (task messages)
  - DB 2: Celery result backend (task results)

### 3. `api` (FastAPI)
- **Port:** 8000
- **Purpose:** REST API server handling HTTP requests
- **Entry Point:** `uvicorn app.main:app`
- **Key Endpoints:**
  - `GET /health` - Health check with last scan time
  - `GET /feed` - Main news feed (filtered, paginated)
  - `GET /cluster/{id}` - Cluster details with all source links
  - `POST /submit/link` - User link submissions

### 4. `worker` (Celery Worker)
- **Purpose:** Executes async tasks (ingestion, enrichment)
- **Command:** `celery -A app.tasks.celery_app:celery worker`
- **Key Tasks:**
  - `ingest_source` - Fetch RSS feeds
  - `enrich_raw_item` - Process articles, extract entities, cluster
  - `process_submission` - Handle user-submitted links
  - `sync_sharks_roster` - Sync player entities from CapWages
  - `purge_old_items` - Remove clusters/items older than 30 days

### 5. `beat` (Celery Beat)
- **Purpose:** Schedules periodic tasks
- **Command:** `celery -A app.tasks.celery_app:celery beat`
- **Scheduled Tasks:**
  - `ingest_all_sources` - Every 10 minutes (configurable)
  - `sync_sharks_roster` - Daily roster sync from CapWages (full organization)
  - `cleanup_expired_cache` - Hourly cache cleanup
  - `purge_old_items` - Daily cleanup of items older than 30 days

### 6. `web` (Next.js)
- **Port:** 3000
- **Purpose:** Frontend web application
- **Key Pages:**
  - `/` - Main feed page with filters
  - `/legal` - Terms and privacy policy

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
- Triggered every 15 minutes by Celery Beat
- Queries all approved sources from database
- Spawns parallel `ingest_source()` tasks

**Function:** `ingest_rss()`
- Fetches RSS feed using `feedparser`
- Creates `raw_item` records for new articles
- Deduplicates by URL hash
- Triggers `enrich_raw_item()` for each new item

### 2. Enrichment (`api/app/tasks/enrich.py`)

**Function:** `enrich_raw_item()`
1. **Relevance Check** - Filters out non-Sharks content from general feeds
2. **Token Normalization** - Extracts keywords for clustering
3. **Entity Extraction** - Finds player/coach mentions
4. **Event Classification** - Categorizes as trade/injury/game/etc.
5. **Clustering** - Matches to existing cluster or creates new one
6. **Tagging** - Assigns tags (News, Rumors, Trade, etc.)

**Function:** `check_sharks_relevance()`
- Checks for "Sharks", "SJ Sharks", "Barracuda", "SAP Center" mentions
- Checks for known entity mentions (players, coaches)
- Sources can opt out via `skip_relevance_check` metadata

**Function:** `match_or_create_cluster()`
- Calculates similarity score: `S = 0.55*E + 0.35*T + 0.10*K`
  - E = Entity overlap (excluding team entities)
  - T = Token Jaccard similarity
  - K = Event type compatibility
- Match threshold: S >= 0.62

### 3. API Request Flow (`api/app/main.py`)

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
- (News, Trade, Injury, Rumors Press, Barracuda, etc.)
```

---

## Configuration

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection string |
| `CELERY_BROKER_URL` | - | Redis broker URL |
| `INGEST_INTERVAL_MINUTES` | 15 | RSS fetch frequency |
| `ALLOWED_ORIGINS` | localhost:3000 | CORS allowed origins |

### Configurable Thresholds (`api/app/core/config.py`)
```python
cluster_similarity_threshold = 0.62
entity_overlap_threshold = 0.50
token_similarity_threshold = 0.40
ingest_interval_minutes = 15
submission_rate_limit_per_ip = 10
```

---

## File Structure

```
sharks-news-aggregator/
├── api/                      # Backend API
│   └── app/
│       ├── main.py           # FastAPI app & endpoints
│       ├── core/
│       │   ├── config.py     # Settings & thresholds
│       │   ├── database.py   # DB connection
│       │   └── queries.py    # Feed query builders
│       ├── models/           # SQLAlchemy models
│       │   ├── source.py
│       │   ├── cluster.py
│       │   ├── story_variant.py
│       │   └── ...
│       ├── tasks/            # Celery tasks
│       │   ├── celery_app.py # Celery config & beat schedule
│       │   ├── ingest.py     # RSS fetching
│       │   ├── enrich.py     # Entity extraction & clustering
│       │   ├── sync_roster.py # Daily roster sync from CapWages
│       │   ├── maintenance.py # Purge old items, cache cleanup
│       │   └── ...
│       └── scripts/          # Management scripts
├── web/                      # Frontend
│   └── app/
│       ├── page.tsx          # Main feed page
│       ├── legal/page.tsx    # Legal page
│       ├── components/       # React components
│       └── api-client.ts     # API client
├── infra/
│   └── postgres/init/        # DB initialization SQL
├── docker-compose.yml        # Container orchestration
└── initial_sources.csv       # Seed data for sources
```

---

## External Integrations

1. **RSS Feeds** - Primary content source (feedparser library)
2. **CapWages** - Daily roster sync for entity database (full organization: NHL + AHL + reserves)
3. **rss.app** - Twitter feed conversion (Friedman, LeBrun)

---

## Security Considerations

- Rate limiting on submissions (10/hour per IP)
- CORS configured for frontend origin only
- No user authentication (read-only public API)
- No cookies or tracking
- Relevance filtering prevents content injection from general feeds
