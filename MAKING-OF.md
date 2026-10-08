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
