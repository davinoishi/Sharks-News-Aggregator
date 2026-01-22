# Sharks News Aggregator

A comprehensive news aggregation and clustering system for San Jose Sharks hockey news. Automatically ingests news from multiple sources, enriches articles with AI-powered entity extraction and tagging, clusters similar stories, and presents them through a modern web interface.

## Features

### Core Functionality
- **Multi-Source RSS Ingestion** - Aggregates news from 15+ sources including The Athletic, ESPN, Mercury News, and more
- **AI-Powered Enrichment** - Uses Claude AI to extract entities (players, coaches), assign tags, classify event types, and generate headlines
- **Smart Clustering** - Groups similar stories from different sources using embedding-based similarity
- **Automated Roster Sync** - Daily synchronization with NHL API to keep player database current
- **Modern Web UI** - Next.js frontend with filtering, tag navigation, and responsive design

### Entity Detection
Automatically detects and links:
- **Players** - All San Jose Sharks roster players (synced daily from NHL API)
- **Coaches** - Head coach and assistant coaches
- **Teams** - San Jose Sharks and affiliate teams
- **Prospects** - Draft picks and prospects

### Tag System
- News, Rumors (Press), Rumors (Other)
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
- Anthropic Claude API (AI enrichment)

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
- Anthropic API key (for AI enrichment)

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

3. Add your Anthropic API key to `.env`:
```
ANTHROPIC_API_KEY=your_api_key_here
```

4. Start all services:
```bash
docker-compose up -d
```

5. Wait for services to initialize (~30 seconds)

6. Seed initial data (coaches, teams, prospects):
```bash
docker-compose exec api python -m app.scripts.seed_entities
```

7. Access the application:
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
2. Enrich them with AI (entities, tags, headlines)
3. Cluster similar stories
4. Display them in the web UI

## Usage

### Web Interface

Open http://localhost:3000 to:
- View clustered news feed
- Filter by tags (Trade, Injury, News, etc.)
- Filter by time range (24h, 7d, 30d, all)
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

**Roster Sync** - Runs daily at midnight UTC
- Syncs all Sharks players from NHL API
- Updates player metadata (position, jersey number, etc.)
- Adds new players, updates existing ones

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
# API Keys
ANTHROPIC_API_KEY=your_key_here

# Ingestion
INGEST_INTERVAL_MINUTES=15

# Database
POSTGRES_USER=sharks
POSTGRES_PASSWORD=sharks123
POSTGRES_DB=sharks

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
```

### RSS Sources

Edit `api/app/data/rss_sources.json` to add/remove news sources.

### Enrichment Prompts

Modify prompts in `api/app/core/enrichment.py` to customize AI behavior.

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
- ✅ AI-powered enrichment (entities, tags, headlines)
- ✅ Story clustering with embeddings
- ✅ REST API with filtering
- ✅ Web UI with responsive design
- ✅ Automated roster sync from NHL API
- ✅ Celery task queue and scheduling

### In Progress
- 🔄 Entity filtering in web UI
- 🔄 Link submission form

### Planned
- 📋 User authentication and preferences
- 📋 Real-time updates (WebSocket)
- 📋 Search functionality
- 📋 Social sharing
- 📋 Email notifications
- 📋 Mobile app
- 📋 Historical player status tracking
- 📋 AHL roster sync (San Jose Barracuda)
- 📋 Prospect tracking

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Acknowledgments

- NHL API for official roster data
- Anthropic Claude for AI-powered enrichment
- All the excellent news sources covering the Sharks
