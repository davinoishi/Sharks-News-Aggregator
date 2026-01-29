# Current Status - Sharks News Aggregator

**Last Updated:** 2026-01-29

## Production Deployment

The Sharks News Aggregator is now live and running on a Raspberry Pi 5 (pi5-ai2).

### Access URLs

| Service | Public URL | Local URL (on Pi) |
|---------|------------|-------------------|
| Web App | https://x2mq74oetjlz.nobgp.com | http://localhost:3001 |
| API | https://tz2k2lxwodrv.nobgp.com | http://localhost:8001 |

### Infrastructure

All 6 Docker services running on pi5-ai2:

- **PostgreSQL 16** - Database with 182 active clusters, 24 sources
- **Redis 7** - Cache and message broker
- **FastAPI API** (port 8001) - REST API serving requests
- **Celery Worker** - Task processor running
- **Celery Beat** - Scheduler triggering tasks every 10 minutes
- **Next.js Frontend** (port 3001) - Web UI with dynamic API URL detection

### Current Database State

```
Sources:           24 approved
Active Clusters:   182
Story Variants:    200+
Tags:              12
Entities:          77+ (synced daily from CapWages)
```

## Fully Functional Features

### RSS Ingestion (100% Complete)

- RSS Feed Fetching - Fetches from all 24 approved sources
- Feedparser Integration - Parses RSS entries successfully
- Idempotency - URL deduplication prevents duplicate ingestion
- Error Handling - Graceful handling of malformed RSS feeds
- Automatic Scheduling - Runs every 10 minutes via Celery Beat

### Roster Sync (100% Complete)

- Automated Daily Sync - Syncs full Sharks organization from CapWages
- 77+ Players Synced - Active roster + AHL/prospects + reserve list
- Departed Player Removal - Automatically removes players who leave
- Idempotent Updates - Safe to run multiple times

### Enrichment & Clustering (100% Complete)

- Entity Extraction - Identifies players, coaches, teams in text
- Token Normalization - NLTK-based text processing
- Event Classification - Detects trade, injury, lineup, etc.
- Clustering Algorithm - Matches variants using entity overlap + token similarity
- Tag Classification - Auto-tags with Trade, Rumors, Injury, etc.

### API Endpoints (100% Complete)

- `GET /health` - Health check with last scan time
- `GET /feed` - Returns clustered news feed with filtering
- `GET /cluster/{id}` - Returns cluster detail with all variants
- `POST /submit/link` - Accepts user submissions with rate limiting
- `GET /stats` - Site-wide statistics
- `POST /metrics/pageview` - Anonymous page view tracking
- `POST /cluster/{id}/click` - Track cluster link clicks

### Frontend (100% Complete)

- Responsive web UI with tag filtering
- Time range filters (24h, 7d, 30d)
- Cluster expansion to view all sources
- Trending indicator for popular stories
- Dynamic API URL detection (works locally and via noBGP)
- Privacy-respecting metrics display

### Production Deployment (100% Complete)

- Deployed on Raspberry Pi 5 (pi5-ai2)
- Public access via noBGP proxy (HTTPS)
- CORS configured for all access patterns
- Auto-restart on container failure
- Database persisted via Docker volumes

## RSS Sources (24 Total)

### Official Sources
- NHL.com - Sharks Official
- NHL.com - San Jose Sharks (via to-rss)

### Local Media
- San Jose Hockey Now
- The Mercury News - Sharks
- NBC Sports Bay Area - Sharks
- SF Gate - Sharks

### National Media
- CBS Sports - Sharks
- Yahoo Sports - Sharks

### Fan Blogs & Analysis
- Fear the Fin
- Blades of Teal
- Teal Town USA
- Puck Prose - Sharks
- The Hockey Writers - Sharks

### Rumors & Trade News
- Pro Hockey Rumors
- NHL Trade Rumors
- NHL Rumors - Sharks

### Twitter/Social (via rss.app)
- Elliotte Friedman
- Pierre LeBrun

### Other
- Google Alerts - Sharks News
- Sharks Audio Network (podcast)
- Sharks Podcast (Simplecast)

## How to Use

### View the Feed

Visit https://x2mq74oetjlz.nobgp.com to browse the news feed.

### API Access

```bash
# Health check
curl https://tz2k2lxwodrv.nobgp.com/health

# Get feed
curl https://tz2k2lxwodrv.nobgp.com/feed

# Get cluster detail
curl https://tz2k2lxwodrv.nobgp.com/cluster/239
```

### Admin Operations (on Pi)

```bash
# SSH to pi5-ai2, then:
cd /opt/Sharks-News-Aggregator

# View logs
docker compose -f docker-compose.pi.yml logs -f worker

# Restart services
docker compose -f docker-compose.pi.yml restart

# Trigger manual ingestion
docker compose -f docker-compose.pi.yml exec api python -c "
from app.tasks.ingest import ingest_all_sources
ingest_all_sources.delay()
"

# Check database
docker compose -f docker-compose.pi.yml exec db psql -U sharks -c "SELECT COUNT(*) FROM clusters WHERE status = 'active';"
```

## Known Limitations

### RSS Parsing Errors

Some RSS feeds occasionally have malformed XML and fail to parse. The system handles these gracefully and continues with other sources.

### Entity Extraction

Current implementation uses keyword matching. May miss entities referenced by nicknames or abbreviations.

## Future Enhancements

### Planned

- [ ] LLM-based relevance checking for better article filtering
- [ ] Search functionality across articles
- [ ] Push notifications via ntfy.sh
- [ ] Social media integration (BlueSky, X)
- [ ] User preferences and saved filters

### Under Consideration

- [ ] Mobile app
- [ ] Email digest
- [ ] Custom RSS feed output
- [ ] Admin dashboard for source management

## Documentation

- **[README.md](README.md)** - Quick start guide
- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** - Detailed setup walkthrough
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and data flow
- **[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)** - Deployment checklist
- **[ROSTER_SYNC.md](ROSTER_SYNC.md)** - Automated roster sync documentation
- **[FRONTEND_IMPLEMENTATION.md](FRONTEND_IMPLEMENTATION.md)** - Frontend features

## Summary

The Sharks News Aggregator is fully deployed and operational. The system automatically ingests news from 24 sources every 10 minutes, clusters similar stories, and presents them through a clean web interface accessible from anywhere via noBGP proxy.
