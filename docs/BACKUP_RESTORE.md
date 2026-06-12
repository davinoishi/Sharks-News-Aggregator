# Postgres backup & restore (brief 09, O2)

The production stack runs a dedicated `backup` service (see `docker-compose.yml`)
that takes a nightly `pg_dump` of the `sharks` database, compresses it, and keeps
the last 14 days. Dumps land in the host-mounted `./backups/` directory — on a
**different filesystem than the Postgres data volume** is strongly recommended so
a corrupt SD card / lost volume doesn't take the backups with it.

## What runs automatically

- **Schedule:** every night at `BACKUP_AT_HOUR` (UTC, default `03`).
- **Output:** `./backups/sharks-YYYYMMDD-HHMMSS.sql.gz`.
- **Retention:** dumps older than `BACKUP_RETENTION_DAYS` (default `14`) are pruned.
- **Format:** plain SQL via `pg_dump --clean --if-exists`, gzip-compressed. The
  `--clean --if-exists` flags mean the dump can be restored on top of an existing
  database (it drops objects before recreating them).

Tunable via environment (all optional):

| Variable | Default | Meaning |
|----------|---------|---------|
| `BACKUP_AT_HOUR` | `3` | Hour of day (UTC) to run the dump |
| `BACKUP_RETENTION_DAYS` | `14` | Days of dumps to keep |

## Trigger a backup on demand

```sh
# Runs one dump immediately, then exits (does not disturb the nightly loop).
docker compose exec backup sh /usr/local/bin/backup.sh once
ls -lh backups/
```

## Restore

> Restoring overwrites the target database. Take a fresh dump first if the
> current data matters.

### Restore into the live database

```sh
# Pick the dump you want.
DUMP=backups/sharks-20260611-030000.sql.gz

# Stop the app services so nothing writes mid-restore (leave db running).
docker compose stop api worker beat web

# Pipe the decompressed dump into psql inside the db container.
gunzip -c "$DUMP" | docker compose exec -T db \
  psql -U "${POSTGRES_USER:-sharks}" -d "${POSTGRES_DB:-sharks}"

docker compose start api worker beat web
```

### Verify into a scratch database (recommended after each schema change)

This proves a dump is restorable without touching production data:

```sh
DUMP=backups/sharks-20260611-030000.sql.gz

# Create a throwaway database alongside the real one.
docker compose exec -T db psql -U "${POSTGRES_USER:-sharks}" -d postgres \
  -c "DROP DATABASE IF EXISTS sharks_restore_test; CREATE DATABASE sharks_restore_test;"

# Restore the dump into it.
gunzip -c "$DUMP" | docker compose exec -T db \
  psql -U "${POSTGRES_USER:-sharks}" -d sharks_restore_test

# Sanity-check row counts against the live DB.
docker compose exec -T db psql -U "${POSTGRES_USER:-sharks}" -d sharks_restore_test \
  -c "SELECT count(*) FROM clusters;"
docker compose exec -T db psql -U "${POSTGRES_USER:-sharks}" -d sharks \
  -c "SELECT count(*) FROM clusters;"

# Clean up.
docker compose exec -T db psql -U "${POSTGRES_USER:-sharks}" -d postgres \
  -c "DROP DATABASE sharks_restore_test;"
```

The two `count(*)` values should match (modulo writes since the dump was taken).

## Off-device copies (manual)

The nightly dumps live on the Pi. To survive a total device loss, copy them to a
second machine. Credentials/targets are intentionally **not** baked into the
stack — wire up whichever of these fits your setup as a host cron job:

```sh
# rsync to another box over SSH (example):
rsync -avz --delete /path/to/Sharks-News-Aggregator/backups/ \
  user@backuphost:/srv/sharks-backups/

# or rclone to cloud storage (after `rclone config`):
rclone copy /path/to/Sharks-News-Aggregator/backups/ remote:sharks-backups
```

Add to the host crontab to run after the nightly dump (e.g. 04:00 UTC):

```cron
0 4 * * *  rsync -az --delete /path/to/Sharks-News-Aggregator/backups/ user@backuphost:/srv/sharks-backups/
```

## Notes

- `db_data_export.sql` in the repo root is a **stale one-off manual dump** kept
  for historical reference; it is not part of this backup scheme.
- The `backup` service shares the compose network and reaches Postgres at
  `db:5432` using the same `POSTGRES_*` credentials as the rest of the stack.
