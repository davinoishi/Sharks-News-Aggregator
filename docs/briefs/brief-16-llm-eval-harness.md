# Brief 16 — LLM replay harness and model bake-off

Plan items: **`RM-4`** (model-selection section), **`RM-2`**, **`RM-3`**.
Tasks **EV-1 … EV-5**.

**Ships as one PR.** Tooling and one migration — no change to pipeline behaviour.
Nothing here alters what the feed shows; it makes model and prompt changes
*measurable*.

## Task

Production runs `google/gemini-2.5-flash-lite`, chosen on price. RM-4 measured
whether a stronger model would fix clustering (no — see below), but three
questions remain open and unanswerable today:

1. Would a stronger model improve `low_value` detection?
2. Would it produce better `story_key` slugs (brief 15)?
3. Does the RM-2 roster-grounding prompt change actually work?

All three are empirical. None can be answered because there is no way to run a
candidate model over a fixed set of articles and compare.

## Context

### What RM-4 already settled — do not redo it

- **Clustering:** a stronger model is neutral-to-negative. The merge is
  overdetermined, and the name-leading prompt instruction means better
  instruction-following produces *more* over-merging. Measured, in `RM-4`.
- **Relevance:** the LLM's errors are stale-roster errors ("Darnell Nurse is an
  Edmonton Oilers player"), not reasoning errors. No model knows about a trade
  made weeks ago. Grounding fixes it; capability does not.

**The remaining candidates are `low_value` and `story_key`** — both pure judgment
over supplied text, needing no external knowledge. Scope the bake-off to those
two and to the RM-2 prompt change. Measuring relevance-as-such again is repeating
work already done.

### Cost is not the constraint

Projected in-season (~6M input, ~0.35M output per month): ~$1 on the current
model, ~$8 on Haiku 4.5, ~$23 on Sonnet 5, ~$39 on Opus 5. The whole decision
space is under $40/month. **Select on accuracy.** Verify current pricing on
OpenRouter live before quoting these — see `[[openrouter-model]]`, and note some
slugs 404.

### Two prerequisites, both already known

- **`validation_logs.llm_response` is `String(100)`** and truncates the stored
  JSON, so verdicts have to be recovered with a `LIKE '%"relevant": true%'`
  prefix hack (noted under RM-2). Widen it or store the verdict as its own
  column, or every future analysis pays the same tax.
- **`run_purge_old_items` deletes `raw_items` after 30 days.** A corpus that is
  not frozen to a file ceases to exist. **An in-season corpus cannot be captured
  until October** — freeze the offseason one now regardless, because the
  offseason/in-season comparison is the whole point of
  `[[relevance-change-seasonal-measurement]]`.

---

## EV-1 — Widen the validation log

- **Approach.** Alembic migration: `validation_logs.llm_response` to `Text`, and
  add a nullable boolean for the parsed verdict so the common query is ordinary
  SQL rather than a `LIKE` on truncated JSON.
- Backfill what is recoverable from existing rows; leave the rest null rather
  than guessing.
- **Verify.** Existing rows still read; a new row round-trips a full JSON
  response; `alembic downgrade` works.

## EV-2 — Freeze an eval corpus ✅ shipped early with brief 14

