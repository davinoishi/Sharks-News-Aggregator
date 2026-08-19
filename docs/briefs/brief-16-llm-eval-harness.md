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

## EV-2 — Freeze an eval corpus

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
