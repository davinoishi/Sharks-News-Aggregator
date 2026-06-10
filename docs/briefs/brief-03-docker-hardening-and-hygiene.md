# Brief 03 — Docker network hardening and security hygiene

Plan items: **S4, S5** (see `docs/IMPROVEMENT_PLAN.md`).

## Task

Stop exposing Postgres/Redis to the host network, add a Redis password, add
security headers to the web app, and clean up small security hygiene issues.

## Context

- `docker-compose.yml` publishes `5432:5432` (Postgres) and `6379:6379`
  (password-less Redis) to the host. The app runs on a Raspberry Pi on a home
  LAN, so anyone on the LAN can reach both. `docker-compose.pi.yml` is the
  Pi-specific variant — apply equivalent changes there.
- Services only need to reach each other over the compose network
  (`db:5432`, `redis:6379`); host publishing exists for developer convenience.
- `web/next.config.js` sets no security headers.
- `api/app/main.py`: 403 messages embed the client IP; submission rows store the
  raw submitter IP (`submitter_ip`). Note: brief 01 may have already reworked
  admin auth — if so, only handle whatever hygiene items remain.

## Requirements

1. **Compose changes** (both `docker-compose.yml` and `docker-compose.pi.yml`):
   - Remove the `ports:` mappings for `db` and `redis`, or bind them to
     `127.0.0.1:` only. Keep a commented-out `127.0.0.1` mapping with a note for
     local debugging.
   - Set a Redis password (`redis-server --requirepass ${REDIS_PASSWORD:?}`),
     thread it through `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`
     (`redis://:pass@redis:6379/1`), and update `.env.example`.
   - Update the redis healthcheck to authenticate.
2. **Security headers** in `web/next.config.js` via `headers()`:
   `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
   `Referrer-Policy: strict-origin-when-cross-origin`, a conservative
   `Permissions-Policy`, and a CSP. Start the CSP report-only if needed, but the
   PR must ship an enforced CSP that the app actually works under (Next.js
   inline runtime needs `'unsafe-inline'` for styles at minimum — verify against
   the real app, don't guess).
3. **Hygiene** in the API:
   - Error bodies never echo client IPs (skip if brief 01 already did this).
   - Hash submitter IPs before storage (e.g. SHA-256 with a server-side salt
     env var) so rate-limit comparisons still work but raw IPs aren't kept.
     Include a tiny migration for the column if needed, and update the
     privacy wording in `web/app/legal/page.tsx` only if it mentions IPs.
4. Update `PRODUCTION_CHECKLIST.md` and `.env.example` for `REDIS_PASSWORD`
   and any other new vars.

## Out of scope

- Admin auth and rate limiting (brief 01).
- SSRF validation (brief 02).
- Splitting dev/prod compose files (brief 09) — keep the current file structure.

## Verification

- `docker compose up` succeeds; all 6 services healthy.
- From the host: `nc -zv localhost 5432` and `nc -zv localhost 6379` fail (or
  only succeed on 127.0.0.1 if you chose loopback binding).
- `redis-cli -h localhost ping` without password fails; worker and beat still
  process tasks (check `docker compose logs worker` for a successful task run).
- `curl -sI http://localhost:3001 | grep -i -E 'x-frame|x-content|referrer|content-security'`
  shows the headers; click through the site (feed loads, expand a cluster,
  filters work) with the CSP enforced and no console violations.
- Feed still renders end-to-end.

## Deliverable

Branch `improve/03-docker-hardening`, PR against `main` with verification
transcript. Update the status table in `docs/IMPROVEMENT_PLAN.md`.
