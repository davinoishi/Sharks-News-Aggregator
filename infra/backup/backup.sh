#!/bin/sh
# Nightly Postgres backup loop with integrity verification (brief 09 O2; R2-O3).
#
# Runs inside the `backup` compose service (postgres:16 image, so pg_dump, psql,
# createdb and dropdb are available). Each night at BACKUP_AT_HOUR it writes a
# compressed dump to /backups (host-mounted ./backups), prunes dumps older than
# BACKUP_RETENTION_DAYS, and verifies integrity:
#
#   - every run: `gzip -t` the new dump so a corrupt/truncated archive is caught
#     and discarded immediately rather than at disaster time;
#   - weekly (BACKUP_VERIFY_WEEKDAY): a full test-restore of the latest dump into
#     a throwaway database, with a sanity query, to prove the dump is actually
#     restorable end-to-end.
#
# On any failure it logs an ERROR (picked up by log forwarding, O1) and, if
# ALERT_WEBHOOK_URL is set, best-effort POSTs a short JSON alert.
#
# Connection settings come from the standard libpq env vars set in compose:
#   PGHOST, PGUSER, PGPASSWORD, PGDATABASE
#
# Manual triggers (bypass the schedule):
#   docker compose exec backup sh /usr/local/bin/backup.sh once     # one dump now
#   docker compose exec backup sh /usr/local/bin/backup.sh verify   # test-restore latest
set -eu

BACKUP_DIR=/backups
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_AT_HOUR="${BACKUP_AT_HOUR:-3}"
# Day of week (0=Sunday .. 6=Saturday, UTC) for the weekly test-restore.
BACKUP_VERIFY_WEEKDAY="${BACKUP_VERIFY_WEEKDAY:-0}"
# Throwaway database name for the test-restore. Must not collide with anything real.
VERIFY_DB="${BACKUP_VERIFY_DB:-sharks_backup_verify}"

mkdir -p "$BACKUP_DIR"

log() {
    echo "$(date -u '+%Y-%m-%d %H:%M:%S%z') backup: $*"
}

# Best-effort alert. Logs ERROR always; additionally POSTs to ALERT_WEBHOOK_URL
# when set and an HTTP client is available (the postgres image may ship neither
# curl nor wget — never fatal). Payload mirrors the app's _send_webhook_alert
# (text + content keys) so it works with ntfy/Discord/Slack receivers.
alert() {
    msg="$1"
    log "ERROR: $msg"
    [ -n "${ALERT_WEBHOOK_URL:-}" ] || return 0
    body="{\"text\":\"[backup] $msg\",\"content\":\"[backup] $msg\"}"
    if command -v curl >/dev/null 2>&1; then
        curl -fsS -m 10 -X POST -H 'Content-Type: application/json' \
            -d "$body" "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 \
            || log "WARN: alert webhook POST failed (curl)"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -T 10 -O /dev/null --header='Content-Type: application/json' \
            --post-data="$body" "$ALERT_WEBHOOK_URL" \
            || log "WARN: alert webhook POST failed (wget)"
    else
        log "WARN: no curl/wget in image; alert not delivered to webhook"
    fi
}

# Path of the most recent dump, or empty if none exist.
latest_dump() {
    ls -1t "$BACKUP_DIR/${PGDATABASE}-"*.sql.gz 2>/dev/null | head -n1
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
        alert "pg_dump failed for '$PGDATABASE'"
        return 1
    fi

    # Integrity gate: a dump that fails gzip's CRC check is worse than useless
    # (it reads as a backup but can't be restored). Discard it and fail loudly.
    if gzip -t "$out" 2>/dev/null; then
        log "integrity check passed (gzip -t)"
    else
        rm -f "$out"
        alert "integrity check FAILED for $out; corrupt dump discarded"
        return 1
    fi

    # Prune dumps older than the retention window.
    deleted="$(find "$BACKUP_DIR" -maxdepth 1 -name "${PGDATABASE}-*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete | wc -l | tr -d ' ')"
    log "pruned $deleted dump(s) older than ${RETENTION_DAYS} days"
}

# Full test-restore of the latest dump into a throwaway database. Proves the
# dump is restorable end-to-end (gzip -t only checks the archive, not the SQL).
verify_restore() {
    dump="$(latest_dump)"
    if [ -z "$dump" ]; then
        alert "test-restore skipped: no dump found in $BACKUP_DIR"
        return 1
    fi

    log "test-restore: restoring $dump into '$VERIFY_DB'"
    # Clean up any leftover verify DB from a previous crashed run.
    dropdb --if-exists "$VERIFY_DB" >/dev/null 2>&1 || true

    if ! createdb "$VERIFY_DB" >/dev/null 2>&1; then
        alert "test-restore: could not create '$VERIFY_DB'"
        return 1
    fi

    rc=0
    # ON_ERROR_STOP makes psql exit non-zero on the first SQL error.
    if gunzip -c "$dump" | psql --quiet -v ON_ERROR_STOP=1 -d "$VERIFY_DB" >/dev/null 2>&1; then
        # Sanity query: a healthy restore has a populated sources table.
        count="$(psql -tA -d "$VERIFY_DB" -c 'SELECT count(*) FROM sources' 2>/dev/null || echo "")"
        if [ -n "$count" ] && [ "$count" -ge 1 ] 2>/dev/null; then
            log "test-restore OK ($count sources restored from $(basename "$dump"))"
        else
            alert "test-restore: restored but sanity query failed (sources count='$count') for $dump"
            rc=1
        fi
    else
        alert "test-restore: psql restore failed for $dump"
        rc=1
    fi

    dropdb --if-exists "$VERIFY_DB" >/dev/null 2>&1 || true
    return $rc
}

# One-shot modes for manual/CI triggering.
case "${1:-}" in
    once)
        run_backup
        exit $?
        ;;
    verify)
        verify_restore
        exit $?
        ;;
esac

log "backup service started (nightly at ${BACKUP_AT_HOUR}:00 UTC, ${RETENTION_DAYS}-day retention, weekly test-restore on weekday ${BACKUP_VERIFY_WEEKDAY})"

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

    if run_backup; then
        # Weekly deep verification, only after a good dump.
        if [ "$(date -u '+%w')" = "$BACKUP_VERIFY_WEEKDAY" ]; then
            verify_restore || log "weekly test-restore failed; see alert above"
        fi
    else
        log "backup run failed; will retry at next scheduled time"
    fi
done
