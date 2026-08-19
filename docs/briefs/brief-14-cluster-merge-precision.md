# Brief 14 — Cluster merge precision

Plan item: **`RM-4`** (`docs/IMPROVEMENT_PLAN.md`). Tasks **CM-1 … CM-7**.

**Ships as one PR.** API/worker only — no web changes, no schema migration. The
card UI work is deliberately held for brief 15.

## Task

A reader reported that the card *"Macklin Celebrini Card Auction Nears $500K &
It's Not Done"* also contained two articles about The Athletic's NHL pipeline
rankings. It does, and it is not an isolated card: five of the 35 multi-variant
clusters in the live feed are similarly mixed, and the largest holds 116 variants
across 435 hours.

Stop the clustering matcher from merging two articles that share nothing but a
person's name and an event type, without breaking the syndication merging that
makes the feed useful.

## Context

### The governing principle — read this before tuning anything

**Over-splitting is the cheap failure. Over-merging is the expensive one.**

A duplicate card costs the reader one redundant glance. A wrong merge costs them
the story outright: variant titles are hidden behind the "View sources" control
(`web/app/components/ClusterCard.tsx:146`), so a reader who has finished with a
storyline never expands that card and never learns the other story exists. The
pipeline did the expensive work correctly and then filed the result where nobody
looks.

Every threshold decision in this brief resolves in favour of a new cluster.
Where a change trades a lost good merge for several blocked bad merges, take it,
and record the loss in the PR description.

### What exists today

`match_or_create_cluster()` (`api/app/enrichment/clustering.py:108`) has **six
routes to a merge**, tried in order:

1. **Syndication UUID** (`:131`) — a shared UUID in the URL path. Content is
   never compared.
2. **Game identifier** (`:194`) — `game` events only.
3. **Title similarity / strong containment / title name-match** (`:218–290`) —
   all three carry lexical gates.
4. **Score path** (`:296–395`) — `E`/`T`/`K`/`L` combined by
   `calculate_similarity_score()` (`:450`) and gated by `is_match()` (`:687`).
5. **Summary name-match** (`:371`) — a shared person name in two LLM summaries
   plus `K >= 0.5`, bypassing the score entirely.

Candidates come from a window anchored on `Cluster.last_seen_at` (`:181`), which
`update_cluster_metadata()` advances on every join (`:910`).

Thresholds live in `api/app/core/config.py:26–38`.

### The proven defect

`0.55·E + 0.35·T + 0.10·K` with a merge gate of `S >= 0.62`. Same player, same
event type, **zero shared words**:

```
E = 1.00, T = 0.00, K = 1.0  ->  S = 0.650  >=  0.62   -> merged
```

`filter_team_entities()` strips team entities, so the entities that drive `E` are
exactly people. A cluster about one star saturates `E = 1.0` against every other
article about that star. The defect is worst where coverage is heaviest.

The entity's name is also counted **twice** — in `E`, and again in `T`, since
"macklin"/"celebrini" are ordinary tokens. Measured over real production pairs,
that overlap makes a plain `T` threshold useless:

| | `T` values observed |
|---|---|
| Pairs that **should** merge | 0.400, 0.700, 0.250, 0.200, 0.231, 0.214 |
| Pairs that **should not** | 0.000, 0.200, 0.000, 0.100, 0.053, 0.000, 0.200 |

They overlap, so no threshold on `T` separates them. Removing entity-derived
tokens first does separate them — see CM-3.

### Measured before designing (2026-08-19, offseason, 225 clusters)

Baseline to beat, computed from `/api/cluster/{id}` over every cluster with 3+
surviving variants. "Cohesion" is mean pairwise Jaccard of normalised headline
tokens:

