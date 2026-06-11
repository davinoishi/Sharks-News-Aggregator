"""FastAPI application wiring (brief 07, Q3).

``main.py`` was a ~1,100-line module holding every route, schema, and helper.
It is now a thin composition root: it builds the app, configures middleware,
and includes the routers in ``app.routers``.

A handful of helpers are re-exported here for backwards compatibility with
existing imports (notably the test suite: ``from app.main import ...``).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.dependencies import (
    enforce_metrics_rate_limit,
    get_real_client_ip,
    hash_client_ip,
    require_admin,
)
from app.routers import admin, feed, health, metrics, submit
from app.routers.admin import list_submissions
from app.utils import _parse_llm_approved, parse_llm_approved, parse_since_parameter

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Sharks News & Rumors Aggregator API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Public routes.
app.include_router(health.router)
app.include_router(feed.router)
app.include_router(submit.router)
app.include_router(metrics.router)
# Admin routes — auth enforced on the router (prefix="/admin", require_admin).
app.include_router(admin.router)

# Backwards-compatible re-exports. These symbols previously lived in this module
# and are imported from ``app.main`` by the test suite and elsewhere.
__all__ = [
    "app",
    "require_admin",
    "get_real_client_ip",
    "hash_client_ip",
    "enforce_metrics_rate_limit",
    "parse_since_parameter",
    "parse_llm_approved",
    "_parse_llm_approved",
    "list_submissions",
]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
