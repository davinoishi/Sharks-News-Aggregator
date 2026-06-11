# Legacy migrations (deprecated)

These files predate the adoption of **Alembic** (brief 07, C6) and are kept only
for historical reference. **Do not run them on new databases** — the schema is
now managed by Alembic (`api/alembic/`). See [`docs/MIGRATIONS.md`](../../../docs/MIGRATIONS.md).

## Contents

Hand-written one-off SQL migrations that were applied manually to the production
(Pi) database before Alembic existed:

- `add_game_and_llm_columns.sql` — added `clusters.game_identifier`,
  `validation_logs.llm_confidence` / `llm_reason`, widened `llm_response`.
- `drop_feed_cache.sql` — dropped the unused `feed_cache` table (brief 04, P2).
- `hash_submitter_ip.sql` — widened `submissions.submitter_ip` to hold a
  SHA-256 hex digest (brief 03, S5).

Ad-hoc data/back-fill scripts (previously under `app/scripts/`):

- `migrate_validation_logs.py`
- `migrate_bluesky_posts.py`

All of the schema changes above are already folded into the current schema
(`infra/postgres/init/` for the bootstrap and the Alembic baseline). New schema
changes must be added as Alembic revisions instead.
