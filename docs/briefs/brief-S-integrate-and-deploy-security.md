# Brief S — Integrate security PRs #52/#53/#54 and deploy to production

Reviewed PRs #52 (brief 01, admin auth + rate limiting), #53 (brief 02, SSRF),
and #54 (brief 03, Docker hardening + hygiene). Each is correct in isolation,
but they edit overlapping code and will conflict on merge. This brief integrates
them safely, runs the real Docker verification none of them ran, and deploys.

## Why this brief exists

- All three PRs modify the **same block of `submit_link()`** in
  `api/app/main.py` and add fields at the **same anchor in `config.py`**.
- PRs #52 and #53 both add new files `api/tests/conftest.py` and
  `api/requirements-dev.txt` (both-added conflict).
- A naive conflict resolution that keeps #54's `submit_link` line verbatim
  (`hash_client_ip(request.client.host)`) **silently reintroduces S3**: it hashes
  the proxy IP, so all users share one rate-limit bucket and the privacy hash is
  meaningless. The fix must compose all three changes.
- None of the three ran `docker compose up`; they verified via FastAPI
  TestClient only. The compose/Redis-auth/CSP changes need real verification.
- All three add **required** env vars; compose now refuses to start without them.

## Task

Produce one integrated, conflict-resolved result of #52 + #53 + #54 on `main`,
verify the whole security batch end-to-end under Docker, then deploy to the Pi.

## Approach

Prefer a single integration branch so conflicts are resolved once, reviewed, and
merged atomically:

1. Branch from latest `main`: `git checkout -b improve/security-integration`.
2. Merge the three PR branches in this order, resolving conflicts as specified
   below: `improve/01-admin-auth`, then `improve/02-ssrf-guard`, then
   `improve/03-docker-hardening`.
   (If the maintainer has already merged one of the three into `main`, skip it
   and merge the remaining two onto the updated `main`.)
3. Run the full verification section. Open the integration PR; once green and
   reviewed, it merges to `main` and supersedes #52/#53/#54 (close those with a
   note pointing here, or merge them first and let this resolve the conflicts —
   maintainer's choice; do not leave conflicting branches half-merged).

## Conflict resolution (exact)

### `api/app/main.py` — `submit_link()`
The body must contain **all three** behaviors, composed in this order:

```python
from app.models import Submission, SubmissionStatus
from app.core.url_guard import validate_url, UrlNotAllowed

# SSRF guard (PR #53): validate before storing/queuing; generic message.
try:
    validate_url(str(payload.url))
except UrlNotAllowed:
    raise HTTPException(status_code=422, detail="URL not allowed")

# Real client IP behind the proxy (PR #52) THEN hash it for storage (PR #54).
# Must compose: hashing request.client.host would re-bucket all users (S3).
ip_hash = hash_client_ip(get_real_client_ip(request))

recent_submissions = db.query(Submission).filter(
    Submission.submitter_ip == ip_hash,
    Submission.created_at >= datetime.utcnow() - timedelta(hours=1)
).count()
if recent_submissions >= settings.submission_rate_limit_per_ip:
    raise HTTPException(status_code=429, detail="Rate limit exceeded. Maximum 10 submissions per hour.")

submission = Submission(
    url=str(payload.url),
    note=payload.note,
    submitter_ip=ip_hash,
    status=SubmissionStatus.RECEIVED,
)
```

