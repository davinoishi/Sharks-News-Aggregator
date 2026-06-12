"""Pipeline health checks (brief 09, O3).

A single source of truth for "is the ingestion pipeline degraded?", shared by
the ``/health`` endpoint (so an external uptime pinger can alert on it) and the
``monitor_pipeline_health`` Celery task (which logs/alerts on it).

Two conditions mark the pipeline degraded:

- **stale ingest** — the newest ``Source.last_fetched_at`` is older than
  ``3 ×`` the configured ingest interval (beat or the workers have stalled), or
  nothing has ever been fetched.
- **broken sources** — one or more approved sources have hit the broken
  threshold (``fetch_error_count >= 3``).
"""
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datetime_utils import ensure_aware, utcnow

BROKEN_ERROR_THRESHOLD = 3
# How many ingest intervals may elapse before "no fresh fetch" is degraded.
STALE_INTERVAL_MULTIPLIER = 3


@dataclass
class PipelineHealth:
    degraded: bool
    last_scan_at: Optional[object]
    ingest_stale: bool
    broken_sources: List[dict] = field(default_factory=list)

    @property
    def conditions(self) -> List[str]:
        """Stable condition keys for alert de-duplication."""
        keys = []
        if self.ingest_stale:
            keys.append("ingest_stale")
        if self.broken_sources:
            keys.append("broken_sources")
        return keys


def check_pipeline_health(db: Session) -> PipelineHealth:
    """Evaluate the ingestion pipeline's health from the database."""
    from app.models import Source, SourceStatus

    last_scan_at = db.query(func.max(Source.last_fetched_at)).scalar()

    stale_after = timedelta(
        minutes=settings.ingest_interval_minutes * STALE_INTERVAL_MULTIPLIER
    )
    if last_scan_at is None:
        ingest_stale = True
    else:
        ingest_stale = utcnow() - ensure_aware(last_scan_at) > stale_after

    broken = (
        db.query(Source)
        .filter(
            Source.status == SourceStatus.APPROVED,
            Source.fetch_error_count >= BROKEN_ERROR_THRESHOLD,
        )
        .order_by(Source.name)
        .all()
    )
    broken_sources = [
        {
            "id": s.id,
            "name": s.name,
            "fetch_error_count": s.fetch_error_count or 0,
        }
        for s in broken
    ]

    degraded = ingest_stale or bool(broken_sources)
    return PipelineHealth(
        degraded=degraded,
        last_scan_at=last_scan_at,
        ingest_stale=ingest_stale,
        broken_sources=broken_sources,
    )
