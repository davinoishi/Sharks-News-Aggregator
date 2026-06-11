# Database migrations (Alembic)

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/)
(brief 07, C6). This replaces the previous mix of:

- `infra/postgres/init/*.sql` — fresh-install bootstrap SQL
- `api/migrations/*.sql` — hand-applied one-off SQL (now in `api/migrations/legacy/`)
- `api/app/scripts/migrate_*.py` — ad-hoc back-fill scripts (now in `api/migrations/legacy/`)

Alembic lives in `api/alembic/`. The database URL is read from the application
settings (`DATABASE_URL`) in `api/alembic/env.py`, so there is a single source
of truth — you do **not** set it in `alembic.ini`.

## Revisions

| Revision | Description |
|----------|-------------|
| `0001_baseline` | Full current schema, built from the SQLAlchemy models (`Base.metadata.create_all`). |
| `0002_timezone_aware` | Converts any naive `timestamp without time zone` columns to `timestamptz` (C2). Idempotent — a no-op on databases that are already timezone-aware. |

## Running migrations

All commands run from the `api/` directory (or inside the API container, where
the working directory is `/app`). The API container also runs
`alembic upgrade head` automatically on startup (see `api/Dockerfile`).

```bash
# Show history / current head
alembic history
alembic heads

# Apply all pending migrations
alembic upgrade head

# Preview the SQL without touching a database (offline mode)
alembic upgrade head --sql
```

### Fresh install

On a brand-new database, `alembic upgrade head` builds the schema (baseline)
and applies later revisions.

> **Note on the bootstrap SQL.** `infra/postgres/init/` is still mounted by the
> compose `db` service and remains the authoritative bootstrap for a new
> database, because it also creates objects the ORM models don't yet express:
> the partial **unique** dedup indexes on `raw_items`, the `healthcheck` table,
> the `updated_at` triggers, and the `feed_view` / `cluster_detail_view` views.
> On a database created by that SQL, `alembic upgrade head` is effectively a
> no-op stamp (every table already exists, columns already `timestamptz`).
> Bringing the ORM models to full parity with the bootstrap SQL — so the init
> mount can be retired and Alembic becomes the *sole* fresh-install path — is a
> follow-up; see the PR for brief 07.

### Existing database (the production Pi)

The live Pi database predates Alembic, so it has no `alembic_version` table.
Stamp the baseline first (asserts "the schema already matches the baseline"),
then upgrade to apply the timezone-aware conversion:

```bash
alembic stamp 0001_baseline
alembic upgrade head
```

`0002_timezone_aware` converts only columns that are still
`timestamp without time zone`, interpreting their stored values as UTC, so it is
safe to run whether or not the Pi's columns were already `timestamptz`.

## Creating a new revision

```bash
# Autogenerate from model changes (review the generated file before committing!)
alembic revision --autogenerate -m "describe the change"

# Or hand-write an empty revision
alembic revision -m "describe the change"
```

Always read the generated migration — autogenerate does not detect everything
(server defaults, some index/constraint changes, data migrations) and may emit
spurious operations. Edit it down to the intended change, then `alembic upgrade
head` to apply.
