# Brief 09 — Operations: prod compose, backups, logging, monitoring

Plan items: **O1, O2, O3, C4, C5** (see `docs/IMPROVEMENT_PLAN.md`).
Independent of other briefs; coordinate with brief 03 if both touch compose
files (rebase on whichever merges first).

## Task

Separate dev from prod Docker configuration, add automated Postgres backups,
replace print-logging with structured logging, and add basic health
monitoring/alerting for the ingestion pipeline.

## Context

- Deployment: Raspberry Pi 5, 6 services via compose, behind a nobgp tunnel.
  `docker-compose.yml` is currently used for both dev and prod: it bind-mounts
  `./api/app` into containers and runs worker/beat under `watchfiles`
  auto-reload (`docker-compose.yml` `worker`/`beat` commands). A
  `docker-compose.pi.yml` variant exists — reconcile with it rather than
  adding a third file blindly.
- Backups: none. `db_data_export.sql` in the repo root is a stale manual dump.
  The Pi's SD card is the only copy of the production data.
- Logging (**C4**): `api/app/tasks/*.py` use `print()` throughout; no levels,
  no timestamps. Celery captures stdout, so logs exist but are unstructured.
- **C5:** LLM relevance check fails open silently
  (`api/app/services/openrouter.py` → `check_relevance` returns
  `is_relevant=True` with `error` set; `api/app/tasks/enrich.py` logs nothing
  alert-worthy). An OpenRouter outage floods the feed with irrelevant items
  with no operator signal. Also `_parse_llm_approved()` in `main.py`
  string-matches stored JSON — parse it with `json.loads` and fall back to
  the legacy string match only for old rows.
- Health: `GET /health` returns `last_scan_at`; `/admin/sources` computes
  per-source health. Nothing watches either.

## Requirements

1. **O1 — dev/prod split:**
   - `docker-compose.yml` = production-shaped: no source bind mounts, no
     `watchfiles`, plain `celery worker`/`celery beat`, restart policies kept.
   - `docker-compose.dev.yml` = overlay adding bind mounts + reloaders
     (`docker compose -f docker-compose.yml -f docker-compose.dev.yml up`).
   - Fold `docker-compose.pi.yml` into this scheme (ideally it becomes
     unnecessary or a tiny overlay). Update `README.md`, `SETUP_GUIDE.md`,
     `PRODUCTION_CHECKLIST.md`.
2. **O2 — backups:**
   - Nightly `pg_dump` via a dedicated compose service (cron loop or
     `ofelia`-style scheduler) writing compressed dumps to a host-mounted
     directory **outside** the SD-card Docker volume if possible (document
     the mount point; default `./backups/`), with 14-day retention.
   - A documented restore procedure in `docs/BACKUP_RESTORE.md`, tested
     against a scratch database.
   - Off-device copying (rsync/rclone target) documented as a manual step —
     don't assume credentials.
3. **C4 — logging:** replace `print()` with `logging` (module-level loggers,
   `%`-style lazy formatting) across `api/app/tasks/` and `api/app/services/`.
   Consistent format with timestamps + task context; respect a `LOG_LEVEL`
   env var (default INFO). Keep messages' information content (source names,
   counts, item ids).
4. **C5 — LLM failure visibility:**
   - When relevance fails open, log at WARNING with the error, and increment
     a counter (a `site_metrics` row, e.g. `llm_failopen_count`, is fine).
   - Expose it in `/admin/validations/stats` (a `fail_open` count).
   - Fix `_parse_llm_approved` to JSON-parse first.
5. **O3 — monitoring:**
   - New task in `app/tasks/maintenance.py` running every ~30 min: flag if
     `last_scan_at` is older than 3× the ingest interval, or any approved
     source has `fetch_error_count >= 3`. On flag: log at ERROR and (if
     `ALERT_WEBHOOK_URL` is configured) POST a short JSON alert to it
     (works with ntfy/Discord/Slack-style webhooks). De-duplicate alerts
     (don't re-fire more than once per ~6h per condition; persist state in
     `site_metrics` or Redis).
   - Extend `/health` to include a `degraded: bool` reflecting those checks
     so an external uptime pinger (document UptimeRobot/healthchecks.io
     setup in the docs) can alert on it.

## Out of scope

- Port exposure / Redis password (brief 03) — rebase if it's merged.
- Metrics stacks (Prometheus/Grafana), log shipping.
- Refactoring task logic beyond the logging swap (brief 07).

## Verification

- `docker compose up` (prod shape): all services healthy, no watchfiles in
  `ps` output inside worker/beat containers, pipeline ingests on schedule.
- Dev overlay: code edit hot-reloads the API.
- Backup service: trigger a run manually, confirm a dump file appears;
  restore it into a scratch container and `SELECT count(*) FROM clusters`
  matches.
- Set `LOG_LEVEL=DEBUG` → debug lines appear; INFO default is reasonably
  quiet. `grep -rn "print(" api/app/tasks api/app/services` → no hits
  (scripts/ may keep prints).
- Stop outbound network for the worker (or set a bogus OpenRouter key) →
  WARNING logs + fail-open counter increments; stats endpoint shows it.
- Set ingest interval low, stop beat → monitoring task fires the ERROR/
  webhook once, not repeatedly; `/health` shows `degraded: true`.

## Deliverable

Branch `improve/09-ops`, PR against `main` with verification transcript and
updated docs. Update the status table in `docs/IMPROVEMENT_PLAN.md`.
