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

### Two traps that take the whole API down

Both were hit while writing revisions `0006` and `0007` (2026-08-19). They matter
more than ordinary migration bugs because the API's command is
`alembic upgrade head && uvicorn` — **a migration that raises means uvicorn never
starts**, so the symptom is not a migration error anyone sees, it is the service
failing to come up. In CI that surfaced as a ten-minute
`API did not become healthy` timeout with no other detail.

**1. A revision that adds a new TABLE must be idempotent.** On a fresh database
the schema is built by `infra/postgres/init/001_init.sql`, which Postgres runs
automatically from `/docker-entrypoint-initdb.d`. `0001_baseline` then runs
`Base.metadata.create_all(checkfirst=True)`, which is mostly a no-op — except for
tables the init script does not define, which it **creates**. A later
`op.create_table` for one of those then fails with DuplicateTable.

Columns are not affected: `checkfirst` tests whether the *table* exists, not its
columns, so `create_all` skips an existing table entirely and a later
`op.add_column` on it succeeds. That is why `0005` (a column on `clusters`)
needed no guard while `0006` (a new table) did.

Guard new tables on the inspector, the way the baseline guards itself:

```python
bind = op.get_bind()
if sa.inspect(bind).has_table("my_table"):
    return  # already created by the baseline's create_all
```

This does not affect an existing database, where the baseline ran long ago and
the guard simply passes.

**2. `op.execute()` parses `:name` as a bind parameter.** It routes the string
through `sqlalchemy.text()`, so a colon inside a SQL literal is read as a
placeholder. `LIKE '%"relevant":true%'` fails with
`A value is required for bind parameter 'true'`. Escape colons as `\:` and use a
raw string:

```python
op.execute(r"""... LIKE '%"relevant"\:true%' ...""")
```

`test_migration_0007_sql_has_no_accidental_bind_parameters` pins this for `0007`
by parsing the inline SQL through `text()` and asserting it yields no bind
parameters. Worth copying for any revision with inline SQL.

**Debugging aid:** `docker-verify` dumps `api` and `db` container logs on failure
(added 2026-08-19). If a migration fails in CI, the traceback is in that step —
do not guess from the health timeout.

**Rebuilding from scratch** works through the compose stack — init SQL first,
then migrations — and `docker-verify` exercises that path on every CI run. It
does **not** work against a bare database created by hand: with no init script
there are no enum types, and `0003` fails with `type "source_status" does not
exist`. If you ever move off the compose-managed Postgres, apply
`infra/postgres/init/001_init.sql` before migrating. See `OPS-1` in
[IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md) for the full investigation.