> **Shipped ahead of this brief (2026-08-19), on purpose.** The 30-day purge was
> deleting the corpus daily, and capture is the only time-sensitive part of this
> brief — labelling can happen whenever. Delivered:
> `api/app/scripts/freeze_eval_corpus.py` (stratified snapshot + candidate
> pairs), `api/eval/pairs.seed.jsonl` (19 hand-labelled clustering pairs from
> the RM-4 measurement), and `api/eval/README.md`.
>
> **Run on the Pi 2026-08-19.** 615 items — `accepted` 150, `rejected` 150,
> `llm_compared` 150, `clustered` 150, `low_value_suspect` 15 (all that exist in
> retained data) — plus 400 unlabelled candidate pairs. Covers published dates
> **2026-07-17 → 2026-08-13**. Stored at `eval_corpus/` on the Pi and copied
> into `backups/`; not in git (R3-A1).
>
> ⚠️ **The corpus straddles a model switch — do not analyse it as one
> population.** `llm_model` shows two models, with a clean boundary:
>
> | Model | Range | n |
> |---|---|---|
> | `google/gemma-4-26b-a4b-it` | 2026-07-17 → 07-24 | 309 |
> | `google/gemini-2.5-flash-lite` | 2026-07-23 → 08-13 | 278 |
>
> Any keyword-vs-LLM rate computed across the whole window silently averages two
> models. **Split on `llm_model` in EV-4.**
>
> **This is NOT A/B data — corrected 2026-08-19.** An earlier note here claimed
> it was. Checked against the database: `raw_items scored by >1 distinct model:
> **0**`. The models ran in *sequence*, so the two groups are different articles
> from different news weeks, and any difference between them confounds model with
> news period. The observed rates are close but not comparably so — gemini
> 323/1,592 keyword-rejected-but-LLM-relevant (20.3%), gemma 68/309 (22.0%).
> Nothing about the bake-off is already answered. **EV-3 is what creates a real
> A/B**, by replaying one frozen corpus through both models.
>
> **Still to do here:** a human labelling pass over the derived labels, and
> re-freezing in November for the in-season comparison. Everything below
> describes what was built; treat it as the record, not as pending work.

- **Approach.** A script that snapshots N `raw_items` (title, description, source
  category, existing entity IDs) to a versioned file in the repo, before the
  purge takes them.
- Sample deliberately, not just recent-first: include the low-cohesion clusters
  from RM-4, the off-team examples from RM-2, the two keyword false positives
  RM-2 caught ("AEW Forbidden Door", the hashtag-only YouTube description), and
  ordinary accepted articles as controls. A corpus of only hard cases measures
  the wrong thing.
- **Label it.** Unlabelled data cannot answer any of the three questions. Labels
  needed per item: relevant y/n, `low_value` y/n, and — for pairs — should_merge.
  Reuse brief 15's SK-7 pair format rather than inventing a second one.
- **Verify.** The corpus loads without a database; regenerating it from the same
  inputs is deterministic.

## Readiness assessment (2026-08-19) — read before starting this brief

Measured against the frozen corpus. **Roughly two thirds of this brief is
unblocked; the scoring half is not**, for three independent reasons.

| Task | Ready | Blocker |
|---|---|---|
| EV-1 widen `llm_response` | yes | — |
| EV-2 freeze corpus | **done** | — |
| EV-3 replay harness | yes | — |
| EV-4 precision/recall | **no** | no labels; `low_value` under-powered; `story_key` absent |
| EV-5 bake off + decide | **no** | depends on EV-4 |

**1. There are zero human labels.** `label_source == "human"` is 0 of 615. Every
label is `derived` — it records what production did, which is what is under
test — so scoring a candidate against them measures *agreement with the current
model*, not correctness. That is the one thing this brief must not do. The input
side is fine: 611 of 615 items carry both title and description, so replay works.

**EV-1 is future-proofing, not an unblock.** 577 of 581 stored responses are
already truncated at 100 chars and widening the column does not retrieve them —
but all 581 remain prefix-recoverable for the relevance verdict, which is what
the analysis needs. Widen it so *future* rows are clean; do not expect to
recover the past.

**2. `low_value` cannot be measured, and most of its ground truth is already
destroyed.** Only **15 positives** exist in the corpus — too few for precision
and recall, where one or two flips is the whole signal. The larger population is
unrecoverable: `is_scoreboard_stub` in `api/app/tasks/ingest.py:347` skips
schedule and scoreboard stubs **before a `raw_item` row is created**, so only a
counter survives them.

