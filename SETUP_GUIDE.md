# Setup Guide - Sharks News Aggregator

Complete guide to get the application running from scratch.

## Prerequisites

- Docker & Docker Compose
- Git

## Deployment Options

| Environment | Config File | Web Port | API Port | Use Case |
|-------------|-------------|----------|----------|----------|
| Development | `docker-compose.yml` | 3000 | 8000 | Local development |
| Production (Pi) | `docker-compose.pi.yml` | 3001 | 8001 | Raspberry Pi 5 deployment |

## Production Deployment (Raspberry Pi 5)

The recommended deployment is on a Raspberry Pi 5 with public access via noBGP proxy.

**Live URLs:**
- Web: https://x2mq74oetjlz.nobgp.com
- API: https://tz2k2lxwodrv.nobgp.com

### Pi Deployment Steps

```bash
# SSH to Pi and clone repo
git clone https://github.com/davinoishi/Sharks-News-Aggregator.git /opt/Sharks-News-Aggregator
cd /opt/Sharks-News-Aggregator

# Start services (Pi-specific config with ports 3001/8001)
docker compose -f docker-compose.pi.yml up -d
```

This starts 6 containers:
- PostgreSQL database (port 5432)
- Redis (port 6379)
- FastAPI API (exposed on port 8001)
- Celery worker
- Celery beat scheduler
- Next.js frontend (exposed on port 3001)

Wait ~60 seconds for all services to initialize on Pi.

## Local Development Setup

### 1. Start the Services

```bash
# From the project root directory
docker-compose up -d
```

This will start:
- PostgreSQL database (port 5432)
- Redis (port 6379)
- FastAPI API (port 8000)
- Celery worker
- Celery beat scheduler
- Next.js frontend (port 3000)

Wait ~30 seconds for all services to initialize.

### 2. Verify Services are Running

```bash
docker-compose ps
```

All services should show as "Up". Check logs if any failed:

```bash
docker-compose logs api
```

### 3. Import Initial Sources from CSV

The `initial_sources.csv` file contains pre-configured news sources (24 sources in production).

**Dry run first (preview what will be imported):**

```bash
docker-compose exec api python -m app.scripts.import_sources /app/../initial_sources.csv --dry-run
```

**Actually import the sources:**

```bash
docker-compose exec api python -m app.scripts.import_sources /app/../initial_sources.csv
```

You should see output like:

```
Reading sources from initial_sources.csv...

Row 2: ✓ Imported 'NHL.com - San Jose Sharks' (ID: 1)
Row 3: ✓ Imported 'San Jose Sharks PR' (ID: 2)
...

✓ Successfully imported 15 sources
```

### 4. Seed Initial Entities (Sharks Roster)

This populates the database with known players, coaches, and teams for entity extraction.

**Option A: Manual seeding (one-time)**

```bash
docker-compose exec api python -m app.scripts.seed_entities
```

**Option B: Trigger roster sync from CapWages (recommended)**

The system includes automated daily roster sync from CapWages that keeps the full organization (NHL + AHL + reserves) up to date.

```bash
# Trigger manual roster sync
docker-compose exec api python -c "
from app.tasks.sync_roster import sync_sharks_roster
sync_sharks_roster.delay()
"
```

This syncs 77+ players from the full Sharks organization including:
- NHL active roster
- AHL (Barracuda) players
- Unsigned draft picks and reserves

### 5. Verify Database Setup

Check that data was imported correctly:

```bash
# Check sources
docker-compose exec api python -m app.scripts.db_manage sources

# Check entities
docker-compose exec api python -m app.scripts.db_manage entities

# Check overall status
docker-compose exec api python -m app.scripts.db_manage status
```

Or directly query the database:

```bash
# Connect to PostgreSQL
docker-compose exec db psql -U sharks -d sharks

# Inside psql:
\dt                    # List tables
SELECT * FROM sources; # View sources
SELECT * FROM entities LIMIT 10; # View entities
SELECT * FROM tags;    # View tags (pre-populated)
\q                     # Quit
```

### 6. Test the API

The API should now be running at http://localhost:8000

```bash
# Health check
curl http://localhost:8000/health

# API documentation (Swagger UI)
open http://localhost:8000/docs

# Get feed (will be empty initially)
curl http://localhost:8000/feed
```

### 7. Test the Frontend

Open http://localhost:3000 in your browser. You should see the placeholder page.

## Database Management Commands

The `db_manage.py` script provides useful commands:

