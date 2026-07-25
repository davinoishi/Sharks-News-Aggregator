# Brief 10 — MCP interface for agent access

Plan items: **R2-U1** (full-text search) plus new **MCP-1 … MCP-5**
(see `docs/IMPROVEMENT_PLAN.md`).

**This brief is larger than briefs 01–09. Ship it as two PRs, one per session:**

| Phase | Scope | Items | Effort |
|-------|-------|-------|--------|
| **A** | Search backend + feed ergonomics (pure FastAPI/Postgres work) | R2-U1, MCP-1 | M–L |
| **B** | The MCP server itself | MCP-2, MCP-3 | M |
| (C) | Remote transport + auth — **deferred, do not build yet** | MCP-4, MCP-5 | — |

Phase A is independently useful (the web UI wants search too) and must merge
before Phase B starts — the MCP `search_news` tool is a thin wrapper over the
Phase A endpoint. Touches `api/app/routers/feed.py`, `api/app/schemas.py`, and
`api/app/core/queries.py`; coordinate with any other in-flight work on those.

## Task

Expose the aggregator to LLM agents over the Model Context Protocol: fetch the
feed, search it, and pull story detail. The MCP wrapper is thin — the real work
is that **search does not exist in the backend today**, and the feed response
is missing fields agents need.

## Context

### The read surface already exists and is close to MCP-shaped

| Endpoint | File | Parameters |
|---|---|---|
| `GET /feed` | `api/app/routers/feed.py:28` | `tags`, `entities`, `since` (`24h\|7d\|30d\|ISO`), `limit` (≤100), `cursor` |
| `GET /cluster/{id}` | `api/app/routers/feed.py:90` | full detail + all source variants |
| `GET /entities` | `api/app/routers/feed.py:157` | `query`, `limit` — name search for the player picker |
| `GET /stats` | `api/app/routers/metrics.py:14` | page views, story count, source count |
| `GET /health` | `api/app/routers/health.py:13` | includes the brief-09 `degraded` flag |
| `GET /rss` | `api/app/routers/feed.py:182` | latest 50 clusters |

Response models are in `api/app/schemas.py`; pagination is proper keyset on
`(last_seen_at, id)` (`api/app/core/queries.py:110`).

### Gaps this brief closes

- **No search anywhere (R2-U1).** The only search in the codebase is
  `search_entities_by_name()` (`api/app/core/queries.py:296`), a
  `Entity.name.ilike()` for the filter picker. There is no index on cluster or
  variant text. Both the round-2 and round-3 external reviews ranked full-text
  search as the top usability gap.
- **`clusters.llm_summary` is never exposed.** The column exists
  (`api/app/models/cluster.py:70`) but neither `format_cluster_for_feed()`
  (`api/app/core/queries.py:228`) nor `ClusterItem` (`api/app/schemas.py:31`)
  returns it. Agents get a headline and a link with no summary text — which is
  most of the value of an aggregator feed.
- **No public tag list.** `get_tag_distribution()` exists
  (`api/app/core/queries.py:334`) but is not routed. An agent can only learn
  the tag vocabulary by inferring it from feed results, so `tags=` filtering is
  effectively guesswork.
- **No `event_type` filter on `/feed`.** It is a first-class enum column
  (`EventType` in `api/app/models/cluster.py:21`: trade/injury/lineup/recall/
  waiver/signing/prospect/game/opinion/other) and exactly what an agent will
  reach for, but the feed only filters by tag and entity.
- **No date-range filter** — `since` only, no upper bound.

### Constraints to respect

- **30-day retention.** `run_purge_old_items()`
  (`api/app/tasks/maintenance.py:35`) deletes clusters and raw items older than
  30 days. Search can never return older material. This must be stated in the
  MCP tool descriptions or agents will report "no coverage" for older events as
  if it were a fact about the world.
- **The API is not publicly reachable.** In `docker-compose.yml` the `api`
  service has no `ports:` mapping at all — only `web` is published (3001), and
  that is what the noBGP tunnel fronts. `docker-compose.pi.yml` publishes the
  API on `8001` to the Pi host only. The browser never talks to FastAPI; every
  request goes through the Next.js proxy routes in `web/app/api/*/route.ts`.
- **Rate limiting is not production-grade for a public endpoint.**
  `enforce_metrics_rate_limit()` (`api/app/dependencies.py:95`) is in-memory and
  per-process; its own docstring says it is not meant for strict enforcement,
  and it is wired only to the metrics endpoints. Backlog item R3-S2 already
  flags rate-limiting `/rss`.
- **Tests.** DB-backed tests use the `pg_db` fixture and the
  `requires_postgres` marker in `api/tests/conftest.py`; the default pytest run
  is SQLite and skips them. CI runs a separate `postgres-tests` job against
  `postgres:16`. Anything `tsvector`-related goes under `requires_postgres`.
