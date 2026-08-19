# Eval sets

## `pairs.seed.jsonl` — hand-labelled clustering pairs

19 variant pairs with human `should_merge` labels, drawn from the production
clusters measured for `RM-4` on 2026-08-19. Ground truth for brief 15's SK-7
pair-eval harness and for brief 16's `story_key` comparison.

Each record carries `provenance` naming the cluster it came from. Two are worth
knowing about specifically:

- *"3 Cards to Watch at Goldin"* vs *"Card Auction Nears $500K"* — labelled
  `true`, and brief 14 knowingly loses it ("card"/"cards" do not match without
  stemming). It is in here so the loss stays visible rather than being quietly
  accepted.
- *"Celebrini, Misa make Sharks clear No. 1"* vs *"Sharks are No. 1 in NHL
  Pipeline Rankings"* — labelled `true`, and production has these on **different
  cards** (4152 and 4188). Over-merging causes under-merging; this pair is the
  recall side of RM-4.

## Frozen corpora

`python -m app.scripts.freeze_eval_corpus` writes a stratified snapshot of
`raw_items` plus candidate pairs. **Run it regularly** — `run_purge_old_items`
deletes `raw_items` after 30 days, so an unfrozen corpus stops existing.

Output is gitignored: it is bulk third-party article text, and R3-A1 tracks
keeping data dumps out of the repo. Store it with the backups (R3-O1).

Labels the script emits are `derived` — they record what production did, and
production is what is under test. Verify by hand and set `label_source` to
`human`.
