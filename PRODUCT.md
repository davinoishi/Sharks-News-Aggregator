# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: the builder himself.** Davin — a lifelong San Jose Sharks fan in San
Jose — built this to stop bouncing between social media, blogs, and news sites
to keep up. His own daily use is the product's reason to exist, and the measure
of whether it works.

**Secondary: other Sharks fans**, arriving mostly on phones, in short check-in
sessions: "what happened with the Sharks since I last looked?" They scan
headlines, recognize player and event names, and click through to the outlet
they already trust. Their use is welcome and designed for, but it does not
outrank the primary user's workflow or the low-maintenance requirement.

**Operator: a single admin (the builder).** Reviews source health, submitted
links, validation/LLM decisions, and BlueSky posting through `/admin`.

## Product Purpose

Consolidate San Jose Sharks news and rumors from 20+ RSS sources into one
fast-to-scan feed, so a fan can catch up in a minute instead of touring a
dozen sites. Articles covering the same story from different outlets are
grouped into one cluster; entities (players, coaches, teams), tags, and event
types are extracted so the feed can be filtered.

Success over the next year is **personal utility**: the builder reaches for it
daily and it keeps running without demanding attention. Audience growth is a
bonus, not a goal — future work should not trade away simplicity, speed, or low
operational cost to chase reach.

## Positioning

Not a news site and not a link dump: a **clustering** aggregator. The
differentiator is that duplicate coverage of one story collapses into a single
card with its sources attached, and that the same feed is published three ways
— web, [RSS](/rss), and BlueSky (`@sjsharks-news.bsky.social`) — so fans can
consume it wherever they already are.

Independent and unofficial. It does not create or break news, and does not
claim accuracy beyond the original sources.

## Operating Context

- **Device:** phones dominate. Sessions are short, frequent, and often
  one-handed. Desktop is a real but secondary case.
- **Hosting:** self-hosted on a Raspberry Pi 5 (`pi5-ai2`), published to the
  public internet through a noBGP tunnel. This is a hard performance ceiling,
  not a detail.
- **Reading flow:** scan the feed → optionally filter by tag, player, or time
  window (24h / 7d / 30d) → click a headline out to the source, or expand a
  cluster to choose among its sources.
- **Background rhythm:** RSS ingest every ~10 min, BlueSky posting every
  ~15 min, roster sync daily from CapWages, items purged after 30 days. The feed
  is therefore always partly fresh — "last scan" recency is user-visible
  information, not decoration.
- **Admin flow:** separate, `noindex`, single-operator, data-dense. It exists to
  diagnose ingestion and LLM behavior, not to be marketed.

## Capabilities and Constraints

**Confirmed capabilities**

- Clustered feed with keyset (cursor) pagination and a "Load more" control.
- Filtering by tag, by entity/player (searchable picker), and by time window;
  all filters mirrored into the URL so views are shareable and bookmarkable.
- Clickable headlines that go to the top-ranked source (official → press →
  other), with click recording; expanding a cluster reveals all variants.
- Public `/submit` page for reader-submitted links (SSRF-guarded).
- `/rss` feed of the aggregated clusters (RSS 2.0).
- `/about` and `/legal` pages; public site stats (visits, stories, sources).
- Single-operator `/admin` area: source health, submissions, validation logs,
  LLM report/health, BlueSky health/stats/posts.
- Enrichment via keyword matching with optional LLM (OpenRouter) relevance and
  classification; fails open to keywords on outage.

**Tag vocabulary** (product terminology, not decoration): Rumors, Trade,
Injury, Signing, Game, Lineup, Recall, Waiver, Prospect, Official, Barracuda.
**Event types:** trade, injury, lineup, game, general news/analysis.
**Entity types:** players (full org — NHL, AHL, unsigned reserves), coaches,
teams.

**Durable constraints — all future work must preserve these**

1. **Free, no ads.** No advertising, no paywall, no sponsored placement.
2. **No login to read.** The feed is fully readable with no account, no cookie
   wall, no gate. (Analytics are cookieless by existing design.)
