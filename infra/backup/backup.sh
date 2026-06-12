#!/bin/sh
# Nightly Postgres backup loop (brief 09, O2).
#
# Runs inside the `backup` compose service (postgres:16 image, so pg_dump and
# psql are available). Each night at BACKUP_AT_HOUR it writes a compressed dump
# to /backups (host-mounted ./backups) and prunes dumps older than
# BACKUP_RETENTION_DAYS.
#
# Connection settings come from the standard libpq env vars set in compose:
#   PGHOST, PGUSER, PGPASSWORD, PGDATABASE
#
# Trigger a one-off backup manually (bypasses the schedule):
#   docker compose exec backup sh /usr/local/bin/backup.sh once
set -eu

BACKUP_DIR=/backups
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_AT_HOUR="${BACKUP_AT_HOUR:-3}"

mkdir -p "$BACKUP_DIR"

log() {
    echo "$(date -u '+%Y-%m-%d %H:%M:%S%z') backup: $*"
}

run_backup() {
    ts="$(date -u '+%Y%m%d-%H%M%S')"
    out="$BACKUP_DIR/${PGDATABASE}-${ts}.sql.gz"
    tmp="${out}.partial"

    log "starting dump of '$PGDATABASE' -> $out"
    # --clean --if-exists makes the dump restorable onto an existing database.
    if pg_dump --clean --if-exists | gzip -c > "$tmp"; then
        mv "$tmp" "$out"
        log "dump complete ($(du -h "$out" | cut -f1))"
    else
        rm -f "$tmp"
        log "ERROR: pg_dump failed"
        return 1
    fi

    # Prune dumps older than the retention window.
    deleted="$(find "$BACKUP_DIR" -maxdepth 1 -name "${PGDATABASE}-*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete | wc -l | tr -d ' ')"
    log "pruned $deleted dump(s) older than ${RETENTION_DAYS} days"
}

# One-shot mode for manual/CI triggering.
if [ "${1:-}" = "once" ]; then
    run_backup
    exit $?
fi

log "backup service started (nightly at ${BACKUP_AT_HOUR}:00 UTC, ${RETENTION_DAYS}-day retention)"

while true; do
    now_hour="$(date -u '+%-H')"
    now_min="$(date -u '+%-M')"
    now_sec="$(date -u '+%-S')"

    # Seconds until the next BACKUP_AT_HOUR:00:00 UTC.
    secs_today=$(( now_hour * 3600 + now_min * 60 + now_sec ))
    target=$(( BACKUP_AT_HOUR * 3600 ))
    if [ "$secs_today" -lt "$target" ]; then
        sleep_for=$(( target - secs_today ))
    else
        sleep_for=$(( 86400 - secs_today + target ))
    fi

    log "sleeping ${sleep_for}s until next run"
    sleep "$sleep_for"

    run_backup || log "backup run failed; will retry at next scheduled time"
done
