# Brief 17 — X/Twitter ingest via twitterapi.io

Plan item: **`XI-1`** (supersedes the transport half of **`RM-1`**).
Tasks **XI-1 … XI-6**.

**Ships as one PR.** New ingest method + config + sources. This is the first
brief that adds a *paid* external dependency to the ingest path, so the cost
controls in `XI-4` are part of the deliverable, not a follow-up.

## Task

`IngestMethod.TWITTER` exists in the enum and one source is seeded against it
(`San Jose Sharks PR`, `https://x.com/SanJoseSharksPR`), but
[`ingest_api`](../../api/app/tasks/ingest.py) is a stub that calls
`_mark_source_unimplemented` — the source is held at `UNSUPPORTED` and never
scheduled. X has been unreachable for this project since the official API was
ruled out on cost.

Implement X ingest against [twitterapi.io](https://twitterapi.io), a third-party
reseller, for the insider accounts that have **no** Bluesky mirror and no
Threads-free alternative.

## Context

### Why this and not the official X API

The official API was rejected on price and that has not changed. twitterapi.io
is pay-as-you-go at $0.15 per 1,000 tweets with no monthly minimum, no developer
approval, and no contract. The projected bill for this brief's full scope is
**under $5/month**. Cost is not a constraint here; the constraints are fragility
and scope creep.

### The pricing model — verified 2026-09-04

| Item | Cost |
|---|---|
| Credits | 100,000 credits = $1.00 |
| Tweets | $0.15 / 1,000 = **$0.00015 per tweet returned** |
| User profiles | $0.18 / 1,000 |
| Minimum charge per API call | $0.00015 (15 credits) — an empty result still costs this |
| Webhook filter rule, hourly interval | $0.09/month per rule + $0.00015 per matched tweet |
| Free signup credit | $0.10, no card required |

**Billing is per tweet returned, not per call.** An hourly poll that returns five
posts costs 5 × $0.00015 = $0.00075. A poll that returns nothing costs the
$0.00015 floor.

Not verified: the minimum top-up/recharge amount. Check it before funding the
account — it does not change the design, only the first invoice.

### Endpoint choice is the whole cost story — do not get this wrong

- **`get_user_last_tweets` is the wrong endpoint.** It has no `since` filter and
  returns up to 20 tweets per page every call, so you pay for 20 tweets an hour
  per account whether or not any are new: **$2.16/month per account**, almost
  all of it duplicates you already have. twitterapi.io's own docs warn that
  polling this endpoint per-user "will cost you a lot."
- **`tweet_advanced_search` is the right endpoint.** It supports `from:`, `OR`,
  and `since_time:` / `until_time:` as **Unix seconds**. Note that `since:` /
  `until:` with date strings (`2021-12-31_23:59:59_UTC`) are documented as *not
  supported* — use the epoch forms. `queryType=Latest`. 20 results per page with
  cursor pagination.

With `since_time` bookkeeping you only ever pay for genuinely new posts, and one
query can cover every tracked account at once:

```
from:SanJoseSharksPR OR from:PierreVLeBrun OR from:kevweekes since_time:<last_poll_epoch>
```

### Projected spend

Beat runs `ingest-all-sources` every 10 minutes, not hourly, so the empty-call
floor is 6/hour not 1/hour. That floor is the only thing polling frequency
changes — tweet volume is the same at any interval.

- Empty-call floor, one combined query at 10-minute cadence: 4,320 calls/month ×
  $0.00015 = **$0.65/month**
- Tweet volume, ~10 insider accounts in season at ~400 tweets/day total: 12,000
  tweets/month × $0.00015 = **$1.80/month**
- **In-season total ≈ $2.50/month. Offseason ≈ $0.75/month.**
- Pessimistic bound — 10 accounts at 200 tweets/day each, 60,000/month — is
  **$9/month.**

Per-account polling of the same 10 accounts on `get_user_last_tweets` would be
~$21.60/month for strictly worse data. That is the ~10× the batching design buys.

### The off-topic posts are not a cost problem

You pay for every tweet retrieved, relevant or not. At $0.00015 each, 90% waste
on a $2.50 bill is $2.25 wasted. Irrelevance here is a *filtering* problem.

The line item that actually scales with noise is downstream:
[`enrich.py:163`](../../api/app/tasks/enrich.py) runs the relevance gate before
the LLM classifier, which is correct — but when `llm_relevance_enabled` is on,
[`validate_sharks_relevance`](../../api/app/enrichment/classify.py) itself calls
the LLM on **every** item. 400 league-wide tweets a day is ~12,000 extra
flash-lite calls a month. On the current model that is still under a dollar, so
it does not change the decision — but see `XI-5`.

### What already covers this ground — do not duplicate it

Sources 30–32 are Bluesky mirror bots (`notfriedgehnic`, `notpierrevlebrun`,
`notfrankseravalli`) on plain `bsky.app/profile/<handle>/rss` feeds. **Friedman,
LeBrun and Seravalli are already covered, for free.** Adding them here spends
money to duplicate rows the deduper will then have to reconcile.

`RM-1` (Threads via self-hosted RSSHub, deferred 2026-07-19) exists to reach
Kevin Weekes, who has no Bluesky presence. If Weekes is reachable on X — check —
this brief solves RM-1's problem without running an RSSHub container on the Pi,
and RM-1 should be closed as superseded rather than left open in parallel.

### Fragility — set expectations honestly

twitterapi.io is a scraper. It self-describes as "an independent third-party
service. Not affiliated with X Corp," and bypasses X's approval process. It
claims 99.99% uptime and sub-second firehose latency, with no published SLA.
This is the same fragility class as rss.app / Nitter / RSSHub, already documented
under RM-1. Assume it can degrade or disappear. The brief-09 health check
flagging the source as broken is the desired signal, not a bug.

---

## XI-1 — Client for twitterapi.io

- **Approach.** A service module alongside `app/services/`, not inline in the
  task. One function: given a list of handles and a `since_time` epoch, return
  normalised post records. Cursor pagination handled internally.
- Key from settings (`twitterapi_key`), following the `openrouter_api_key`
  pattern in `app/core/config.py`. Absent key ⇒ the ingest method is disabled and
  the sources are held out of scheduling, **not** an error loop.
- **Verify first, against the $0.10 free credit, before writing the client:**
  that a query chaining several `from:` clauses with `OR` actually returns posts
  from all of them. The docs confirm `from:` and confirm `OR`, but do **not**
  document chaining multiple `from:` terms in one query. If it does not work, the
  fallback is one query per account — same per-tweet cost, ~10× the empty-call
  floor ($6.50/month rather than $0.65), still affordable. Write down which one
  you confirmed.
- **Verify.** A live call returns posts for a known-recent handle; a bogus handle
  and a bad key each fail with a clear message rather than a silent empty result.

## XI-2 — Batched fetch that preserves per-source attribution

This is the one real architectural decision in the brief.

- **The tension.** `ingest_all_sources` fans out one `ingest_source.delay(id)`
  per Source row. A combined `from:a OR from:b` query does not fit that shape —
  it is one call covering N sources.
- **Do not collapse the accounts into a single "X insiders" Source row.** It is
  the cheap fix and it destroys per-source attribution, per-source health, the
  `source_signal` ranking, and the ability to retire one account.
- **Approach.** Keep one Source row per account (`ingest_method=twitter`,
  `base_url=https://x.com/<handle>`, handle in `extra_metadata`). Add a separate
  batching task that collects all active `twitter` sources, issues one combined
  query, and routes each returned tweet to the Source row matching its author.
  Exclude `twitter` sources from the per-source fan-out so they are not fetched
  twice.
- Track `since_time` per source, not globally — a source added mid-cycle must not
  inherit another source's watermark, and a source that errors must not advance
  it. Persist it in `extra_metadata` or a dedicated column; do not derive it from
  `last_fetched_at`, which is a fetch record, not a data watermark.
- **Verify.** Two accounts posting in the same window produce raw_items on two
  different `source_id`s from a single upstream call. Killing the worker
  mid-cycle does not lose or re-bill a window.

## XI-3 — Map tweets onto `raw_items`

- **Approach.** `canonical_url` = `https://x.com/<handle>/status/<tweet_id>` —
  stable and unique, which is what the `source_id:canonical_url:raw_title` content
  hash in `create_raw_item` needs. Set `source_item_id` to the tweet id.
- Tweets have no title. Reuse
  [`derive_title_from_description`](../../api/app/tasks/ingest.py) rather than
  writing a second derivation.
- **Decide and document: a tweet that only links to an article.** Ingest the
  tweet as its own item (an insider's post *is* the news for breaking content),
  and let the existing clusterer merge it with the article when the article
  arrives from its own feed. Do not follow the link and ingest the target — that
  is a second ingest path hiding inside this one.
- `verify_age` stays False (it is an RSS-only cross-check). `published_at` comes
  from the tweet's own creation time.
- **Verify.** The same tweet seen in two consecutive cycles creates one row. A
  tweet lands on a card with a readable title and a working link.

## XI-4 — Cost controls in the code, not in a runbook

- **Approach.** A hard per-cycle cap on tweets retrieved (setting, default
  generous — say 500). Hitting it logs loudly and stops paginating; it does not
  silently truncate and advance the watermark.
- Count tweets retrieved into the existing site-metrics table so spend is
  observable from the app rather than only from the vendor dashboard.
- A kill switch: one setting that disables X ingest entirely without a deploy.
- **Why this is in scope.** Every other ingest failure mode in this codebase is
  free. This one bills. A pagination bug that loops is a bill, and the first
  thing anyone will want is the ability to turn it off from the Pi at 11pm.
- **Verify.** With the cap set to 1, a busy window retrieves one tweet, logs the
  cap, and leaves the watermark where it can resume without a gap.

## XI-5 — Relevance settings per source

- **Approach.** League-wide insider accounts get the relevance check **ON** — a
  low accept ratio is expected and correct, exactly as documented for the Bluesky
  mirrors. `@SanJoseSharksPR` is team-dedicated and is the candidate for
  `skip_relevance_check` in `extra_metadata`.
- Consider a cheap pre-gate for X-sourced items: drop anything matching no NHL
  entity *before* `validate_sharks_relevance` reaches the LLM. Optional — the
  measured cost is under a dollar a month — but it is the only thing in the
  pipeline that scales linearly with X noise, and it is a few lines.
- **Do not** retune the relevance filter itself in this PR. See
  `[[relevance-change-seasonal-measurement]]`: a filter change measured only in
  the offseason cost 28 real stories a month. Any tuning is its own brief with
  its own in-season measurement.
- **Verify.** A rugby "Sharks" tweet and an Oilers-only tweet are both dropped; a
  Sharks trade tweet is kept. Check the `validation_logs` rows, not just the feed.

## XI-6 — Pick the accounts

- **Approach.** Only accounts with no free equivalent. Confirmed *not* candidates:
  Friedman, LeBrun, Seravalli (sources 30–32 already mirror them on Bluesky).
- Candidates to check: `@SanJoseSharksPR` (already seeded), Kevin Weekes, Chris
  Johnston, Darren Dreger — the same list RM-1 assembled, since the reason they
  were on it (no Bluesky presence) is unchanged.
- Start with **three or four**, not ten. The cost model holds either way; the
  reason to start small is that every added account is more league-wide noise
  through the relevance gate, and you want to see the accept ratio before scaling.
- **Verify.** Each added account has a one-line note in the source row saying why
  it is not already covered by a Bluesky mirror.

---

## Out of scope

- Any change to relevance scoring, clustering, or the LLM prompts.
- The webhook / filter-rule delivery mode. It is $0.09/month per rule at hourly
  interval and pushes rather than polls, which is cheaper on the empty-call floor
  — but it needs public ingress through the noBGP tunnel and does not fit the
  Celery Beat model. Revisit only if polling latency turns out to matter.
- Backfilling history. `since_time` starts at deploy.
- Reddit and HTML ingest, which share the `_mark_source_unimplemented` stub.

## Deploy notes

- `TWITTERAPI_KEY` into the Pi `.env` — same handling as `OPENROUTER_MODEL`, see
  `[[openrouter-model]]`: the Pi `.env` is the source of truth, not the code
  default.
- The seeded `San Jose Sharks PR` source is at `UNSUPPORTED` and
  `get_active_sources` excludes it. Flipping it back to `APPROVED` is a data
  change, not a migration — do it deliberately and only once the client is
  verified live, or the first cycle after deploy bills against an untested path.
- Fund the account with the smallest allowed top-up. Watch the vendor dashboard
  for the first 48 hours against the `XI-4` metric; if the two disagree, the code
  is wrong about what it is being charged for.

## After this brief

- **Close `RM-1` as superseded** if Weekes is reachable here. Leaving both open
  invites someone to build the RSSHub container for a problem already solved.
- Re-measure the accept ratio on the X sources in season. The offseason ratio
  tells you nothing — that is the `[[relevance-change-seasonal-measurement]]`
  lesson, and it applies to a new source as much as to a filter change.
- If spend or noise turns out worse than projected, the next lever is narrowing
  the query with keywords (`(Sharks OR "San Jose") from:...`) so you stop paying
  to retrieve posts you were always going to drop. Cheaper, but it will silently
  miss a trade tweet that names neither — measure before adopting.
