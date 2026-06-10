# Brief 06 — Test suite for the core pipeline

Plan item: **Q1** (see `docs/IMPROVEMENT_PLAN.md`). Depends on brief 05 (CI)
being merged. Must merge **before** brief 07 (refactors) starts — these tests
are the refactoring safety net.

## Task

Build a pytest suite covering the logic that makes the product work: URL
normalization/dedup, clustering, classification fallback, feed queries, and
LLM response parsing. No production code changes except minimal seams needed
for testability (e.g. dependency injection of a session — keep such changes
surgical and call them out in the PR).

## Context

- Zero tests exist. CI (brief 05) runs `pytest api/` and currently tolerates
  "no tests collected" — once this brief lands, remove that tolerance in the
  workflow.
- Key modules and what matters in each:
  - `api/app/tasks/ingest.py` — `normalize_url()` (tracking-param stripping,
    Google-redirect unwrapping, fragment removal), `create_raw_item()` dedup
    (source_item_id, canonical_url, ingest_hash, same-source title), age gate
    (`max_article_age_days`), `sanitize_feed_xml()`, `strip_html()`,
    `parse_published_date()`.
  - `api/app/tasks/enrich.py` — `normalize_tokens()`, `extract_entities()`,
    `extract_game_identifier()` (opponent table + date),
    `match_or_create_cluster()` (entity overlap + token similarity + time
    window + game-id matching; thresholds in `api/app/core/config.py`),
    keyword fallback classification.
  - `api/app/core/queries.py` — `build_feed_query()` filters (tags, entities,
    since), ordering. (Brief 04 may have already added some tests here —
    extend, don't duplicate.)
  - `api/app/services/openrouter.py` — `_parse_json_content()` (plain JSON,
    markdown-fenced, embedded), `check_relevance()` fail-open on error,
    `classify_and_summarize()` tag/event validation against allowed sets.
  - `api/app/main.py` — `parse_since_parameter()` (24h/7d/ISO/garbage),
    `_parse_llm_approved()`.
- Database: Postgres 16 in compose. Models use Postgres features; prefer a
  real Postgres for DB-backed tests (GitHub Actions `services:` container, or
  `testcontainers`). SQLite-in-memory is acceptable ONLY if the models work on
  it unmodified — verify before committing to that path.
- All OpenRouter/HTTP calls must be mocked (`respx` or monkeypatching the
  service); tests must run offline. Celery tasks: call the task function
  bodies directly (they're plain functions), never run a worker.

## Requirements

1. Layout: `api/tests/` with `conftest.py` providing a DB session fixture
   (transaction-rollback per test), model factories (plain helper functions
   are fine — no factory_boy requirement), and a mocked OpenRouter fixture.
2. Coverage targets (breadth over depth — the goal is regression protection):
   - ~10–15 cases for `normalize_url` + dedup paths.
   - Clustering: same-story-two-sources merges into one cluster; unrelated
     stories don't merge; game articles cluster by game-id; time window
     respected; threshold boundary cases (just above/below
     `cluster_similarity_threshold`).
   - Feed query: tag filter, entity filter, since filter, multi-tag
     no-duplicates, unknown-slug behavior (assert whatever brief 04 defined).
   - LLM parsing: all three JSON extraction paths + unparseable → error;
     fail-open returns `is_relevant=True` with `error` set.
   - `parse_since_parameter` + `_parse_llm_approved` edge cases.
3. Add `pytest`, any test deps to a new `api/requirements-dev.txt`; CI
   installs it.
4. Update the CI workflow: remove the exit-code-5 tolerance; add the Postgres
   service if you chose real-Postgres tests.
5. Keep total suite runtime under ~2 minutes in CI.

## Out of scope

- Refactoring production code for style (brief 07).
- Frontend tests.
- Integration/e2e tests against running Docker services.
- Fixing bugs you discover: write the test as `xfail` with a comment and a
  list in the PR description instead (unless the fix is one line).

## Verification

- `pytest api/` green locally and in CI on the PR.
- Deliberately break `normalize_url` locally → relevant tests fail (spot-check
  the suite actually bites). Revert.
- CI runtime for the api job stays under ~5 minutes.

## Deliverable

Branch `improve/06-tests`, PR against `main`. PR description lists any `xfail`
bugs discovered. Update the status table in `docs/IMPROVEMENT_PLAN.md`.