- **Pi capacity.** Single Raspberry Pi 5, shared with other services. `/feed`
  has never been load-tested (R3-T3). Agent traffic is burstier and less
  cacheable than human browsing.

---

## Phase A — search backend and feed ergonomics

### A1. R2-U1 — full-text search

- **Schema.** Add a stored generated column on `clusters`:

  ```sql
  ALTER TABLE clusters ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
      to_tsvector('english', coalesce(headline, '') || ' ' || coalesce(llm_summary, ''))
    ) STORED;
  CREATE INDEX ix_clusters_search_vector ON clusters USING GIN (search_vector);
  ```

  A generated column is preferred over a trigger: no backfill step, no way for
  the enrichment path to forget to update it, and Postgres 16 handles it
  natively. Declare it on the model with SQLAlchemy `Computed(..., persisted=True)`
  so `Base.metadata.create_all()` emits it — the `pg_db` test fixture builds
  the schema that way, not through Alembic, and the column will silently not
  exist in tests otherwise.
- **Migration.** New Alembic revision in `api/alembic/versions/`, following the
  existing `YYYYMMDD_NNNN_description.py` naming. Must be downgrade-safe.
- **Query.** Use `websearch_to_tsquery('english', q)` — it accepts user-style
  input (quoted phrases, `or`, `-exclusion`) and, unlike `to_tsquery`, does not
  raise on malformed input. Rank with `ts_rank_cd`. Blend in recency so a
  relevant story from last week outranks a marginally-more-relevant one from
  four weeks ago; a simple decay multiplier is fine, do not over-engineer it.
- **Endpoint.** `GET /search?q=&since=&event_type=&limit=` returning the same
  `ClusterItem` shape as `/feed` so clients and tools share one model.
- **Pagination.** Relevance ordering is incompatible with the existing
  `(last_seen_at, id)` keyset cursor — do **not** try to reuse `encode_cursor`.
  Return a ranked, capped list (`limit` ≤ 50, default 20) with **no cursor**.
  Deep pagination through search results is not a requirement here; say so in
  the docstring so the next reader doesn't "fix" it.
- **Empty/no-match:** empty `q` → 422; no matches → `200` with an empty list,
  never a 404.
- **Scope:** cluster-level text only (`headline` + `llm_summary`). Cluster
  headlines are already derived from the best variant title, so indexing
  `story_variants.title` separately adds cost for little recall. Note it as a
  follow-up, don't build it.

### A2. MCP-1 — expose what agents (and the UI) need

- Add `llm_summary` to `format_cluster_for_feed()` and to the `ClusterItem`
  schema, nullable. Verify `web/app/types.ts` and `ClusterCard.tsx` tolerate the
  new field — additive, so they should, but check rather than assume.
- Add `event_type` as a filter parameter on `/feed` (single value or
  comma-separated list, validated against the `EventType` enum; unknown value →
  422, not a silent empty feed).
- Add an `until` parameter alongside `since`, parsed by the same
  `parse_since_parameter()` path in `api/app/utils.py`.
- Route the existing `get_tag_distribution()` as `GET /tags`, returning slug,
  name, display colour, and active-cluster count.

### A3. Tests (Phase A)

Extend the existing suites rather than adding new files where one already fits
(`api/tests/test_feed_queries.py`, `api/tests/test_public_endpoints.py`):

- Search matches on headline text and on `llm_summary` text.
- Stemming works (`"traded"` finds `"trade"`); ranking puts the better match first.
- Malformed query input (`"foo ((("`, a bare `-`) returns 200, not a 500.
- `event_type` filter returns only matching clusters; an invalid value 422s.
- `since` + `until` bound the window correctly at both ends.
- `/tags` returns counts that match the seeded fixture data.

---

## Phase B — the MCP server

### B1. MCP-2 — server package and tools

- New top-level `mcp/` package (its own `pyproject.toml`/requirements — do
  **not** add the MCP SDK to `api/requirements.txt`; the API image should not
  grow for a client-side tool). Uses the official Python `mcp` SDK, stdio
  transport, and talks to the aggregator over HTTP with a configurable base URL
  (`SHARKS_API_URL`), defaulting to the public Next.js origin so it works with
  no server-side change at all.
- **Read-only. Six tools:**

  | Tool | Backing endpoint |
  |---|---|
  | `search_news(query, since, event_type, limit)` | `GET /search` |
  | `get_feed(tags, entities, event_type, since, until, limit, cursor)` | `GET /feed` |
  | `get_story(cluster_id)` | `GET /cluster/{id}` |
  | `list_players(query)` | `GET /entities` |
  | `list_tags()` | `GET /tags` |
  | `get_status()` | `GET /health` + `GET /stats` |

