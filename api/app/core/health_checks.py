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

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import USER_SUBMISSION_SOURCE_URL
from app.core.datetime_utils import ensure_aware, utcnow

BROKEN_ERROR_THRESHOLD = 3
# How many ingest intervals may elapse before "no fresh fetch" is degraded.
STALE_INTERVAL_MULTIPLIER = 3

# Cluster shape limits (brief 15, SK-6). A cluster this large or this long-lived
# is the signature of the RM-4 over-merge: production held one with 116 variants
# spanning 435 hours against a 72-hour event window, and it took a reader
# reporting a bad card to notice. Both of these would have fired weeks earlier.
#
# Advisory, not degraded: a wrong card is a content-quality problem, not an
# outage, and flipping /health would train an uptime pinger to cry wolf.
OVERSIZED_CLUSTER_VARIANTS = 15
OVERSIZED_CLUSTER_HOURS = 120


@dataclass
class PipelineHealth:
    degraded: bool
    last_scan_at: Optional[object]
    ingest_stale: bool
    broken_sources: List[dict] = field(default_factory=list)
    oversized_clusters: List[dict] = field(default_factory=list)

    @property
    def conditions(self) -> List[str]:
        """Stable condition keys for alert de-duplication."""
        keys = []
        if self.ingest_stale:
            keys.append("ingest_stale")
        if self.broken_sources:
            keys.append("broken_sources")
        if self.oversized_clusters:
            keys.append("oversized_clusters")
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

    # Exclude the synthetic "User Submissions" source: it is not a fetchable
    # feed, so a non-zero fetch_error_count on it is not a real outage and must
    # not flip the pipeline to "degraded".
    broken = (
        db.query(Source)
        .filter(
            Source.status == SourceStatus.APPROVED,
            Source.fetch_error_count >= BROKEN_ERROR_THRESHOLD,
            Source.base_url != USER_SUBMISSION_SOURCE_URL,
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

    oversized_clusters = _check_cluster_shape(db)

    # oversized_clusters deliberately does NOT set degraded — see the constants.
    degraded = ingest_stale or bool(broken_sources)
    return PipelineHealth(
        degraded=degraded,
        last_scan_at=last_scan_at,
        ingest_stale=ingest_stale,
        broken_sources=broken_sources,
        oversized_clusters=oversized_clusters,
    )


def _check_cluster_shape(db: Session) -> List[dict]:
    """Active clusters that are implausibly large or long-lived (RM-4)."""
    from app.models import Cluster, ClusterStatus, ClusterVariant

    variant_count = func.count(ClusterVariant.variant_id)
    span_hours = (
        func.extract("epoch", Cluster.last_seen_at - Cluster.first_seen_at) / 3600.0
    )

    rows = (
        db.query(Cluster.id, Cluster.headline, variant_count, span_hours)
        .join(ClusterVariant, ClusterVariant.cluster_id == Cluster.id)
        .filter(Cluster.status == ClusterStatus.ACTIVE)
        .group_by(Cluster.id, Cluster.headline, Cluster.first_seen_at, Cluster.last_seen_at)
        .having(
            or_(
                variant_count >= OVERSIZED_CLUSTER_VARIANTS,
                span_hours >= OVERSIZED_CLUSTER_HOURS,
            )
        )
        .order_by(variant_count.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": cluster_id,
            "headline": (headline or "")[:80],
            "variants": int(count or 0),
            "span_hours": round(float(span or 0.0), 1),
        }
        for cluster_id, headline, count, span in rows
    ]
