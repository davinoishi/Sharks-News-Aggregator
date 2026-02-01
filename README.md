# Sharks News Aggregator

A comprehensive news aggregation and clustering system for San Jose Sharks hockey news. Automatically ingests news from multiple sources, enriches articles with entity extraction and tagging, clusters similar stories, and presents them through a modern web interface.

## Live Demo

- **Web App**: https://x2mq74oetjlz.nobgp.com
- **BlueSky**: [@sjsharks-news.bsky.social](https://bsky.app/profile/sjsharks-news.bsky.social)

## Features

### Core Functionality
- **Multi-Source RSS Ingestion** - Aggregates news from 24+ sources including San Jose Hockey Now, Mercury News, NBC Sports, NHL.com, and more
- **Enrichment Pipeline** - Extracts entities (players, coaches), assigns tags, and classifies event types using keyword matching and NLP
- **Smart Clustering** - Groups similar stories from different sources using entity overlap and token similarity scoring
- **Automated Roster Sync** - Daily synchronization with CapWages to keep full organization player database current
- **BlueSky Integration** - Automatic posting of news clusters to [@sjsharks-news.bsky.social](https://bsky.app/profile/sjsharks-news.bsky.social)
- **Modern Web UI** - Next.js frontend with filtering, tag navigation, and responsive design
- **Server-Side API Proxy** - Next.js API routes proxy all backend requests, eliminating CORS and exposing only the frontend URL

### Entity Detection
Automatically detects and links:
- **Players** - Full Sharks organization (synced daily from CapWages: NHL roster + AHL + unsigned reserves)
- **Coaches** - Head coach and assistant coaches
- **Teams** - San Jose Sharks and affiliate teams

### Tag System
- Rumors, Trade, Injury, Signing, Game
- Lineup, Recall, Waiver, Prospect
- Official, Barracuda

### Event Classification
- Trade news (player movements)
- Injury reports
- Lineup changes
- Game coverage
- General news and analysis

## Architecture

```
┌─────────────────┐
│   Next.js Web   │  ← User Interface
└────────┬────────┘
         │
         ↓ HTTP
┌─────────────────┐
│   FastAPI API   │  ← REST API
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   PostgreSQL    │  ← Data Storage
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
- noBGP (Public proxy)

## Deployment

### Production (Raspberry Pi 5)

The application runs on a Raspberry Pi 5 (pi5-ai2) with public access via noBGP proxy.

**Access URL:**
- Web: https://x2mq74oetjlz.nobgp.com (or `localhost:3001` on Pi)

**Deploy to Pi:**
```bash
# SSH to Pi and clone repo
git clone https://github.com/davinoishi/Sharks-News-Aggregator.git /opt/Sharks-News-Aggregator
cd /opt/Sharks-News-Aggregator

# Start services (uses Pi-specific config with ports 3001/8001)
docker compose -f docker-compose.pi.yml up -d
```

### Local Development

```bash
# Clone the repository
git clone https://github.com/davinoishi/Sharks-News-Aggregator.git
cd sharks-news-aggregator

# Start all services (uses default ports 3000/8000)
docker-compose up -d

# Access the application
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

### Publishing with noBGP

This project uses [noBGP](https://docs.nobgp.com/) to publish the web app to a public URL without exposing your local IP address or opening any ports in your router/firewall. The noBGP agent runs on your machine and creates a secure tunnel to the noBGP network.

**AI-Assisted Deployment:** With the noBGP agent installed and the noBGP MCP server connected to Claude (or your LLM of choice), you can deploy this entire project through natural language commands. The LLM can pull the repo, start Docker containers, and publish services - all without you needing to SSH into the machine.

```bash
# Install noBGP agent on your endpoint
# See https://docs.nobgp.com/ for installation

# Publish a local service (example)
nobgp service publish --port 3001 --title "Sharks News"
```

## Quick Start

### Prerequisites
- Docker and Docker Compose

### Setup

1. Clone the repository:
```bash
git clone https://github.com/davinoishi/Sharks-News-Aggregator.git
cd sharks-news-aggregator
```

2. Start all services:
```bash
docker-compose up -d
```

3. Wait for services to initialize (~30 seconds)

4. Seed initial data (coaches, teams):
```bash
docker-compose exec api python -m app.scripts.seed_entities
```

5. Access the application:
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

Open http://localhost:3000 (or the noBGP proxy URL) to:
- View clustered news feed
- Filter by tags (Trade, Injury, Game, etc.)
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
curl -X POST "http://localhost:8000/submit/link" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/sharks-news"}'
```

**Health Check:**
```bash
curl "http://localhost:8000/health"
```

### Automated Tasks

**RSS Ingestion** - Runs every 10 minutes (configurable)
- Fetches new articles from all 24 sources
- Queues them for enrichment
- Auto-clusters similar stories

**BlueSky Posting** - Runs every 15 minutes
- Posts new story clusters to [@sjsharks-news.bsky.social](https://bsky.app/profile/sjsharks-news.bsky.social)
- Includes headline, event type, source count, and hashtags
- Rate-limited to avoid spam (5-minute cooldown between posts)
- Retries failed posts hourly (up to 3 attempts)

**Roster Sync** - Runs daily
- Syncs full Sharks organization from CapWages (NHL + AHL + reserves)
- Adds new players, updates existing ones
- Removes departed players to prevent false positive matches

**Cache Cleanup** - Runs hourly
- Removes expired feed cache entries
- Keeps database clean

## Configuration

### Environment Variables

Key settings in `.env`:

```bash
# Ingestion
INGEST_INTERVAL_MINUTES=10

# Database (set via .env file - use strong passwords!)
DATABASE_URL=postgresql+psycopg://user:password@db:5432/sharks

# Redis
CELERY_BROKER_URL=redis://redis:6379/1

# Frontend (server-side API proxy)
INTERNAL_API_URL=http://api:8000

# BlueSky Integration
BLUESKY_ENABLED=true
BLUESKY_HANDLE=sjsharks-news.bsky.social
BLUESKY_APP_PASSWORD=your_app_password  # Get from bsky.app > Settings > App Passwords
BLUESKY_MIN_SOURCES=1
BLUESKY_POST_INTERVAL_MINUTES=15
```

### RSS Sources

24 approved sources including:
- San Jose Hockey Now
- The Mercury News - Sharks
- NBC Sports Bay Area - Sharks
- NHL.com - Sharks Official
- Fear the Fin
- Blades of Teal
- Teal Town USA
- Pro Hockey Rumors
- Yahoo Sports - Sharks
- SF Gate - Sharks
- And more...

Sources are managed in the database `sources` table.

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
│   │   └── api-client.ts     # API wrapper with dynamic URL detection
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml        # Docker orchestration (development)
├── docker-compose.pi.yml     # Docker orchestration (Pi production)
└── README.md                 # This file
```

## Documentation

- **[CURRENT_STATUS.md](CURRENT_STATUS.md)** - Project completion status
- **[FRONTEND_IMPLEMENTATION.md](FRONTEND_IMPLEMENTATION.md)** - Frontend features and usage
- **[ROSTER_SYNC.md](ROSTER_SYNC.md)** - Automated roster sync documentation
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and data flow
- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** - Detailed setup walkthrough
- **[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)** - Production deployment checklist

## Development

### Viewing Logs

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

**Clear all data and restart:**
```bash
docker-compose down -v
docker-compose up -d
```

## Roadmap

### Completed
- RSS ingestion from multiple sources (24 sources)
- Enrichment pipeline (entity extraction, tagging, event classification)
- Story clustering with entity overlap and token similarity
- REST API with filtering
- Web UI with responsive design
- Automated roster sync from CapWages (full organization)
- Celery task queue and scheduling
- Automatic purge of items older than 30 days
- Production deployment on Raspberry Pi 5
- Public access via noBGP proxy
- Server-side API proxy (no exposed backend URL)
- LLM-based relevance checking (evaluation mode with Ollama)
- BlueSky social media integration (automatic posting)

### Planned
- User authentication and preferences
- Search functionality
- Push notifications (ntfy.sh)

## License

MIT License - see LICENSE file for details

## Acknowledgments

- CapWages for comprehensive organization roster data
- All the excellent news sources covering the Sharks
- noBGP for simple public proxy hosting