3. **Link out, never host.** Headlines send readers to the original reporting;
   the site never reproduces full article text.
4. **Mobile-first, Pi-budget.** Phones are the primary device. It must stay fast
   on a Raspberry Pi 5 — no heavy client bundles, no expensive per-view render
   cost, no dependency that inflates the image build (the web image build is
   already the slowest part of deploying).

**Technical constraints**

- Next.js 14 App Router + TypeScript + Tailwind; the feed page is client-side.
- All backend calls go through Next.js proxy routes under `web/app/api/`; the
  FastAPI URL is never exposed to the browser.
- Backend: FastAPI, SQLAlchemy, PostgreSQL, Celery + Redis, Docker Compose.

**Undecided / open**

- Planned but not committed: user accounts and preferences, search, push
  notifications. Accounts, if ever built, must not become a condition of
  reading (constraint 2).

## Brand Commitments

- **Name:** Sharks News Aggregator (the crest reads "SHARKS NEWS").
- **Logo — binding, keep as-is.** `web/public/logo.png` (with favicon and
  Apple-touch variants) is an original illustrated crest: a headphoned shark
  over a newspaper on a shield, in teal, orange, near-black, and white. It is
  **not** the official San Jose Sharks club mark; its colors are team-adjacent,
  not the club's exact palette. The user has explicitly asked that this mark be
  kept unchanged.
- **UI colors and typography are open.** The user considers the current UI
  palette and fonts generic and has explicitly authorized changing them. The
  logo is the constraint; the interface around it is not.
- **Voice:** first-person, plain, fan-to-fan, unpretentious. Honest about
  limits (e.g. the site openly states it misses X/Twitter coverage because the
  API costs money). No hype, no manufactured urgency.
- **Required disclaimer:** independent and unofficial; not affiliated with the
  NHL or the San Jose Sharks. This must remain visible.

## Evidence on Hand

- **Live production site** with real data: https://x2mq74oetjlz.nobgp.com
- **Live BlueSky mirror:** `@sjsharks-news.bsky.social`
- **Real assets:** `Logos/` (source art), `web/public/` (logo + favicons).
- **Real copy:** `/about` (personal, first-person origin story) and `/legal`
  (terms + privacy) are written and approved — treat as factual content, not
  placeholder.
- **Real public stats:** visit count, stories tracked, source count, served
  from the API.
- **Real support links:** `linktr.ee/davinoishi`, `buymeacoffee.com/davinoishi`.
- **Product/engineering record:** `docs/` (ARCHITECTURE, MODELS, SETUP_GUIDE,
  IMPROVEMENT_PLAN), `docs/briefs/` (11 executed briefs including
  `brief-08-ux-round.md`, the last frontend UX pass), and
  `docs/original_specs/` including a wireframe (`sharks-wireframe.png`).
- **Absent — do not fabricate:** there are no testimonials, no named users, no
  traffic claims beyond the live counter, no press coverage, no pricing, no
  sponsors, no partnerships, and no team endorsement.

## Product Principles

1. **A minute, not a session.** The win is a fan getting caught up fast and
   leaving for the source. Time-on-site is not a goal; anything that slows the
   scan is a regression.
2. **One story, one card.** Clustering is the product. Duplicate coverage
   collapses; sources stay one tap away and attributed.
3. **Send readers to the source.** Credit and traffic belong to the outlets
   that did the reporting.
4. **Honest about what it is.** Unofficial, incomplete, unverified rumors
   labeled as such. State gaps rather than paper over them.
5. **Cheap to run, cheap to keep running.** It lives on a Pi maintained by one
   person. Simplicity is a feature; every addition must survive that budget.

## Accessibility & Inclusion

No formal external standard has been mandated, but the codebase carries an
established practice that future work should not regress: WCAG AA contrast for
tag chips (computed by luminance in `web/app/lib/tagColor.ts`),
`aria-expanded` on expand controls, visible focus-visible rings, keyboard-
navigable cards, and verified layout down to 360px width.