| Cohesion | Span | Variants | Cluster |
|---|---|---|---|
| 0.032 | 46h | 4 | NHL Rumors: Sharks willing to offer Celebrini max contract |
| 0.041 | 157h | 6 | Connor McDavid Speaks Out On Darnell Nurse Trade |
| 0.111 | 179h | 10 | 'Mac is crazy': Leafs' McKenna on summer training with Celebrini |
| 0.135 | 130h | 7 | Macklin Celebrini Named IIHF Male Player of the Year |
| 0.143 | 127h | 8 | Macklin Celebrini Card Auction Nears $500K *(reported)* |
| 0.197 | **435h** | **116** | Sharks sign Celebrini to 5-year, $94M extension |
| 0.489 | 146h | 52 | Sharks ink Graf to 3-year contract — **legitimate wire syndication** |

**5 of 35 below 0.15.** The Graf row is the control: high cohesion, large, and
correct. A change that flattens it has gone too far.

### Decisions already taken — do not re-litigate

- **Do not raise `cluster_similarity_threshold` as the fix.** It would sacrifice
  genuine syndication merges (the Graf cluster) to buy a partial improvement, and
  it leaves the summary-name bypass — which skips the score entirely —
  untouched.
- **Do not tune `token_similarity_threshold` upward.** The table above shows the
  distributions overlap. This is the RM-3 mistake in a new place: see
  `[[relevance-change-seasonal-measurement]]`.
- **Do not add an LLM call to adjudicate merges in this brief.** The durable
  semantic fix is a `story_key` field added to the classifier's existing JSON
  response — zero extra calls — and it belongs to brief 15 with its own
  measurement. Adding a second network call per candidate pair to the enrich task
  is not an acceptable substitute.
- **The gate shipped here is "some topical evidence", not "enough topical
  evidence".** It blocks merges backed by *zero* content overlap. It will not
  separate the genuinely hard pairs; that is brief 15's job. Scope it that way
  deliberately rather than over-fitting thresholds to eight examples.
- **No schema migration.** Everything needed is already on the models.
- **Measure in-season too.** These numbers are August. Game-day clustering
  (`game_identifier`, 24h windows) barely exists in the offseason sample, so the
  eval in CM-6 must include game-event fixtures rather than relying on the live
  feed to exercise them.

---

## CM-1 — Instrument the merge decision

**Do this first, and land it before the gates in CM-2…CM-5**, so the production
log records the *old* behaviour for at least one ingest cycle.

- **Approach.** In `match_or_create_cluster()`, emit one structured `INFO` record
  per clustering decision naming the deciding route (`syndication`, `game`,
  `title`, `containment`, `title_name`, `score`, `summary_name`, `new_cluster`)
  plus `cluster_id`, `variant_id`, and the `E`/`T`/`K`/`L`/`S` values. The
  existing per-candidate detail stays at `debug`.
- Why: six routes can produce a merge, and only the score route is proven to be
  at fault. Production keeps `INFO`, not `debug`, so today there is no way to
  attribute an observed bad card to a route. Guessing which to change is how RM-3
  went wrong.
- Keep it to one line per decision, not per candidate — a busy ingest evaluates
  many candidates per variant.
- **Verify.** Run the enrich task against a seeded fixture and confirm exactly
  one decision record per variant, with the route named and the scores present.

## CM-2 — Require positive topical evidence for any score-path merge

- **Approach.** Add a hard precondition to the score route: entity overlap and
  event-type compatibility may **corroborate** a merge, never **cause** one. A
  score-path merge requires at least one of
  - `T_topic > settings.topic_evidence_threshold` (see CM-3), or
  - `L >= settings.summary_evidence_threshold` (LLM summary similarity).
- Default `topic_evidence_threshold = 0.0` — i.e. *any* non-entity token in
  common. Default `summary_evidence_threshold = 0.45`. Both configurable, and
  both deliberately permissive: this gate exists to block the zero-evidence case,
  not to arbitrate close calls.
- Leave routes 1–3 alone. The title routes already carry lexical gates; game and
  syndication matching are separate mechanisms with their own failure modes.
