"""Route-table snapshot (brief 07, Q3).

Freezes the set of ``(method, path)`` pairs the API exposes so a future
refactor (splitting routers, moving endpoints) can't silently drop or rename an
endpoint without this test failing. When you intentionally add/remove a route,
update ``EXPECTED_ROUTES`` in the same commit.

The route set is read from the OpenAPI schema rather than by walking
``app.routes`` and isinstance-checking ``APIRoute``. FastAPI 0.137 stopped
flattening included routers into top-level ``APIRoute`` instances (they now sit
behind an internal ``_IncludedRouter`` wrapper), which silently emptied the old
introspection and made every route read as "missing". ``app.openapi()["paths"]``
is the public, version-stable view of exactly the endpoints the app serves, and
already omits the built-in docs/openapi routes.
"""
from app.main import app

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

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
    for path, operations in app.openapi().get("paths", {}).items():
        for method in operations:
            method = method.upper()
            if method in _HTTP_METHODS:
                routes.add((method, path))
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