- **Tool descriptions carry the domain caveats** — Sharks-focused coverage, the
  30-day retention window, and the fact that "sources" are aggregated
  third-party outlets, not original reporting. Agents route on these
  descriptions; vague ones produce bad tool selection.
- **Do not auto-generate tools from `/openapi.json`.** FastAPI publishes the
  schema and `fastapi-mcp`-style adapters will happily consume it, but that
  exposes all 13 `/admin/*` routes as tools and yields machine-generated
  descriptions agents use poorly. Hand-write the six.

### B2. MCP-3 — response budgeting

The most likely way this ships badly is by flooding the agent's context.
`/feed?limit=50` returns 50 clusters each carrying full tag and entity arrays.

- Default `limit` of 10, hard cap 25 — lower than the HTTP API's cap of 100.
- Return compact markdown-ish text, not a raw JSON echo: headline, summary
  line, event type, source count, age, link. Keep full detail for `get_story`,
  which an agent calls for one cluster at a time.
- Strip fields agents cannot use (`click_count`, internal ids beyond
  `cluster_id`, tag colours).

### B3. Verification and docs (Phase B)

- Unit tests for the tool layer against a mocked HTTP client — argument
  validation, limit clamping, and the compact rendering. No live network in CI.
- `mcp/README.md` with the client config block for connecting the server, plus
  the `SHARKS_API_URL` variable.
- A short section in the root `README.md` under Features.

---

## Phase C — deferred, do not build in this brief

**MCP-4 (remote transport)** and **MCP-5 (auth + abuse controls)** are recorded
so the Phase B design doesn't paint them into a corner, but they are explicitly
out of scope. Revisit only after Phase B has been used in practice.

Three options were evaluated for reaching the server remotely:

| Option | Trade-off |
|---|---|
| Streamable-HTTP MCP mounted on FastAPI at `/mcp`, published as a second noBGP service | Any remote agent can connect; adds a new public attack surface on the Pi and needs real auth |
| An MCP route inside Next.js reusing the existing proxy pattern | Rides the existing public URL and middleware; duplicates tool logic in TypeScript, away from the Python data layer |
| stdio only (**this brief**) | Zero new exposure, zero server change; only usable by clients that can spawn the process |

If Phase C is ever picked up, it needs a static bearer token **and** a real
shared-state rate limiter (Redis is already in the stack) — the in-memory
per-process limiter is not sufficient for an unauthenticated public endpoint.
Full MCP OAuth is overkill here. An unauthenticated public MCP endpoint over
this data is an invitation to pull the whole database on a loop against a
Raspberry Pi.

## Out of scope

- **All write tools.** `POST /submit/link` has a solid SSRF guard
  (`api/tests/test_submit_ssrf.py`), but exposing submission to agents fills the
  review queue with spam for no clear benefit.
- **All `/admin/*` tools.** Not in v1, not behind a flag.
- Remote transport, auth, OAuth (Phase C above).
- Search UI in the Next.js frontend — Phase A ships the endpoint; the search box
  is a separate UX change.
- Variant-level (`story_variants.title`) search indexing.
- Semantic/vector search. Postgres FTS is the right tool at this data volume;
  pgvector on a Pi for a few thousand clusters is not.

## Verification

**Phase A**

- `cd api && PYTHONPATH=. pytest -q` passes; the Postgres-marked tests pass
  under the `postgres-tests` CI job.
- `alembic upgrade head` then `alembic downgrade -1` both succeed against a
  scratch database with real data in `clusters`.
- `EXPLAIN ANALYZE` on the search query shows the GIN index in use, not a
  sequential scan.
- Manual: `curl "localhost:8000/search?q=celebrini+injury"` returns ranked,
  plausible results; `/feed?event_type=trade` returns only trade clusters;
  `/tags` returns the tag vocabulary.
- The web UI still renders correctly with `llm_summary` added to the feed
  payload.

**Phase B**

- The server starts under stdio and a connected client lists exactly six tools.
- Each tool executes end-to-end against a running local stack.
- A `get_feed` call at default limit produces a response small enough to be
  quoted whole in the PR description — if it isn't, MCP-3 isn't done.
- `ruff check` clean over the new package.

## Deliverable

Two PRs against `main`, one per session:

- **Phase A** — branch `improve/10a-search`, PR with verification transcript
  (including the `EXPLAIN ANALYZE` output) and updated docs.
- **Phase B** — branch `improve/10b-mcp`, PR with `mcp/README.md`, the client
  config block, and a transcript of a real agent session using the tools.

Update the status table in `docs/IMPROVEMENT_PLAN.md` and mark **R2-U1** done
when Phase A merges.
