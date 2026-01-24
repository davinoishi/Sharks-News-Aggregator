# Sharks News Aggregator

A comprehensive news aggregation and clustering system for San Jose Sharks hockey news. Automatically ingests news from multiple sources, enriches articles with entity extraction and tagging, clusters similar stories, and presents them through a modern web interface.

## Features

### Core Functionality
- **Multi-Source RSS Ingestion** - Aggregates news from 15+ sources including San Jose Hockey Now, Mercury News, NBC Sports, and more
- **Enrichment Pipeline** - Extracts entities (players, coaches), assigns tags, and classifies event types using keyword matching and NLP
- **Smart Clustering** - Groups similar stories from different sources using entity overlap and token similarity scoring
- **Automated Roster Sync** - Daily synchronization with CapWages to keep full organization player database current
- **Modern Web UI** - Next.js frontend with filtering, tag navigation, and responsive design

### Entity Detection
Automatically detects and links:
- **Players** - Full Sharks organization (synced daily from CapWages: NHL roster + AHL + unsigned reserves)
- **Coaches** - Head coach and assistant coaches
- **Teams** - San Jose Sharks and affiliate teams

### Tag System
- News, Rumors
- Trade, Injury, Lineup, Signing, Draft
- Game Preview, Game Recap, Analysis

### Event Classification
- Trade news (player movements)
- Injury reports
- Lineup changes
- Game coverage
- General news and analysis

## Architecture

```
┌─────────────────┐
│   Next.js Web   │  ← User Interface (localhost:3000)
└────────┬────────┘
         │
         ↓ HTTP
┌─────────────────┐
│   FastAPI API   │  ← REST API (localhost:8000)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   PostgreSQL    │  ← Data Storage (localhost:5432)
└─────────────────┘

Background Workers:
┌─────────────────┐
│  Celery Worker  │  ← Async task processing
└─────────────────┘
┌─────────────────┐
│  Celery Beat    │  ← Scheduled tasks (RSS ingest, roster sync)
└─────────────────┘
┌─────────────────┐
│     Redis       │  ← Message broker & cache
└─────────────────┘
```

## Tech Stack

**Backend:**
- Python 3.11
- FastAPI (REST API)
- SQLAlchemy (ORM)
- PostgreSQL (Database)
- Celery (Task queue)
- Redis (Message broker)
- NLTK (Natural language processing)

**Frontend:**
- Next.js 14 (React framework)
- TypeScript
- Tailwind CSS
- Client-side rendering

**Infrastructure:**
- Docker & Docker Compose
- Celery Beat (Scheduler)

## Quick Start

### Prerequisites
- Docker and Docker Compose

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/sharks-news-aggregator.git
cd sharks-news-aggregator
```

2. Create `.env` file:
```bash
cp .env.example .env
```

3. Start all services:
```bash
docker-compose up -d
```

4. Wait for services to initialize (~30 seconds)

5. Seed initial data (coaches, teams):
```bash
docker-compose exec api python -m app.scripts.seed_entities
```

6. Access the application:
- **Frontend:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs
- **API:** http://localhost:8000

### First-Time Setup

Trigger initial RSS ingestion:
```bash
docker-compose exec api python -c "
from app.tasks.ingest import ingest_all_sources
ingest_all_sources.delay()
print('Ingestion started! Check logs: docker-compose logs -f worker')
"
```

The system will:
1. Fetch articles from all RSS sources
2. Enrich them (extract entities, assign tags, classify events)
3. Cluster similar stories
4. Display them in the web UI

## Usage

### Web Interface

Open http://localhost:3000 to:
- View clustered news feed
- Filter by tags (Trade, Injury, News, etc.)
- Filter by time range (24h, 7d, 30d)
- Expand clusters to see all source articles
- Click links to read full articles

### API Endpoints

**Get News Feed:**
```bash
curl "http://localhost:8000/feed?tags=trade,injury&since=24h&limit=50"
```

**Get Cluster Details:**
```bash
curl "http://localhost:8000/cluster/{cluster_id}"
```

**Submit New Link:**
```bash
curl -X POST "http://localhost:8000/submit" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/sharks-news", "source_name": "Example News"}'
```

**Health Check:**
```bash
curl "http://localhost:8000/health"
```

### Automated Tasks

**RSS Ingestion** - Runs every 15 minutes (configurable)
- Fetches new articles from all sources
- Queues them for enrichment
- Auto-clusters similar stories

**Roster Sync** - Runs daily
- Syncs full Sharks organization from CapWages (NHL + AHL + reserves)
- Adds new players, updates existing ones
- Removes departed players to prevent false positive matches

**Cache Cleanup** - Runs hourly
- Removes expired feed cache entries
- Keeps database clean

### Manual Operations

**Trigger RSS Ingestion:**
```bash
docker-compose exec api python -c "
from app.tasks.ingest import ingest_all_sources
ingest_all_sources.delay()
"
```

**Trigger Roster Sync:**
```bash
docker-compose exec api python -c "
from app.tasks.sync_roster import sync_sharks_roster
sync_sharks_roster.delay()
"
```

**View Worker Logs:**
```bash
docker-compose logs -f worker
```

**Check Database:**
```bash
# List all entities
docker-compose exec db psql -U sharks -d sharks -c \
  "SELECT COUNT(*), entity_type FROM entities GROUP BY entity_type;"