```bash
# Show database status and counts
docker-compose exec api python -m app.scripts.db_manage status

# List all sources
docker-compose exec api python -m app.scripts.db_manage sources

# List recent clusters (limit 20)
docker-compose exec api python -m app.scripts.db_manage clusters

# List clusters with custom limit
docker-compose exec api python -m app.scripts.db_manage clusters 50

# Show tag distribution
docker-compose exec api python -m app.scripts.db_manage tags

# List all entities
docker-compose exec api python -m app.scripts.db_manage entities

# List only players
docker-compose exec api python -m app.scripts.db_manage entities player

# Reset database (WARNING: deletes all data)
docker-compose exec api python -m app.scripts.db_manage reset
```

## Development Workflow

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f beat
```

### Restarting Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart api
docker-compose restart worker
```

### Rebuilding After Code Changes

```bash
# Rebuild and restart
docker-compose up -d --build

# Or rebuild specific service
docker-compose up -d --build api
```

### Accessing Python Shell

```bash
# Python shell with app context
docker-compose exec api python

# Then in Python:
from app.core.database import SessionLocal
from app.models import Source, Cluster
db = SessionLocal()
sources = db.query(Source).all()
print(f"Total sources: {len(sources)}")
```

## Triggering Ingestion Manually

The Celery beat scheduler will automatically run ingestion every 10 minutes (configured in `.env`).

To manually trigger ingestion:

```bash
# Enter the worker container
docker-compose exec worker python

# Then in Python:
from app.tasks.ingest import ingest_all_sources
result = ingest_all_sources.delay()
print(f"Task ID: {result.id}")
```

Or update the beat schedule to run more frequently by changing `INGEST_INTERVAL_MINUTES` in `.env`.

## Monitoring Celery Tasks

```bash
# View Celery worker logs
docker-compose logs -f worker

# View Celery beat (scheduler) logs
docker-compose logs -f beat
```

## Troubleshooting

### Database Connection Issues

```bash
# Check if database is running
docker-compose ps db

# Check database logs
docker-compose logs db

# Manually test connection
docker-compose exec api python -c "from app.core.database import SessionLocal; db = SessionLocal(); print('✓ Connected')"
```

### Redis Connection Issues

```bash
# Check if Redis is running
docker-compose ps redis

# Test Redis
docker-compose exec redis redis-cli ping
# Should return: PONG
```

### Port Conflicts

If you see errors about ports already in use:

```bash
# Check what's using a port (e.g., 5432)
lsof -i :5432

# Change ports in docker-compose.yml if needed
# Example: Change postgres port from 5432:5432 to 5433:5432
```

### Reset Everything and Start Fresh

```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Rebuild and start
docker-compose up -d --build

# Re-import data
docker-compose exec api python -m app.scripts.import_sources /app/../initial_sources.csv
docker-compose exec api python -m app.scripts.seed_entities
```

## Next Steps

Now that the infrastructure is set up:

1. **Wait for first ingestion** - Check worker logs after 10 minutes to see RSS feeds being fetched
2. **Monitor cluster creation** - As articles are ingested, they'll be clustered automatically
3. **Check the feed** - Visit http://localhost:8000/feed to see clustered news
4. **Test submissions** - Try POST http://localhost:8000/submit/link with a Sharks news URL
5. **Build the frontend** - Create React components to display the feed

## Useful Tips

- **Environment variables** are in `.env.example` - copy to `.env` to customize
- **Database migrations** will be handled by Alembic (coming soon)
- **Add new sources** - Edit `initial_sources.csv` and re-run import script
- **Update roster** - Edit `api/app/scripts/seed_entities.py` and re-run
- **Adjust clustering** - Modify thresholds in `.env`:
  - `CLUSTER_SIMILARITY_THRESHOLD=0.62`
  - `ENTITY_OVERLAP_THRESHOLD=0.50`
  - `TOKEN_SIMILARITY_THRESHOLD=0.40`

## Production Considerations

The application is currently deployed on Raspberry Pi 5 (pi5-ai2) with:

**Completed:**
- ✅ Public HTTPS access via noBGP proxy
- ✅ CORS configured for all access patterns (`ALLOWED_ORIGINS=*`)
- ✅ Rate limiting on submission endpoint (10/hour per IP)
- ✅ Auto-restart on container failure
- ✅ Database persisted via Docker volumes
- ✅ Dynamic API URL detection (works locally and via noBGP)

**Recommended for enhanced security:**
1. Change default database passwords in `.env`
2. Set up proper authentication for admin endpoints
3. Set up automated database backups
4. Configure monitoring/alerting (uptime checks on `/health`)
5. Review and harden CSP headers

## Pi-Specific Operations

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
