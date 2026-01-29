# Production Deployment Checklist

A checklist of tasks to complete before deploying the Sharks News Aggregator to production.

## Security

- [ ] **Disable API documentation** — Set `docs_url=None, redoc_url=None` in FastAPI app
- [ ] **Disable or protect public APIs** — Review which endpoints should be accessible
  - `/health` — Keep (needed for monitoring)
  - `/feed` — Keep (main functionality)
  - `/cluster/{id}` — Keep (main functionality)
  - `/submit/link` — Disable or add CAPTCHA
  - `/admin/*` — Keep disabled (already returns 501)
- [ ] **Update CORS origins** — Set `ALLOWED_ORIGINS` to production domain
- [ ] **Add rate limiting** — Consider adding limits to `/feed` and `/cluster/{id}` endpoints
- [ ] **Review CSP headers** — Add Content-Security-Policy via noBGP proxy or Next.js middleware

## Environment Configuration

- [ ] **Create production .env file** with:
  - [ ] Strong database password (not `sharks`)
  - [ ] Production `ALLOWED_ORIGINS`
  - [ ] Production `NEXT_PUBLIC_API_BASE_URL`
- [ ] **Remove debug settings** — Ensure no debug flags are enabled
- [ ] **Set appropriate log levels** — Reduce verbosity for production

## Infrastructure

- [ ] **Set up noBGP proxy** for both web and API services
  - [ ] Configure HTTPS
  - [ ] Set `auth_required` if needed
  - [ ] Configure custom domain (optional)
- [ ] **Database backups** — Set up automated PostgreSQL backups
- [ ] **Monitoring** — Set up health check monitoring (e.g., uptime monitor hitting `/health`)
- [ ] **Log aggregation** — Consider centralizing logs from all containers

## Performance

- [ ] **Database indexes** — Verify indexes exist for common query patterns
- [ ] **Connection pooling** — Review SQLAlchemy pool settings for production load
- [ ] **Redis persistence** — Decide if Redis data should persist across restarts

## Data & Content

- [ ] **Review RSS sources** — Confirm all sources in `initial_sources.csv` are appropriate
- [ ] **Seed production database** — Run entity seeding scripts
- [ ] **Test ingestion pipeline** — Verify RSS ingestion works with production sources

## DNS & Domain (if using custom domain)

- [ ] **Register domain** or configure subdomain
- [ ] **Set up DNS records** pointing to noBGP proxy
- [ ] **Update all URL references** in code and config

## Pre-Launch Testing

- [ ] **Test all user flows** — Feed browsing, filtering, cluster expansion
- [ ] **Test on mobile** — Verify responsive design works
- [ ] **Load test** — Verify system handles expected traffic
- [ ] **Review feed quality** — Check for false positives/negatives in article filtering

## Post-Launch

- [ ] **Monitor error rates** — Watch for unexpected errors in logs
- [ ] **Monitor feed quality** — Periodically check for irrelevant articles
- [ ] **Set up alerts** — Notify on service downtime or high error rates

---

## Future Enhancements (Post-Launch)

These are not blockers for production but noted for future work:

- [ ] **Social media posting** — BlueSky, X, Threads integration
- [ ] **Push notifications** — ntfy.sh integration
- [ ] **LLM-based filtering** — For improved article relevance detection
- [ ] **User authentication** — If adding personalization features
- [ ] **Search functionality** — Full-text search across articles