# View recent clusters
docker-compose exec db psql -U sharks -d sharks -c \
  "SELECT id, headline, event_type, source_count FROM clusters ORDER BY last_seen_at DESC LIMIT 10;"
```

## Configuration

### Environment Variables

Key settings in `.env`:

```bash
# Ingestion
INGEST_INTERVAL_MINUTES=10

# Database
DATABASE_URL=postgresql+psycopg://sharks:sharks@db:5432/sharks

# Redis
CELERY_BROKER_URL=redis://redis:6379/1

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### RSS Sources

Sources are managed in the database `sources` table. See `initial_sources.csv` for the seed data format.

## Project Structure

```
sharks-news-aggregator/
├── api/                      # FastAPI backend
│   ├── app/
│   │   ├── api/              # API routes
│   │   ├── core/             # Core utilities (enrichment, clustering)
│   │   ├── models/           # SQLAlchemy models
│   │   ├── tasks/            # Celery tasks (ingest, enrich, sync)
│   │   ├── data/             # RSS sources, seed data
│   │   └── scripts/          # Utility scripts
│   ├── Dockerfile
│   └── requirements.txt
├── web/                      # Next.js frontend
│   ├── app/
│   │   ├── components/       # React components
│   │   ├── types.ts          # TypeScript types
│   │   └── api-client.ts     # API wrapper
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml        # Docker orchestration
├── .env.example              # Environment template
└── README.md                 # This file
```

## Documentation

- **[CURRENT_STATUS.md](CURRENT_STATUS.md)** - Project completion status
- **[FRONTEND_IMPLEMENTATION.md](FRONTEND_IMPLEMENTATION.md)** - Frontend features and usage
- **[ROSTER_SYNC.md](ROSTER_SYNC.md)** - Automated roster sync documentation
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and data flow

## Development

### Running Tests

```bash
# Backend tests
docker-compose exec api pytest

# Frontend tests
docker-compose exec web npm test
```

### Database Migrations

```bash
# Generate migration
docker-compose exec api alembic revision --autogenerate -m "description"

# Apply migrations
docker-compose exec api alembic upgrade head
```

### Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f worker
docker-compose logs -f api
docker-compose logs -f web
```

### Rebuild Services

```bash
# Rebuild all
docker-compose build

# Rebuild specific service
docker-compose build api
docker-compose build web
```

## Troubleshooting

**API not responding:**
```bash
docker-compose logs api
docker-compose restart api
```

**Worker not processing tasks:**
```bash
docker-compose logs worker
docker-compose restart worker beat
```

**Frontend not loading:**
```bash
docker-compose logs web
docker-compose restart web
```

**Database connection issues:**
```bash
docker-compose logs db
docker-compose restart db
```

**Clear all data and restart:**
```bash
docker-compose down -v
docker-compose up -d
```

## Roadmap

### Completed
- ✅ RSS ingestion from multiple sources
- ✅ Enrichment pipeline (entity extraction, tagging, event classification)
- ✅ Story clustering with entity overlap and token similarity
- ✅ REST API with filtering
- ✅ Web UI with responsive design
- ✅ Automated roster sync from CapWages (full organization)
- ✅ Departed player removal (prevents false positives)
- ✅ Celery task queue and scheduling
- ✅ Automatic purge of items older than 30 days

### In Progress
- 🔄 Entity filtering in web UI
- 🔄 Link submission form

### Planned
- 📋 User authentication and preferences
- 📋 Real-time updates (WebSocket)
- 📋 Search functionality
- 📋 Social sharing
- 📋 Push notifications (ntfy.sh)
- 📋 Mobile app

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Acknowledgments

- CapWages for comprehensive organization roster data
- All the excellent news sources covering the Sharks
