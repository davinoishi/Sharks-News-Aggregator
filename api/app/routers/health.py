"""Health check endpoint (brief 07, Q3)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.datetime_utils import utcnow
from app.models import Source
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    """
    Health check endpoint.
    Returns OK if service is running and last RSS scan time.
    """
    # Get the most recent last_fetched_at across all sources
    last_scan_at = db.query(func.max(Source.last_fetched_at)).scalar()

    return {
        "ok": True,
        "timestamp": utcnow(),
        "last_scan_at": last_scan_at
    }