- **Measured effect** on the pairs taken from production (`T_topic` per CM-3,
  ignoring the `L` fallback, which can only rescue more):

  | | Blocked by the gate |
  |---|---|
  | Pairs that should **not** merge | **7 of 8** |
  | Pairs that **should** merge | 1 of 7 |

  The one good merge lost is *"3 Cards to Watch at Goldin: Celebrini, Ohtani,
  Yamal"* against *"Celebrini Card Auction Nears $500K"* — `T_topic = 0.000`
  because "card"/"cards" do not match without stemming. That is an acceptable
  trade under the governing principle, it may still merge via `L`, and brief 15
  resolves it properly. **Record it in the PR rather than hiding it.**
- The one bad pair that survives is the Celebrini extension against *"Cale Makar
  Extension Questions Emerge"* (`T_topic = 0.125`, sharing "extension"). Expected
  — this is the class brief 15 handles.
- **Verify.** The reported pair no longer merges; the Graf syndication cluster
  still forms; `T_topic = 0` with `E = 1.0` and `K = 1.0` creates a new cluster.

## CM-3 — Stop double-counting entity names in the token score

- **Approach.** Add a `T_topic` signal: Jaccard over normalised headline tokens
  with tokens derived from the entity names on **either** side removed. Build the
  strip-set from the names of the entities already credited in `E`, tokenised
  through `normalize_tokens()` so "Macklin Celebrini" removes both parts.
- Use `T_topic` for the CM-2 gate. **Leave the existing `T` in
  `calculate_similarity_score()` unchanged** — this brief changes what is
  *required* to merge, not the ranking among candidates that clear the bar.
  Changing both at once makes a regression impossible to attribute.
- Team tokens ("sharks", "san", "jose") are already excluded in practice because
  `filter_team_entities()` drops team entities from `E`; strip them from
  `T_topic` anyway — they are pure noise, present in nearly every headline.
- **Verify.** Unit tests on `T_topic` directly: the card-auction/pipeline pair
  scores 0.000; the Graf pair scores ~0.29; the two card-auction articles score
  ~0.10.

## CM-4 — Gate the summary-name bypass

- **Approach.** `summary_name_match` (`clustering.py:371`) currently merges on a
  shared person name plus `K >= 0.5`, with no content comparison at all. Require
  `L >= settings.summary_evidence_threshold` in addition.
- Do **not** delete the route. It was added for a real case — a headline naming
  its subject only by role ("Sharks' first-round pick finalizes plans") — which
  `test_role_headline_merges_with_named_sibling_via_summary` covers and which
  must keep passing.
- Note for whoever picks this up: `CLASSIFY_PROMPT_USER`
  (`api/app/services/openrouter.py:72`) tells the model to lead every summary
  with the subject's full name *specifically so same-person stories cluster*.
  That instruction is correct for the role-headline case and actively harmful
  once it is the sole merge criterion. Do not change the prompt in this brief —
  brief 15 revisits it when `story_key` lands.
- **Verify.** The existing role-headline test still passes;
  `test_summary_bridge_keeps_different_people_apart` still passes; a new test
  covering same-person-different-story does not merge.

## CM-5 — Bound cluster lifetime

- **Approach.** Anchor the candidate window to `Cluster.first_seen_at` rather
  than `last_seen_at`: a cluster stops accepting new variants once it is older
  than its own event window, regardless of how much activity it has attracted.
  Add `settings.cluster_max_age_hours` (default 96) as an absolute ceiling so no
  route — including syndication and game matching — can extend a cluster
  indefinitely.
- **Measure the age against the incoming variant's `published_at`, never against
  `utcnow()`.** The pipeline is deliberately publication-relative
  (`clustering.py:166`), and a wall-clock ceiling would break
  `test_late_copies_use_publication_relative_window`, where two copies of a
  five-day-old story must still find each other. The rule is "this cluster's
  first article is more than N hours older than the article being placed", not
  "this cluster is old".
- That test must keep passing: the window is still computed relative to the
  *variant's* publication time, so a genuinely late syndicated copy of a
  five-day-old story still finds its siblings. What changes is that the
  **cluster** ages out on its own clock instead of being kept alive by traffic.
- Consequence, and it is intended: a story that runs for a week produces more
  than one card. Under the governing principle that is the correct trade, and
  brief 15's "Related stories" link is the planned repayment.
