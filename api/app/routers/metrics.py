"""Site stats and public counter endpoints (brief 07, Q3)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import enforce_metrics_rate_limit
from app.models import Cluster, ClusterStatus, SiteMetrics, Source, SourceStatus
from app.schemas import SiteStatsResponse

router = APIRouter()


@router.get("/stats", response_model=SiteStatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """
    Get site-wide statistics.

    Returns aggregate metrics without any user-identifying information:
    - Total page views (lifetime)
    - Total stories tracked
    - Total active sources
    """
    # Get page views from metrics table
    page_views_metric = db.query(SiteMetrics).filter(SiteMetrics.key == "page_views").first()
    page_views = page_views_metric.value if page_views_metric else 0

    # Get lifetime stories count from metrics table
    total_stories_metric = db.query(SiteMetrics).filter(SiteMetrics.key == "total_stories").first()
    total_stories = total_stories_metric.value if total_stories_metric else 0

    # Count approved sources
    total_sources = db.query(func.count(Source.id)).filter(
        Source.status == SourceStatus.APPROVED
    ).scalar() or 0

    return {
        "page_views": page_views,
        "total_stories": total_stories,
        "total_sources": total_sources
    }


@router.post("/metrics/pageview")
def record_pageview(request: Request, db: Session = Depends(get_db)):
    """
    Record a page view.

    Increments the global page view counter. No user information is stored.
    Called once per page load (not on SPA navigation or filter changes).
    """
    enforce_metrics_rate_limit(request)

    metric = db.query(SiteMetrics).filter(SiteMetrics.key == "page_views").first()
    if metric:
        metric.value += 1
    else:
        metric = SiteMetrics(key="page_views", value=1)
        db.add(metric)

    db.commit()

    return {"status": "ok"}


@router.post("/cluster/{cluster_id}/click")
def record_cluster_click(
    cluster_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Record a click on a cluster's source link.

    Increments the click counter for the cluster. No user information is stored.
    Used to show trending/popular stories.
    """
    enforce_metrics_rate_limit(request)

    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_id,
        Cluster.status == ClusterStatus.ACTIVE
    ).first()

    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster.click_count = (cluster.click_count or 0) + 1
    db.commit()

    return {"status": "ok", "click_count": cluster.click_count}
