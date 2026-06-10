# Production Deployment Checklist

A checklist of tasks for deploying the Sharks News Aggregator to production.

**Current Status:** ✅ Deployed and running on Raspberry Pi 5 (pi5-ai2)

**Live URLs:**
- Web: https://x2mq74oetjlz.nobgp.com
- BlueSky: https://bsky.app/profile/sjsharks-news.bsky.social

---

## Security

- [x] **Update CORS origins** — Set `ALLOWED_ORIGINS=*` for public API access
- [x] **Rate limiting** — proxy-aware per-client limits: `/submit/link`
  (`SUBMISSION_RATE_LIMIT_PER_IP`/hr) plus `/metrics/pageview` and
  `/cluster/{id}/click` (`METRICS_RATE_LIMIT_PER_MIN`). Backend keys on the real
  client IP via `X-Forwarded-For` from trusted proxies (`TRUSTED_PROXY_IPS`).
- [x] **Disable API documentation** — Set `docs_url=None, redoc_url=None` in FastAPI app (optional)
- [x] **Protect admin endpoints** — Every `/admin/*` route requires the
  `require_admin` dependency (`X-Admin-API-Key` via constant-time compare,
  **fail closed** when unset). The Next.js proxy injects the key server-side and
  gates the admin page/proxy with HTTP Basic
  (`ADMIN_PANEL_USER`/`ADMIN_PANEL_PASSWORD`). The old IP allowlist was removed.
- [x] **Security headers** — `next.config.js` sets `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and an enforced CSP.
- [x] **Network isolation** — Postgres/Redis are no longer published to the host;
  they're reachable only on the compose network. Redis requires a password
  (`REDIS_PASSWORD`, threaded into the Celery broker/result URLs).
- [x] **Hash submitter IPs** — `/submit/link` stores a salted SHA-256 hash
  (`IP_HASH_SALT`), never the raw IP. Run `api/migrations/hash_submitter_ip.sql`.

> **Required env (set before deploy):** `ADMIN_API_KEY`, `ADMIN_PANEL_PASSWORD`,
> and `REDIS_PASSWORD` (URL-safe) — the compose files refuse to start if any are
> empty (`${VAR:?...}`). Also set `IP_HASH_SALT`; optionally `ADMIN_PANEL_USER`,
> `TRUSTED_PROXY_IPS`, `METRICS_RATE_LIMIT_PER_MIN`.

## Environment Configuration

- [x] **Production docker-compose** — Using `docker-compose.pi.yml` with ports 3001/8001
- [x] **CORS configuration** — `ALLOWED_ORIGINS=*`
- [x] **Dynamic API URL detection** — Frontend auto-detects local vs. noBGP access
- [x] **Change default database password** — Credentials now loaded from `.env` file (not in git)
- [ ] **Set appropriate log levels** — Reduce verbosity if needed

## Infrastructure

- [x] **noBGP proxy configured** — Both web and API services accessible via HTTPS
  - Web: https://x2mq74oetjlz.nobgp.com
  - `auth_required=false` for public access
- [x] **Docker containers running** — All 6 services operational
- [x] **Datastore ports not exposed** — `db`/`redis` host port mappings removed
  (commented loopback-only mappings remain for local debugging)
- [x] **Auto-restart enabled** — `restart: unless-stopped` on all containers
- [x] **Database persistence** — PostgreSQL data persisted via Docker volumes
- [ ] **Database backups** — Set up automated PostgreSQL backups
- [x] **Monitoring** — Set up health check monitoring (uptime monitor on `/health`)
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

## Social Media Integration

- [x] **BlueSky integration** — Automatic posting to [@sjsharks-news.bsky.social](https://bsky.app/profile/sjsharks-news.bsky.social)
- [x] **BlueSky scheduling** — Posts new clusters every 15 minutes
- [x] **BlueSky rate limiting** — 5-minute cooldown between posts
- [x] **BlueSky retry mechanism** — Failed posts retried hourly (up to 3 times)
- [x] **BlueSky credentials** — App password stored in `.env` file (not in git)

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

# Trigger manual BlueSky posting
docker compose -f docker-compose.pi.yml exec api python -c "
from app.tasks.bluesky import post_new_clusters
post_new_clusters.delay()
"

# Check cluster count
docker compose -f docker-compose.pi.yml exec db psql -U sharks -c "SELECT COUNT(*) FROM clusters WHERE status = 'active';"

# Check source count
docker compose -f docker-compose.pi.yml exec db psql -U sharks -c "SELECT COUNT(*) FROM sources WHERE status = 'approved';"
```

---

## Completed Enhancements

- [x] **LLM-based relevance filtering, tagging, and clustering** — Google Gemma 4 via OpenRouter (replaced local Ollama/Hailo)
- [x] **Social media posting** — BlueSky integration complete

## Future Enhancements (Post-Launch)

These are not blockers for production but noted for future work:

- [ ] **Search functionality** — Full-text search across articles
- [ ] **Push notifications** — ntfy.sh integration
- [ ] **User authentication** — If adding personalization features
- [ ] **Custom domain** — Configure custom domain via noBGP
