# Making of Sharks News

The running story of this project: what got decided, what got tested, and what turned out
to be wrong. Appended to after every working session. Newest entry at the bottom. Rules:
`CLAUDE.md` in the Projects-AI root.

The point of this file is the wrong turns. README.md says where things landed; this is
the record of how, so a decision doesn't get re-litigated in six months because nobody
remembers why it went the way it did.

---

## Session 1 — 8 Oct 2026: the file starts

Created in the Projects-AI making-of review, which found this project had no making-of.
Nothing in the project itself changed in that session.

**Before this file:** 206 commits from 21 Jan 2026 in git log, and `docs/IMPROVEMENT_PLAN.md` with its archive, which hold the numbered briefs and the superseded plans (RM-1, the RSSHub route, gave way to brief 17 on 4 Sep 2026).

## Session 2 — 8 Oct 2026: Google Search Console verification file

Davin got the HTML-file verification method from Search Console for
`https://wplepla23gjn.nobgp.link/` and dropped `google68323acf17ad7172.html` in the
Projects-AI root. It went into `web/public/`, which Next.js serves at the site root.

**Checked before adding, not assumed:** `web/middleware.ts` matches only `/admin/:path*`
and `/api/admin/:path*`, so the file isn't behind Basic auth. `next.config.js` puts
`Cache-Control: no-cache, no-store, must-revalidate` on it (it isn't in the exclusion
list), which is harmless for a file Google fetches once per check. The web Dockerfile does
`COPY . .` before `npm run build`, so the file only reaches production through an image
rebuild, not a restart.

**Committed to GitHub** on purpose: the file is public at a URL anyway and carries no
secret, and keeping it in the repo means a rebuild from `main` can't drop it and silently
unverify the property.

**Deploy — WRONG PLAN:** pi5-ai2 tracks `main` at `/opt/Sharks-News-Aggregator` (it was at
`240236e`, clean), so the plan was PR → merge → `git pull` on the Pi → rebuild `web`. The
push never left the Mac: from the Claude session's sandbox, `git push` failed with
`fatal: could not read Username for 'https://github.com': Device not configured` and
`gh pr create` with `x509: OSStatus -26276` (no keychain access in the sandbox).

**What shipped instead:** the file was written straight to
`/opt/Sharks-News-Aggregator/web/public/` over the noBGP MCP (`fs_write`, sha256
`17fd42d9…49e49f`, matching the local copy), then
`docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d --build web` (exit 0,
about 3 min on the Pi; compose also recreated `api` as a dependency of `web`). Verified:
`curl https://wplepla23gjn.nobgp.link/google68323acf17ad7172.html` → `200 text/html`, body
`google-site-verification: google68323acf17ad7172.html`; homepage still 200.

**Left open:** the commit (`claude/google-search-console-verify` branch) still has to be
pushed and merged from a machine with GitHub credentials. Until then the file is an
untracked file on the Pi, and the next `git pull` that brings it in will refuse to
overwrite it: delete the Pi copy first (`rm web/public/google68323acf17ad7172.html`), then
pull. Not verified that the Search Console "Verify" button has been pressed.

**Closed, same day:** Davin pushed the branch and merged it as #167 (`0e7d4a7`); the merge
couldn't be done from the Claude session either (`gh` TLS failure again, `gh auth token`
empty in the sandbox). On the Pi: `rm` of the untracked copy, `git pull --ff-only`
(`34d8411`… → `0e7d4a7`, clean, no longer behind), and the tracked file hashed to the same
`17fd42d9…49e49f` as the hand-placed one. Rebuilt `web` (exit 0, 17 s, cache hit, `api`
recreated again as a dependency). Public checks after: the verification file, `/`, `/rss`
and `/sitemap.xml` all 200. Still not verified that Search Console's "Verify" was pressed.

## Session 3 — 18 Oct 2026: a headline that told the wrong story

A reader on Bluesky pointed out that a card read *"NHL Rumors: San Jose Sharks, and the
Philadelphia Flyers"* (nhlrumors.com, 15 Oct). Out of context that says Sharks–Flyers
trade rumor; the article is two separate news items, one per team. Davin didn't want it
fixed now, only captured, so it went into the roadmap as `RM-5` in
`docs/IMPROVEMENT_PLAN.md` (the existing "Roadmap / backlog" section, next free ID after
`RM-4`) rather than a new TODO file.