This is load-bearing for the brief's premise. RM-4 named `low_value` as one of
the two places model capability plausibly pays, so **the headline question is
currently unanswerable**, and re-freezing does not help. It needs a code change
to start persisting ingest-time rejects before the data to measure against
exists at all. That change is urgent for the same reason EV-2 was: every day it
is not in, more ground truth is discarded permanently.

**3. `story_key` does not exist.** EV-4 wants story-key agreement on
known-same/known-different pairs; that field ships in brief 15. A third of EV-4
is unreachable until then.

### Suggested split

- **Doable now:** EV-1, EV-3, plus persisting ingest-time stub rejections.
- **Then:** a labelling pass, most usefully over a stratified subsample (~200)
  rather than all 615. If an LLM produces the first pass, **write that into the
  method**: models scored against LLM-authored labels are partly measured on
  agreement with that LLM. Disclosed and spot-checked by a human it is a normal
  approach; discovered afterwards it invalidates the result.
- **After brief 15:** the `story_key` half of EV-4, then EV-5.

---

## EV-3 — Replay harness

- **Approach.** Run the frozen corpus through the existing prompt functions
  against an arbitrary OpenRouter model slug, and write per-item results to a
  comparable output. Same inputs, N models, side by side.
- Reuse the real prompt builders in `api/app/services/openrouter.py` — a harness
  with its own copy of the prompt measures the wrong prompt within one PR.
- Take the model slug as an argument. Validate it against OpenRouter before the
  run rather than discovering a 404 halfway through a paid sweep.
- Cache responses on disk keyed by (model, item, prompt hash) so re-running the
  analysis does not re-run the spend.
- **Verify.** Two runs of the same model over the same corpus agree; a bad slug
  fails immediately with a clear message.

## EV-4 — Report precision and recall, separately, per task

- **Approach.** For each model: `low_value` precision/recall, relevance
  precision/recall, and `story_key` agreement on known-same and known-different
  pairs. Never a single blended accuracy number.
- Include the current production model as the baseline column in every table, and
  report estimated cost per 1,000 articles alongside the quality numbers so the
  trade is visible in one place.
- **This is the RM-3 lesson.** That change looked fine on one metric in one
  window and cost 28 real stories a month. A number that cannot regress
  invisibly is the entire deliverable.
- **Verify.** The report reproduces the current model's known behaviour on the
  RM-2 examples — if it does not, the harness is wrong, not the model.

## EV-5 — Bake off and write down the decision

- **Approach.** Run the current model, Haiku 4.5 and Sonnet 5 over the corpus.
  Record the result in `RM-4`'s model section — **including if the answer is "no
  change"**, which is a real finding and stops the question being reopened every
  few months.
- Test the RM-2 roster-grounding prompt on the same corpus while the harness is
  warm. It is the highest-ceiling change identified so far and it costs nothing
  extra to evaluate here.
- If a model change is adopted, change **one thing at a time** — model or prompt,
  never both — or the next regression is unattributable.
- **Verify.** The decision, the numbers behind it, and the date are in the plan
  document, not only in a PR description.

---

## Deploy notes

EV-1 is a migration: `alembic upgrade head` on the Pi, then `up -d api worker`.
EV-2 … EV-5 are offline tooling and need no deploy — but **EV-2 is
time-sensitive**, because the 30-day purge is deleting the corpus daily.

## After this brief

- Re-freeze a corpus in November for the in-season comparison. The offseason
  numbers alone are exactly the trap RM-3 fell into.
- If the bake-off says a stronger model helps `story_key`, consider a split
  configuration — cheap model for relevance (where RM-4 showed capability does
  not help), stronger model for classification. `openrouter_model` is a single
  setting today; splitting it is a small change with a real payoff.
- Confirm the LLM-outage alert actually pages before October. Relevance **fails
  open** by design, which is a mild noise problem in the offseason and a feed
  full of junk on a game night at 10× volume.
