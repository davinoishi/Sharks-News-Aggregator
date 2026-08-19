# Brief 15 — Story keys: the durable fix for RM-4

Plan item: **`RM-4`** (`docs/IMPROVEMENT_PLAN.md`). Tasks **SK-1 … SK-7**.
Follows [brief 14](brief-14-cluster-merge-precision.md), which must be deployed
and measured first.

**Ships as one PR.** API + worker + web. One prompt change, no new LLM calls.

## Task

Brief 14 blocks merges backed by *zero* content overlap. That kills the reported
card, but it cannot separate the genuinely hard pairs — "Celebrini's rookie card
sold for $1.28M" from "Celebrini tops the pipeline rankings" — because the words
those headlines share **are his name**. Lexical similarity has no answer here.

Give the matcher a semantic signal instead: a canonical topic slug produced by
the classifier that already runs on every article.

## Context

### Why lexical similarity cannot finish the job

Measured over real production pairs during brief 14 (headline token Jaccard with
entity-derived tokens removed):

| | `T_topic` range |
|---|---|
| Pairs that **should** merge | 0.077 – 0.667 |
| Pairs that **should not** | 0.000 – 0.125 |

The distributions touch. Brief 14's gate exploits only the fact that most bad
pairs sit at exactly 0.000; the survivor (Celebrini extension vs. "Cale Makar
Extension Questions Emerge", sharing the word "extension") is the shape of every
remaining failure. No threshold fixes it. A topic label does.

### The prompt is currently a cause, not a cure

`CLASSIFY_PROMPT_USER` (`api/app/services/openrouter.py:72`) instructs the model
to lead every summary with the subject's full name, *"so two stories about the
same person cluster together"*. RM-4 measured the effect: name-led summaries lift
`L` from 0.220 to 0.531 on the card-auction/pipeline pair — over the 0.62 bar —
and make `summary_name_match` fire outright.

**That instruction is load-bearing in the wrong direction, and a more capable
model would obey it more faithfully and merge more.** It exists to serve one real
case (a headline naming its subject only by role, covered by
`test_role_headline_merges_with_named_sibling_via_summary`). `story_key` serves
that case better, which is what finally makes the instruction removable — see
SK-3.

### Decisions already taken — do not re-litigate

- **No second LLM call.** `story_key` is one more field in the JSON the
  classifier already returns. Adding a per-candidate-pair adjudication call to
  the enrich task is not an acceptable substitute — it multiplies calls by
  candidate count on exactly the busiest stories.
- **`story_key` corroborates; it does not become a new bypass.** RM-4 exists
  because single signals were allowed to carry merges alone. A matching
  `story_key` must still pass the brief 14 evidence gate. Do not add a
  `story_key`-only fast path.
- **Do not change the model in this brief.** Tempting, and RM-4 shows why it
  would confound the measurement. Model selection is brief 16.
- **Do not remove brief 14's gates.** `story_key` is an additional signal, not a
  replacement. If it regresses, the gates are what keep the feed sane.
- **Slugs are compared, never trusted as identifiers.** The model will emit
  near-misses (`celebrini-card-auction` vs `celebrini-rookie-card-auction`).
  Compare with token overlap, not equality — see SK-2.

---

## Execution status (2026-08-19)

**Shipped: SK-1, SK-2, SK-5, SK-6, SK-7.** Deferred: SK-3 and SK-4, both for
reasons the brief itself gives.

**SK-3 is deferred by this brief's own instruction.** It says *"Do this last,
behind the SK-2 measurement"* — and that measurement needs `story_key` to have
run in production against real articles. On the day SK-1 deploys, every existing
cluster has no key and every comparison takes the "unknown" fallback, so there is
nothing to measure yet. Retiring the name-leading instruction before then would
re-break the role-headline case while the replacement signal is still unproven.
Revisit once the decision log shows `key=agree`/`key=differ` firing on real
traffic.

**SK-4 is deferred as too large for this PR.** Related-stories links need a new
table, a migration, relation recording in the matcher, an API field and a web
surface — a second schema change and a new UI concept on top of a PR that already
carries one migration plus API, worker and web changes. It is the repayment for
over-splitting, so it should not be dropped; it wants its own pass.

Note the practical consequence of deferring both: **brief 14's accepted
regression is still live.** The role-headline case still splits, and there is no
"Related stories" link yet to soften a split. `story_key` is what fixes it, and
only once clusters have accumulated keys.

---

## SK-1 — Emit `story_key` from the classifier

- **Approach.** Add `story_key` to `CLASSIFY_PROMPT_USER`'s JSON contract and to
  the parsed result in `api/app/services/openrouter.py`: a lowercase
  hyphenated slug, 2–5 tokens, naming **the event, not the subject** — e.g.
  `celebrini-rookie-card-auction`, `sharks-pipeline-ranking-2026`,
  `graf-contract-extension`.
- Instruct explicitly: *two articles covering the same event must produce the
  same key; two articles about the same person covering different events must
  not.* Give one worked contrast in the prompt using the card-auction/pipeline
  pair — it is the canonical failure and the model should see it.
- Persist on `StoryVariant.extra_metadata` alongside `llm_summary`, and on
  `Cluster` next to `llm_summary`. Backfill a missing cluster key the same way
  `update_cluster_metadata()` already backfills `llm_summary`, so an early LLM
  failure does not permanently blind the cluster.
- Cap the stored length as `llm_summary` is capped (`summary[:100]`), and
  normalise: lowercase, strip anything not `[a-z0-9-]`, collapse repeats.
- **Verify.** A contract test asserting the parser tolerates a missing or
  malformed `story_key` (older rows and LLM failures must not raise) — the
  keyword fallback path has no key at all and must keep working.

## SK-2 — Make `story_key` the primary merge signal

- **Approach.** Add `story_key` agreement as the highest-weighted signal in
  `calculate_similarity_score()`, above entity overlap. Compare keys by token
  Jaccard over hyphen-split parts, not string equality.
- **Both directions matter.** A strong key match should let a merge through that
  lexical evidence alone would miss; a strong key *mismatch* between two
  otherwise-similar articles should block one. The second half is the RM-4 fix —
  same player, same event type, different keys must not merge.
- The brief 14 evidence gate still applies. A key match satisfies it (it is
  positive topical evidence); a key mismatch does not override it.
- Rebalance the weights in one place with the existing `llm_signal` branches, and
  **record the old and new weight sets in the PR description** — this function
  has been tuned repeatedly and the history is not otherwise recoverable.
- Where either side lacks a key (LLM failure, pre-deploy rows), fall back to the
  brief 14 behaviour exactly. No key must never be treated as a mismatch — that
  is the same "missing data as evidence" bug `calculate_similarity_score()`
  already documents in its docstring.
- **Verify.** The full brief 14 regression set still passes, plus: same person +
  same event type + different `story_key` → no merge; different headlines +
  matching `story_key` → merge.

## SK-3 — Retire the name-leading summary instruction

- **Approach.** Once `story_key` carries story identity, change the summary
  instruction to describe the **event** rather than lead with the person, and
  gate or delete `summary_name_match` accordingly (brief 14 already requires
  `L >= summary_evidence_threshold` on it).
- **Do this last, behind the SK-2 measurement.** The instruction is currently the
  only thing that makes the role-headline case work; removing it before
  `story_key` is proven re-breaks a case that has a passing test.
- **Verify.** `test_role_headline_merges_with_named_sibling_via_summary` and
  `test_summary_bridge_keeps_different_people_apart` both still pass, now via
  `story_key` rather than via the name.

## SK-4 — "Related stories" between near-miss clusters

Repays the cost of brief 14's and brief 15's deliberate over-splitting.

- **Approach.** When a variant's best candidate scores above a *relation*
  threshold but below the merge bar, record the cluster pair as related rather
  than discarding the comparison. Surface up to ~3 related clusters on the card.
- This is what makes aggressive splitting safe: the reader still reaches the
  other story, and a duplicate card stops being a dead end.
- Keep it directional-agnostic and deduplicated; do not let a hub cluster
  accumulate unbounded relations.
- **Verify.** The card-auction and pipeline clusters — split by brief 14 — appear
  as related to each other.

## SK-5 — Surface variant headlines on the card

**The cheapest real safety net in either brief, and it protects against whatever
the matcher still gets wrong.**

- **Approach.** Show 2–3 variant headlines (or "+N other headlines") inline on
  `ClusterCard` without expanding. Today every variant title is hidden behind
  "View sources" (`web/app/components/ClusterCard.tsx:146`), which is precisely
  why the reported mis-merge cost the reader the story.
- Respect the existing card density — this is a preview, not the expanded list.
  Skip it for single-variant clusters.
- **Verify.** Server-rendered HTML contains the preview headlines (they must be
  crawlable, per briefs 12–13); the expanded view is unchanged.

## SK-6 — Alert on cluster shape anomalies

- **Approach.** Extend the existing pipeline-health checks
  (`api/app/core/health_checks.py`) with a warning when any active cluster
  exceeds ~15 variants or ~120 hours from `first_seen_at` to `last_seen_at`.
- Wire it to the existing webhook alert path used by the other health checks.
- Every one of RM-4's mega-clusters would have fired this weeks before a reader
  had to report one.
- **Verify.** A seeded oversized cluster raises the warning; normal clusters do
  not.

## SK-7 — Pair-eval harness

- **Approach.** A script that takes a labelled set of (variant A, variant B,
  should_merge) pairs and reports merge **precision and recall separately**,
  plus which route decided each pair (using brief 14's CM-1 instrumentation).
- Seed it from the pairs already collected in RM-4 and brief 14, and from the
  clusters CM-7 splits — those are labelled by construction.
- **Precision and recall must be reported separately.** A single accuracy number
  hides exactly the trade this work is making, and reporting one number is how
  the RM-3 regression stayed invisible for a month
  (`[[relevance-change-seasonal-measurement]]`).
- **Freeze the corpus to a file in the repo.** `run_purge_old_items` deletes
  `raw_items` after 30 days; an eval set that reads live data silently changes
  under you.
- **Verify.** The harness reproduces brief 14's reported 7-of-8 / 1-of-7 result
  on the pairs from that brief.

---

## Deploy notes

API + worker + web. Land SK-1 and let it run one cycle so clusters accumulate
keys before SK-2 starts depending on them — on day one every existing cluster has
no `story_key` and will take the brief 14 fallback path, which is correct but
means the change appears to do nothing at first.

## After this brief

- **Re-measure the cohesion table** (method in brief 14) and compare against both
  the pre-brief-14 baseline and the post-brief-14 numbers. Three points is enough
  to tell a fix from a regression; two is not.
- **Repeat in-season.** Everything measured so far is offseason. Game-day
  clustering is barely exercised in August.
- **Brief 16** — the LLM replay harness and model bake-off. RM-4 concluded model
  capability is not the bottleneck for clustering or relevance, but `story_key`
  and `low_value` are the two jobs where it plausibly is, and SK-7's harness is
  what makes that measurable.