**What was checked, from the code:** headlines are never rewritten.
`select_cluster_headline()` (`api/app/enrichment/clustering.py:1137`) chooses among the
variants' publisher titles; the RSS path never reads the article body (the classifier sees
title + RSS description only); `trafilatura` body extraction exists only for reader
submissions. So the bug is a publisher's roundup title passed through verbatim.

**Not checked:** the article itself, its RSS description, or how often roundup titles
reach the feed. Those are listed as open questions in the RM-5 entry, with the cheapest
first: if the RSS description already shows two separate items, the classifier could flag
a roundup without fetching anything.

## Session 4 — 21–22 Oct 2026: off Node 20

**Why.** Node's 21 Oct 2026 security release fixed ten CVEs, with patches in 22.23.4,
24.22.1 and 26.12.1. Measured in production: the web container ran **v20.20.2**
(`docker exec sharks-news-aggregator-web-1 node -v`). Node 20 has been end-of-life since
April 2026, so it doesn't get these fixes or any later ones. The advisory says end-of-life
lines are always affected. Exposure is lower than Rummy's: every server-side `fetch` in
`web/app` goes to the internal API (`INTERNAL_API_URL`, `API_BASE_URL`), and the Python
worker does the outside fetching. The main problem was simply the unsupported runtime
behind a public link.

**Change (PR #170, merged as 1fff6ac):**
- `web/Dockerfile`: `node:20-alpine` → `node:22.23.4-alpine`, pinned to an exact patch so
  a security release is a deliberate rebuild.
- `npm install --no-audit --no-fund` (below).
- `.github/workflows/ci.yml`: the `web` job's `node-version: 20` → `22.23.4`. The first
  push left CI testing Node 20 while the Dockerfile said 22, and nobody would have
  noticed while CI was green.

**What went wrong on the way.**
- npm's audit endpoint hung on 22 Oct. Test builds on the Pi finished `npm install`, then
  sat at `silly audit bulk request failed` for minutes. The full trail, including the
  WRONG THEORY that the new Node release's keep-alive fix was to blame (22.23.3 hung the
  same way), is in Hawaiian Rummy's MAKING-OF session 12. Measured: the same install took
  2 s with `--no-audit` and was killed at 45 s with it.
- The first CI run (`39714544049`, Node 20, plain `npm ci`) had its `web` job stuck in
  `Run npm ci` from 03:01:25 UTC and never reached typecheck. That was on a GitHub runner,
  which suggests the hang was on npm's side, not our home connection. The step's log
  wasn't readable while it was running, so this is consistent but not proven. Claude's
  token can't cancel runs (`HTTP 403: Resource not accessible by personal access token`),
  so that run was left for Davin to cancel.
- `main` is protected: the first `gh pr merge` was refused ("base branch policy prohibits
  the merge") while checks were running. After the CI fix, all seven checks passed on
  `2ef366c` (`changes`, `api`, `postgres-tests`, `web`, `docker-build`, `docker-verify`,
  `ci`), and the merge went through.

**Tested before deploy:** a build from the branch on pi5-ai2 (`next build` on 22.23.4,
EXIT 0), run as a throwaway container on the live compose network with the production
`INTERNAL_API_URL` and `PUBLIC_SITE_URL`: `/`, `/about` and `/rss` all 200.

**Deploy (22 Oct ~03:30 UTC):** at `/opt/Sharks-News-Aggregator`, `git pull --ff-only`
to 1fff6ac, then `docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d
--build --no-deps web`. `--no-deps` was deliberate: session 2's web rebuild also recreated
`api`. This time it didn't (api still `Up 13 days`). Build EXIT 0 (`next build` 34.9 s).

**Verified after deploy:** web `node -v` **v22.23.4**, `Ready in 391ms`; on the Pi `/`,
`/about`, `/rss`, `/sitemap.xml` and `/api/health` all 200; `/about` canonical still
`https://wplepla23gjn.nobgp.link/about`; signed-out fetches of the public link from the Mac:
`/`, `/about`, `/rss` and `/sitemap.xml` all 200, with the expected `<title>`.

Not checked: whether Next 14.2.35 behaves differently on Node 22 anywhere the smoke paths
don't reach (admin pages, link submission).