- **Verify.** A cluster whose `first_seen_at` is older than the window rejects a
  new variant even when `last_seen_at` is minutes old — this is the case with no
  coverage today. The 435-hour cluster is not reproducible.

## CM-6 — Test the entity path

`_cluster()` (`api/tests/test_clustering.py:57`) passes `entities=[]` to every
case in the file, so the 0.55-weight term that causes this bug has **no coverage
at all**. `test_unrelated_stories_do_not_merge` varies both the player and the
event type, and passes trivially.

- **Approach.** Extend the helper to seed real `Entity` rows and pass entity IDs,
  then add cases that hold entities and event type **constant** and vary only the
  topic. Keep the existing entity-free cases — they cover the entityless
  fallback, which is a real path.
- Required regression cases, all from production:
  - Celebrini card auction vs. pipeline rankings → **must not** merge.
  - Celebrini extension vs. "5 Restricted Free Agents Still Unsigned" → **must
    not** merge.
  - IIHF Player of the Year vs. "71 Days to Opening Day: Celebrini" → **must
    not** merge.
  - Two card-auction articles from different outlets → **must** merge.
  - Two Graf re-signing wire copies → **must** merge.
  - A cluster past `cluster_max_age_hours` with fresh activity → **must not**
    accept a new variant.
- Include at least one `game`-event pair so the 24h window and `game_identifier`
  route stay covered — the offseason feed does not exercise them.
- **Verify.** `pytest api/tests/test_clustering.py` green against Postgres; the
  three "must not merge" cases fail if CM-2 is reverted.

## CM-7 — Split the existing over-merged clusters

Without this the feed still shows the reported card after deploy: nothing
re-clusters historical variants.

- **Approach.** A `api/app/scripts/split_cluster.py` mirroring
  `merge_clusters.py` — move named variant IDs out of a cluster into a new one,
  recompute `entities_agg`, `tokens`, `source_count`, `first_seen_at`,
  `last_seen_at` and the headline via `select_cluster_headline()`, with
  `--dry-run`.
- Run it against the clusters in the baseline table, starting with 4152 (the
  reported card) and 4055 (116 variants).
- Note: `source_count` is incremented on join and never decremented after the
  30-day variant purge, so it over-reports badly — cluster 3820 claims 64 sources
  and holds 7 variants. Recompute it by query while splitting. The general fix is
  tracked as **R2-F4** and stays out of scope.
- **Verify.** `--dry-run` output matches intent before executing; after the
  split, `/api/cluster/4152` holds only the auction articles and the pipeline
  articles have their own cluster.

---

## Deploy notes

API + worker: `build api` then `up -d api worker beat`. Builds run ~40s–3min (see
`[[pi-deploy]]`).

Land CM-1 and let one ingest cycle run before deploying CM-2…CM-5, so the
decision log captures the current behaviour for comparison. Run CM-7 last, after
the gates are live, or the same clusters re-form.

## After this brief

- **Re-measure the cohesion table** a week after deploy, same method, and put the
  numbers in `RM-4`. Watch the count of clusters below 0.15 cohesion, the maximum
  cluster span, and — as the counter-metric — whether the Graf-style syndication
  clusters still form at full size. Repeat in-season; an offseason-only
  measurement is exactly what hid the RM-3 regression.
- **Read the CM-1 decision log** to attribute the remaining bad merges to
  specific routes. The syndication-UUID route (route 1, no content check at all)
  is the leading unexamined suspect.
- **Brief 15** — the durable fix: a `story_key` slug from the classifier's
  existing JSON response as the primary merge signal; "Related stories" links
  between near-miss clusters; an offline eval harness over labelled pairs;
  2–3 variant headlines surfaced inline on the card so a bad merge is visible
  without expanding it; and an alert when a cluster exceeds ~15 variants or
  ~120 hours.
- Cluster 4003 contains a non-hockey Edmonton Journal video ("Edmonton police to
  introduce involuntary detention detox"). Clustering is not why it is in the
  feed — that is **RM-2/RM-3**.
