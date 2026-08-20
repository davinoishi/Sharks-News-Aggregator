# Eval sets and harnesses

Two things live here: the hand-labelled clustering pairs, and the entry points
for the two evaluation scripts. Both scripts are in `api/app/scripts/`.

## `pairs.seed.jsonl` — hand-labelled clustering pairs

19 variant pairs with human `should_merge` labels, drawn from the production
clusters measured for `RM-4` on 2026-08-19. Ground truth for the pair harness
below and for brief 16's `story_key` comparison.

Each record carries `a_title`, `b_title`, `should_merge`, plus the `entities`
and `event_type` of the cluster it came from and a `provenance` string.

**The `entities` and `event_type` fields are not optional decoration.** Without
them a pair runs through the *entityless* fallback (`T >= 0.55`) instead of the
production path, which made a genuine wire-syndication merge look broken. Any
pair added here needs them.

Two entries are worth knowing about specifically:

- *"3 Cards to Watch at Goldin"* vs *"Card Auction Nears $500K"* — labelled
  `true`, and brief 14 knowingly loses it ("card"/"cards" do not match without
  stemming). It is here so the loss stays visible rather than quietly accepted.
- *"Celebrini, Misa make Sharks clear No. 1"* vs *"Sharks are No. 1 in NHL
  Pipeline Rankings"* — labelled `true`, and production had these on **different
  cards** (4152 and 4188). Over-merging causes under-merging; this pair is the
  recall side of RM-4.

## Pair harness — `app.scripts.eval_pairs`

Scores the matcher against the labelled pairs and reports merge **precision and
recall separately**. Brief 14 buys precision with recall on purpose, and one
blended number hides exactly that trade.

```bash
# On the Pi. Scratch database — the script refuses production-looking names.
docker compose -f docker-compose.yml -f docker-compose.pi.yml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE eval_pairs_scratch;"'

docker cp api/eval/pairs.seed.jsonl sharks-news-aggregator-api-1:/tmp/pairs.seed.jsonl

docker compose -f docker-compose.yml -f docker-compose.pi.yml exec -T \
  -e PYTHONPATH=/app -w /app api python -m app.scripts.eval_pairs \
  --database-url 'postgresql+psycopg://USER:PW@db:5432/eval_pairs_scratch' \
  --pairs /tmp/pairs.seed.jsonl --verbose
```

`PYTHONPATH=/app` is required: Python sets `sys.path[0]` to the script's
directory, so a module run from `/tmp` cannot import `app`.

Drop the scratch database afterwards.

**Measured baseline (2026-08-19):** precision **0.857**, recall **0.857**. Both
remaining mismatches are documented in brief 14 — the Cale Makar pair (shares
the word "extension"; needs `story_key`) and the Goldin card pair (stemming).

### Two traps this harness already fell into

Recorded because the numbers looked plausible both times.

1. **Rollback is not isolation here.** `match_or_create_cluster` commits
   internally, so an earlier version's per-pair rollback did nothing and every
   pair saw the clusters built by every previous pair. It truncates between
   pairs now. If you write another harness around that function, do the same.
2. **Check the inputs before believing a regression.** Its first run reported
   precision 1.000 / recall 0.143 with the wire-syndication control failing —
   entirely an artifact of pairs missing `entities`/`event_type`.

## Corpus freeze — `app.scripts.freeze_eval_corpus`

Writes a stratified snapshot of `raw_items` plus candidate pairs.

```bash
docker compose -f docker-compose.yml -f docker-compose.pi.yml exec -T api \
  python -m app.scripts.freeze_eval_corpus --out /app/eval_corpus/corpus-YYYY-MM-DD.jsonl
docker cp sharks-news-aggregator-api-1:/app/eval_corpus/... ./eval_corpus/
```

**Run it regularly.** `run_purge_old_items` deletes `raw_items` after 30 days, so
an unfrozen corpus stops existing. The api container has no bind mount, so write
inside it and `docker cp` the result out — anything left in the container is lost
on the next `up -d`.

Output is gitignored: bulk third-party article text, and `R3-A1` tracks keeping
data dumps out of the repo. Store it with the backups (`R3-O1`).

Labels the script emits are `derived` — they record what production did, and
production is what is under test. Verify by hand and set `label_source` to
`human`. The one exception is the `ingest_stub` stratum, marked
`low_value_confidence: "high"`: a rule matched those, so the label is not an
inference.