Keep all of: `require_admin` + `admin_router` + `get_real_client_ip` +
`enforce_metrics_rate_limit` (from #52), `hash_client_ip` (from #54), and the
`url_guard` import usage (from #53). Ensure the `import hashlib`, `secrets`,
`threading`, `time` lines from the respective PRs all survive.

### `api/app/core/config.py` — `Settings`
Keep **all** added fields: `metrics_rate_limit_per_min` (#52),
`trusted_proxy_ips` (#52), `submission_allowed_ports` / `submission_max_redirects`
/ `submission_fetch_max_bytes` (#53), `ip_hash_salt` (#54). Remove
`admin_allowed_ips` (deleted by #52).

### `api/tests/conftest.py` and `api/requirements-dev.txt`
Both-added. Keep one copy of each (they're equivalent — the env-var setup and
`pytest==8.3.4`). The conftest must set `DATABASE_URL`/`CELERY_*` before import.

### `.env.example`, `docker-compose.yml`, `docker-compose.pi.yml`, `PRODUCTION_CHECKLIST.md`
Union of all three PRs' additions. The final `api` service env must include
`ADMIN_API_KEY` (required), `TRUSTED_PROXY_IPS`, and the password-bearing
`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`. The `web` service must include
`ADMIN_API_KEY` + `ADMIN_PANEL_USER` + `ADMIN_PANEL_PASSWORD`. `redis` must keep
`--requirepass` + authenticated healthcheck + no host port. `db` must keep no
host port. `.env.example` lists `REDIS_PASSWORD`, `ADMIN_API_KEY`,
`ADMIN_PANEL_PASSWORD`, `ADMIN_PANEL_USER`, `IP_HASH_SALT`, `TRUSTED_PROXY_IPS`,
`METRICS_RATE_LIMIT_PER_MIN`, and the SSRF tunables.

### `docs/IMPROVEMENT_PLAN.md`
Set briefs 1, 2, 3 status to "merged" with their PR links; note the integration
PR. Resolve the three single-line status-table edits into all three rows.

## Verification (must actually run under Docker)

1. `pip install -r api/requirements-dev.txt && PYTHONPATH=api pytest api/ -q`
   → all tests from #52 and #53 pass.
2. Create a `.env` with all required vars set
   (`ADMIN_API_KEY`, `ADMIN_PANEL_PASSWORD`, `REDIS_PASSWORD`, `IP_HASH_SALT`,
   `POSTGRES_PASSWORD`, `DATABASE_URL`). Confirm `docker compose up -d --build`
   **fails fast** if `ADMIN_API_KEY` / `ADMIN_PANEL_PASSWORD` / `REDIS_PASSWORD`
   are empty, and **starts cleanly** when set. All 6 services healthy.
3. Admin auth:
   - `curl -s -o /dev/null -w '%{http_code}' localhost:8001/admin/sources` → 403.
   - `+ -H "X-Admin-API-Key: $ADMIN_API_KEY"` → 200.
   - Browser `/admin/sources` → Basic prompt; correct creds → page loads.
   - 403 body contains no IP.
4. Rate limiting:
   - Burst >`METRICS_RATE_LIMIT_PER_MIN` POSTs to `/api/metrics/pageview` → 429s.
   - Submit limit buckets per real client IP (forge distinct `X-Forwarded-For`
     from the web container path and confirm separate buckets; same IP hits the
     hourly cap).
5. SSRF: `POST /submit/link` with `http://10.0.0.1/`, `http://localhost:6379/`,
   `http://169.254.169.254/`, `http://[::1]/` → 422 "URL not allowed"; a real
   public news URL → 200 and processes.
6. Network isolation: from the host, `nc -zv localhost 5432` and
   `nc -zv localhost 6379` fail; worker/beat still process tasks
   (`docker compose logs worker` shows a successful task with Redis auth).
7. Headers: `curl -sI localhost:3001 | grep -iE 'content-security|x-frame|x-content|referrer|permissions-policy'`
   present; click through feed / expand / filters with CSP enforced, **zero**
   console violations.
8. IP hashing: submit a link, then inspect the `submissions` row → `submitter_ip`
   is a 64-char hex digest, not a raw IP.
9. End-to-end: ingestion fires, items enrich, clusters appear in `/feed`,
   frontend renders.

## Deploy to production (Pi)

Only after verification passes and the integration is on `main`:

1. On the Pi, add to the deployment `.env`:
   - `ADMIN_API_KEY=$(openssl rand -hex 32)`
   - `ADMIN_PANEL_PASSWORD=<strong password>` (optionally `ADMIN_PANEL_USER`)
   - `REDIS_PASSWORD=$(openssl rand -hex 24)` (URL-safe; no `@ : / #`)
   - `IP_HASH_SALT=$(openssl rand -hex 16)`
   - Remove the now-unused `ADMIN_ALLOWED_IPS` (harmless if left).
2. Apply the submitter_ip migration:
   `docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < api/migrations/hash_submitter_ip.sql`
   (Redis password change means a full `down`/`up` is cleanest since the broker
   URL changes — note any in-flight Celery tasks will be dropped; acceptable.)
3. `git pull` on the Pi, then
   `docker compose -f docker-compose.pi.yml up -d --build`.
4. Post-deploy smoke (against the public URLs): feed loads; admin page prompts
   for Basic auth then loads; `/admin/sources` without the Basic creds is denied;
   submit a real link and confirm it processes; BlueSky posting still runs.
5. Confirm in logs that Redis auth succeeded and no service is crash-looping.

## Out of scope

- Any new features or items from briefs 04–09.
- Changing the auth scheme, SSRF policy, or header policy the three PRs chose.

## Deliverable

Branch `improve/security-integration`, PR against `main` with the full
verification transcript (TestClient + the Docker curl/psql checks) and the
post-deploy smoke results. Update the status table in `docs/IMPROVEMENT_PLAN.md`.
