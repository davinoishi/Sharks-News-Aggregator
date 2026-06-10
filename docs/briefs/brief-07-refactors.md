# Brief 07 — Structural refactors: routers, modules, timezone-aware datetimes, Alembic

Plan items: **Q3, Q4, C2, C3, C6** (see `docs/IMPROVEMENT_PLAN.md`).

**Preconditions (hard):** briefs 05 (CI) and 06 (tests) merged; `pytest api/`
green on `main`. Brief 01 (auth) merged — it touches `main.py` and must land
first. Do not start otherwise.

This is the largest brief. If needed, split into two PRs in this order:
(a) Q3+C3, (b) Q4+C2+C6. Behavior must not change except where C3 removes
dead endpoints.

## Task

Break up the two giant modules, make admin auth structural, remove stub
endpoints, migrate to timezone-aware datetimes, and adopt Alembic as the
single migration mechanism.

## Context

- `api/app/main.py` (~1,100 lines): all routes, Pydantic schemas, admin auth,
  utilities in one file, with imports inside function bodies.
- `api/app/tasks/enrich.py` (~1,240 lines): entity extraction, keyword
  classification, LLM orchestration, clustering, the NHL opponent-team table,
  and game-id extraction all in one module.
- **C3 stubs:** `/admin/candidate-sources` returns hardcoded empty data;
  approve/reject return 501; `ingest_html`/`ingest_api` in `ingest.py` return
  `not_implemented`. Decision: **remove** the three candidate-source endpoints
  (model stays — the data pipeline may still write candidates), and make the
  unimplemented ingest methods log a warning and mark the source broken
  instead of silently "succeeding".
- **C2:** naive `datetime.utcnow()` used throughout API + tasks; scattered
  `.replace(tzinfo=None)` compensations. DB columns are `TIMESTAMP` (check
  `infra/postgres/init/001_init.sql` and models for whether they're
  timezone-aware).
- **C6:** Alembic is in `requirements.txt` but unused. Schema lives in
  `infra/postgres/init/*.sql` (fresh installs), `api/migrations/*.sql`
  (manual), and `api/app/scripts/migrate_*.py` (ad-hoc). The live Pi database
  predates some of these — the baseline must be stampable onto an existing DB.

## Requirements

1. **Q3 — split `main.py`** into `api/app/routers/` (`feed.py`, `submit.py`,
   `metrics.py`, `admin.py`, `health.py`) with schemas in `api/app/schemas.py`
   and shared helpers (`parse_since_parameter`) in a util module. Admin router
   uses `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` so
   no admin endpoint can forget auth. Module-level imports only. Route paths,
   methods, and response shapes must be byte-for-byte unchanged (except C3
   removals).
2. **Q4 — split `enrich.py`** into e.g. `api/app/enrichment/`:
   `entities.py`, `classify.py` (keyword + LLM orchestration), `clustering.py`
   (match_or_create + similarity), `teams.py` (NHL table + game-id). The
   Celery task stays a thin orchestrator in `tasks/enrich.py` with its
   registered name unchanged (`app.tasks.enrich.enrich_raw_item`) so queued
   messages survive the deploy.
3. **C3** as decided above; delete the corresponding admin proxy/frontend
   references if any exist.
4. **C2 — timezone-aware datetimes:** replace `datetime.utcnow()` with
   `datetime.now(timezone.utc)` (or a `utcnow()` helper returning aware UTC)
   across `api/`. Make model columns `DateTime(timezone=True)` and add the
   Alembic migration converting existing columns
   (`ALTER ... TYPE timestamptz USING column AT TIME ZONE 'UTC'`). Remove the
   `.replace(tzinfo=None)` patches. API JSON output must remain
   ISO-8601-with-offset or unchanged-shape (frontend parses with
   `new Date(...)` — verify it still renders correct local times).
5. **C6 — Alembic:** init under `api/alembic/`, autogenerate a baseline
   matching current models, document the workflow in `docs/MIGRATIONS.md`:
   fresh install = run migrations (replace init-SQL reliance), existing DB
   (the Pi) = `alembic stamp` the baseline then upgrade. Fold the C2 column
   migration in as the first real revision. Add an
   `alembic upgrade head` step to the API container startup or document the
   manual step in `PRODUCTION_CHECKLIST.md`. Mark old SQL/script migrations
   as deprecated (move to `api/migrations/legacy/`).
6. **Tests:** full suite green throughout; add a route-table snapshot test
   (list of `(method, path)` pairs) so future refactors can't drop endpoints
   silently.

## Out of scope

- Any behavior/feature changes beyond C3 removals.
- Frontend changes.
- Implementing HTML/API ingestion for real.
- Performance work (brief 04) — rebase on it if it's merged.

## Verification

- `pytest api/` green; CI green.
- `docker compose up`: full pipeline runs — ingest fires, items enrich,
  clusters appear in `/feed`, frontend renders, admin pages work with auth.
- Compare `GET /openapi.json` route list before/after: identical except the
  removed candidate-source endpoints.
- Fresh-DB path: `docker compose down -v && docker compose up` brings up a
  working empty instance via Alembic.
- Existing-DB path: against a copy of the production dump
  (`db_data_export.sql` in repo root), stamp + upgrade succeeds.

## Deliverable

Branch(es) `improve/07a-routers` / `improve/07b-modules-tz-alembic` (or one
`improve/07-refactors` if kept together), PR(s) against `main` with the
openapi diff and migration test transcript. Update the status table in
`docs/IMPROVEMENT_PLAN.md`.
