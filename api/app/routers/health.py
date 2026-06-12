"""Health check endpoint (brief 07, Q3)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.datetime_utils import utcnow
from app.core.health_checks import check_pipeline_health
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    """
    Health check endpoint.

    Returns OK if the service is running, the last RSS scan time, and a
    ``degraded`` flag reflecting pipeline health (stale ingest or broken
    sources) so an external uptime pinger can alert on it (brief 09, O3).
    """
    pipeline = check_pipeline_health(db)

    return {
        "ok": True,
        "timestamp": utcnow(),
        "last_scan_at": pipeline.last_scan_at,
        "degraded": pipeline.degraded,
    }
