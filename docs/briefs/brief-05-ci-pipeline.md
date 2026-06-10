# Brief 05 — CI pipeline

Plan item: **Q2** (see `docs/IMPROVEMENT_PLAN.md`). Land this early — every
later brief's PR should get checks.

## Task

Add GitHub Actions CI: lint + tests for the Python API, typecheck + lint +
build for the Next.js web app.

## Context

- Repo layout: `api/` (FastAPI, Python, `requirements.txt`, no tests yet —
  brief 06 adds them), `web/` (Next.js 14, TypeScript, `package.json` with
  `package-lock.json`).
- `.github/` currently contains only `dependabot.yml` (npm weekly, pip weekly,
  docker weekly). Dependabot PRs currently merge with zero checks.
- There is no lint config in either project yet.
- Deployment is manual on a Raspberry Pi — CI is checks-only, no deploy jobs.

## Requirements

1. `.github/workflows/ci.yml` triggered on `pull_request` and push to `main`:
   - **api job:** Python 3.12 (match `api/Dockerfile` — check it; if it pins an
     older version, match that), `pip install -r api/requirements.txt`, run
     `ruff check` and `ruff format --check`, then `pytest api/` — but make the
     pytest step tolerate "no tests collected" (exit code 5) until brief 06
     lands, e.g. `pytest api/ || [ $? -eq 5 ]`.
   - **web job:** Node 20, `npm ci` in `web/`, `npx tsc --noEmit`,
     `npm run lint` (add a minimal eslint setup with `next lint` defaults if
     none exists), `npm run build`. Provide dummy env vars the build needs
     (e.g. `INTERNAL_API_URL=http://localhost:8000`).
   - Use dependency caching (setup-python/setup-node built-in caches).
   - Path filters so api-only changes skip the web job and vice versa, but both
     run when shared files (compose, workflows) change.
2. Add `ruff` config (in `api/pyproject.toml` or `ruff.toml`): start permissive
   — target the installed Python version, enable the default rule set plus
   `I` (isort). **Fix or explicitly ignore existing violations so CI is green
   on the first run**; prefer per-file ignores over mass reformatting (keep the
   diff reviewable — if `ruff format --check` would reformat half the codebase,
   skip the format check and note it for brief 07).
3. Docker build smoke job (optional but preferred): `docker build ./api` and
   `docker build ./web` on PRs touching the respective Dockerfiles.
4. Add a CI status badge to `README.md`.
5. Document branch protection steps in the PR description (enabling required
   checks on `main` is a repo-settings action the human must take — list the
   exact check names).

## Out of scope

- Writing the actual test suite (brief 06).
- Deploy automation, release tagging, container publishing.
- Large-scale reformatting of existing code.

## Verification

- Open the PR and confirm both jobs run and pass on the PR itself.
- Push a deliberate failure on a scratch branch (e.g. a TypeScript error),
  confirm the web job fails, then drop the scratch branch.
- `act` is not required; the live PR run is the verification.

## Deliverable

Branch `improve/05-ci`, PR against `main` with green checks and the branch
protection instructions. Update the status table in `docs/IMPROVEMENT_PLAN.md`.
