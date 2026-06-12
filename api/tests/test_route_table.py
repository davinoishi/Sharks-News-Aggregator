"""Route-table snapshot (brief 07, Q3).

Freezes the set of ``(method, path)`` pairs the API exposes so a future
refactor (splitting routers, moving endpoints) can't silently drop or rename an
endpoint without this test failing. When you intentionally add/remove a route,
update ``EXPECTED_ROUTES`` in the same commit.
"""
from fastapi.routing import APIRoute

from app.main import app

# FastAPI's built-in docs/openapi routes are excluded — we only snapshot the
# application's own endpoints.
_BUILTIN_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

EXPECTED_ROUTES = {
    ("GET", "/health"),
    ("GET", "/feed"),
    ("GET", "/entities"),
    ("GET", "/rss"),
    ("GET", "/cluster/{cluster_id}"),
    ("POST", "/submit/link"),
    ("GET", "/stats"),
    ("POST", "/metrics/pageview"),
    ("POST", "/cluster/{cluster_id}/click"),
    # Admin (auth enforced on the router).
    ("GET", "/admin/sources"),
    ("POST", "/admin/sources/{source_id}/disable"),
    ("POST", "/admin/sources/{source_id}/enable"),
    ("GET", "/admin/submissions"),
    ("GET", "/admin/validations"),
    ("GET", "/admin/validations/stats"),
    ("GET", "/admin/validations/rejected"),
    ("GET", "/admin/validations/llm-report"),
    ("GET", "/admin/llm/health"),
    ("GET", "/admin/bluesky/health"),
    ("GET", "/admin/bluesky/stats"),
    ("GET", "/admin/bluesky/posts"),
    ("POST", "/admin/bluesky/post/{cluster_id}"),
}


def _actual_routes():
    routes = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in _BUILTIN_PATHS:
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            routes.add((method, route.path))
    return routes


def test_route_table_matches_snapshot():
    actual = _actual_routes()
    missing = EXPECTED_ROUTES - actual
    unexpected = actual - EXPECTED_ROUTES
    assert not missing, f"routes disappeared: {sorted(missing)}"
    assert not unexpected, f"routes added without updating snapshot: {sorted(unexpected)}"


def test_candidate_source_endpoints_removed():
    """Brief 07 (C3) removed the candidate-source stub endpoints."""
    paths = {path for _, path in _actual_routes()}
    assert not any("candidate-sources" in p for p in paths)
