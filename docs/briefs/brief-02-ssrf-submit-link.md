# Brief 02 — SSRF protection for user-submitted links

Plan item: **S2** (see `docs/IMPROVEMENT_PLAN.md`).

## Task

Validate user-submitted URLs before any server-side fetch so the submissions
worker cannot be used to probe internal services (Redis, Postgres, the Pi's LAN,
cloud metadata endpoints).

## Context

- `POST /submit/link` (`api/app/main.py`) accepts any `HttpUrl`, stores a
  `Submission` row, and queues `process_submission` (`api/app/tasks/submissions.py`),
  which fetches the URL server-side (httpx/trafilatura) from inside the Docker
  network.
- The stack: FastAPI + Celery worker, deployed on a Raspberry Pi behind a tunnel.
  Internal neighbors include `db:5432`, `redis:6379`, the API itself, and
  anything on the Pi's LAN.
- RSS ingestion (`api/app/tasks/ingest.py`) fetches admin-approved feed URLs —
  lower risk, but the validator you build should be reusable there for redirect
  protection.

## Requirements

1. Create a reusable validator module (e.g. `api/app/core/url_guard.py`):
   - Allow only `http`/`https` schemes; reject credentials-in-URL
     (`user:pass@host`) and non-standard ports (allow 80/443 by default,
     make the allowlist configurable).
   - Resolve the hostname and reject if **any** resolved address is private,
     loopback, link-local, multicast, reserved, or unspecified
     (`ipaddress.ip_address(...).is_private` etc.). Reject raw-IP hostnames in
     those ranges too, including IPv6 and IPv4-mapped IPv6.
   - Re-validate on redirects: fetches of submitted URLs must either disable
     auto-redirects and validate each hop (cap at ~5), or use an httpx transport
     hook that validates every request URL.
   - DNS-rebinding hardening: connect to the already-validated IP (pin via
     resolved address) or at minimum re-resolve-and-validate immediately before
     the fetch; document the chosen approach in the module docstring.
2. Apply it in both places:
   - `POST /submit/link`: validate before creating the Submission; return 422
     with a generic message ("URL not allowed") on failure — do not echo internal
     reasoning.
   - `process_submission` worker: validate again before fetching (defense in
     depth; the row may predate validation), marking failures as rejected.
3. Add a size cap and timeout on the worker's fetch of submitted content
   (e.g. 5 MB / 30 s) if not already enforced.
4. Unit tests for the validator: private IPv4, loopback, link-local, IPv6
   (`::1`, `fd00::/8`, `::ffff:10.0.0.1`), `localhost`, internal hostnames
   (mock DNS), allowed public URLs, redirect-to-private (mock).

## Out of scope

- Do NOT change rate limiting or auth (brief 01).
- Do NOT restructure the submissions pipeline beyond inserting validation.
- Do NOT add an outbound proxy or egress firewall (document as future option).

## Verification

- `pytest api/ -k url_guard` (or the project's test layout) passes.
- Manual: `curl -X POST localhost:8001/submit/link -d '{"url":"http://10.0.0.1/"}' -H 'Content-Type: application/json'`
  → 422; same for `http://localhost:6379/`, `http://[::1]/`,
  `http://169.254.169.254/`. A real public news URL → 200 and processes normally.
- Confirm the worker logs show rejection (not a fetch attempt) for a submission
  row hand-inserted with a private URL.

## Deliverable

Branch `improve/02-ssrf-guard`, PR against `main` with test output and the
manual curl transcript. Update the status table in `docs/IMPROVEMENT_PLAN.md`.
