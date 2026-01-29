# Production Deployment Checklist

A checklist of tasks for deploying the Sharks News Aggregator to production.

**Current Status:** ✅ Deployed and running on Raspberry Pi 5 (pi5-ai2)

**Live URLs:**
- Web: https://x2mq74oetjlz.nobgp.com
- API: https://tz2k2lxwodrv.nobgp.com

---

## Security

- [x] **Update CORS origins** — Set `ALLOWED_ORIGINS=*` for public API access
- [x] **Rate limiting** — 10 submissions per IP per hour on `/submit/link`
- [ ] **Disable API documentation** — Set `docs_url=None, redoc_url=None` in FastAPI app (optional)
- [ ] **Protect admin endpoints** — Currently return 501 (not implemented)
- [ ] **Review CSP headers** — Add Content-Security-Policy if needed

## Environment Configuration

- [x] **Production docker-compose** — Using `docker-compose.pi.yml` with ports 3001/8001
- [x] **CORS configuration** — `ALLOWED_ORIGINS=*`
- [x] **Dynamic API URL detection** — Frontend auto-detects local vs. noBGP access
- [ ] **Change default database password** — Currently using default `sharks` password
- [ ] **Set appropriate log levels** — Reduce verbosity if needed

## Infrastructure

- [x] **noBGP proxy configured** — Both web and API services accessible via HTTPS
  - Web: https://x2mq74oetjlz.nobgp.com
  - API: https://tz2k2lxwodrv.nobgp.com
  - `auth_required=false` for public access
- [x] **Docker containers running** — All 6 services operational
- [x] **Auto-restart enabled** — `restart: unless-stopped` on all containers
- [x] **Database persistence** — PostgreSQL data persisted via Docker volumes
- [ ] **Database backups** — Set up automated PostgreSQL backups
- [ ] **Monitoring** — Set up health check monitoring (uptime monitor on `/health`)
- [ ] **Log aggregation** — Consider centralizing logs

## Performance

- [x] **Database indexes** — Indexes exist for common query patterns
- [x] **Connection pooling** — SQLAlchemy default pool settings
- [ ] **Redis persistence** — Currently ephemeral (acceptable for task queue)

## Data & Content

- [x] **RSS sources configured** — 24 approved sources active
- [x] **Entity database populated** — 77+ players synced from CapWages
- [x] **Automated roster sync** — Daily sync keeps organization current
- [x] **RSS ingestion working** — Every 10 minutes via Celery Beat
- [x] **Old item purge** — Daily cleanup of items older than 30 days

## Testing

- [x] **Feed browsing** — Working at both localhost and noBGP URLs
- [x] **Tag filtering** — Working correctly
- [x] **Cluster expansion** — Shows all source variants
- [x] **Mobile responsive** — UI works on mobile devices
- [x] **API endpoints** — All endpoints functional

---

## Current Database State

```
Sources:           24 approved
Active Clusters:   182+
Story Variants:    200+
Tags:              12
Entities:          77+ (synced daily from CapWages)
```

## Admin Operations (on Pi)

```bash
# SSH to pi5-ai2, then:
cd /opt/Sharks-News-Aggregator

# View logs
docker compose -f docker-compose.pi.yml logs -f worker

# Restart all services
docker compose -f docker-compose.pi.yml restart

# Trigger manual RSS ingestion
docker compose -f docker-compose.pi.yml exec api python -c "
from app.tasks.ingest import ingest_all_sources
ingest_all_sources.delay()
"

# Trigger manual roster sync
docker compose -f docker-compose.pi.yml exec api python -c "
from app.tasks.sync_roster import sync_sharks_roster
sync_sharks_roster.delay()
"

# Check cluster count
docker compose -f docker-compose.pi.yml exec db psql -U sharks -c "SELECT COUNT(*) FROM clusters WHERE status = 'active';"

# Check source count
docker compose -f docker-compose.pi.yml exec db psql -U sharks -c "SELECT COUNT(*) FROM sources WHERE status = 'approved';"
```

---

## Future Enhancements (Post-Launch)

These are not blockers for production but noted for future work:

- [ ] **LLM-based relevance filtering** — Improved article filtering
- [ ] **Search functionality** — Full-text search across articles
- [ ] **Push notifications** — ntfy.sh integration
- [ ] **Social media posting** — BlueSky, X, Threads integration
- [ ] **User authentication** — If adding personalization features
- [ ] **Custom domain** — Configure custom domain via noBGP
