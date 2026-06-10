# Brief 01 — Proxy-aware admin auth and rate limiting

Plan items: **S1, S3** (see `docs/IMPROVEMENT_PLAN.md`). Priority: highest. Do this
brief before any other change to `api/app/main.py`.

## Task

Replace the IP-allowlist admin auth with API-key auth injected by the Next.js
proxy, and fix rate limiting so it keys on the real client, not the proxy IP.

## Context

- The browser never talks to FastAPI directly. All requests flow through Next.js
  API routes in `web/app/api/*/route.ts`, which forward to `INTERNAL_API_URL`.
  **FastAPI's `request.client.host` is always the Next.js container or tunnel IP,
  never the end user.**
- `check_admin_access()` (`api/app/main.py`, ~line 551) checks
  `request.client.host` against `settings.admin_allowed_ips` (defaults include
  `192.168.0.0/24` and `10.0.0.0/8`) and also accepts an `X-Admin-API-Key` header
  matching `settings.admin_api_key`. Every `/admin/*` endpoint calls it manually.
- `web/app/api/admin/sources/route.ts` proxies `GET /admin/sources` with **no
  credential**. If the container IP happens to be allowlisted, every internet
  visitor to the `/admin/sources` page is an admin. If not, the admin UI is broken.
- `/submit/link` (`api/app/main.py`, ~line 254) rate-limits by
  `request.client.host` + a count of `Submission` rows in the last hour — so all
  real users share one bucket of `settings.submission_rate_limit_per_ip` (10/hour).
- `POST /metrics/pageview` and `POST /cluster/{id}/click` have no rate limiting.
- Config lives in `api/app/core/config.py` (pydantic-settings, env-driven);
  Docker env wiring in `docker-compose.yml` and `docker-compose.pi.yml`;
  example env in `.env.example`.

## Requirements

1. **Backend admin auth**
   - Convert admin auth to a FastAPI dependency (e.g. `require_admin`) applied to
     every `/admin/*` endpoint via an `APIRouter(dependencies=[...])` or per-route
     `Depends`. No endpoint may rely on a manually-called check.
   - Auth = `X-Admin-API-Key` header compared against `settings.admin_api_key`
     using `secrets.compare_digest`. If `admin_api_key` is empty/unset, **deny all
     admin requests** (fail closed) — do not fall back to IP checks.
   - Remove the IP allowlist logic and the `admin_allowed_ips` setting, or demote
     it to optional defense-in-depth that is ANDed with the key, never a substitute.
   - 403 responses must not echo the client IP or any request detail.
2. **Next.js admin proxy**
   - `web/app/api/admin/sources/route.ts` (and any other admin proxy route)
     injects `X-Admin-API-Key` from a **server-side** env var (`ADMIN_API_KEY`,
     never `NEXT_PUBLIC_*`).
   - Gate the admin proxy routes themselves: require a shared secret from the
     browser (HTTP Basic via middleware, or a simple password prompt that sets an
     httpOnly cookie checked by the route). Pick the simplest approach that keeps
     the admin page usable from a phone; document it in the PR description.
3. **Real client IP**
   - Add a small trusted-proxy helper in the API: read `X-Forwarded-For` **only**
     when the direct peer is a configured trusted proxy (new setting, e.g.
     `trusted_proxy_ips`, defaulting to the Docker network); otherwise use
     `request.client.host`. Next.js proxy routes must forward the original
     client IP in `X-Forwarded-For`.
   - Use that helper for the `/submit/link` rate limit and for the
     `submitter_ip` field.
4. **Rate limits on public write endpoints**
   - `/metrics/pageview` and `/cluster/{id}/click`: add a cheap per-client limit
     (e.g. Redis token bucket or in-memory with a comment about multi-worker
     limits). Generous limits are fine (e.g. 60/min); the goal is stopping
     trivial counter spam, not precision.
5. **Config/docs:** update `.env.example`, `docker-compose.yml`,
   `docker-compose.pi.yml`, and `PRODUCTION_CHECKLIST.md` for the new/removed
   variables. `ADMIN_API_KEY` must be required-nonempty in the compose files'
   `web` and `api` services (`${ADMIN_API_KEY:?...}`).

## Out of scope

- Do NOT refactor `main.py` into routers beyond what's needed for the auth
  dependency (that is brief 07).
- Do NOT implement the candidate-sources endpoints (brief 07).
- Do NOT touch the ingestion/enrichment pipeline, SSRF validation (brief 02), or
  Docker port exposure (brief 03).
- No new auth frameworks, OAuth, or user accounts.

## Verification

- `docker compose up` locally, then:
  - `curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/admin/sources`
    → **403** (no key).
  - Same with `-H "X-Admin-API-Key: $ADMIN_API_KEY"` → **200**.
  - With `ADMIN_API_KEY` unset in the API env → **403** even with a key.
  - Browser: `/admin/sources` page loads only after passing the proxy gate, and
    shows sources (proxy injects the key).
  - Two rapid bursts of >limit POSTs to `/api/metrics/pageview` → 429s appear.
- Confirm 403 bodies contain no IP addresses.
- `grep -rn "check_admin_access" api/` returns nothing (replaced by dependency).
- If a test suite exists by the time you start, all tests pass; add tests for the
  auth dependency (no key / wrong key / right key / empty configured key).

## Deliverable

Branch `improve/01-admin-auth` with a PR against `main`. PR description: what
changed, new env vars, migration steps for the Pi deployment, and the curl
transcript from verification. Update the status table in
`docs/IMPROVEMENT_PLAN.md` (brief 1 → "in review", add PR link).
