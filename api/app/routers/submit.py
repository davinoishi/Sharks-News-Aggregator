"""User link submission endpoint (brief 07, Q3)."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.datetime_utils import utcnow
from app.core.url_guard import UrlNotAllowed, validate_url
from app.dependencies import get_real_client_ip, hash_client_ip
from app.models import Submission, SubmissionStatus
from app.schemas import SubmitLinkRequest, SubmitLinkResponse
from app.tasks.submissions import process_submission

router = APIRouter()


@router.post("/submit/link", response_model=SubmitLinkResponse)
async def submit_link(
    payload: SubmitLinkRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Submit a user link for ingestion (Option C).

    Process:
    1. Create submission record
    2. Queue for processing by submission worker
    3. Return submission ID and initial status

    Rate Limiting:
    - 10 submissions per IP per hour
    """
    # SSRF guard (PR #53): validate before storing/queuing; generic message —
    # do not leak internal reasoning (which host/IP, why) to the submitter.
    try:
        validate_url(str(payload.url))
    except UrlNotAllowed:
        raise HTTPException(status_code=422, detail="URL not allowed")

    # Compose PR #52 + #54: resolve the REAL client IP behind the Next.js proxy,
    # THEN hash it for storage. Hashing request.client.host directly would hash
    # the proxy IP — re-bucketing every user into one rate limit (reintroduces S3)
    # and making the stored privacy hash meaningless.
    ip_hash = hash_client_ip(get_real_client_ip(request))

    # Check rate limit
    recent_submissions = db.query(Submission).filter(
        Submission.submitter_ip == ip_hash,
        Submission.created_at >= utcnow() - timedelta(hours=1)
    ).count()

    if recent_submissions >= settings.submission_rate_limit_per_ip:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Maximum 10 submissions per hour.")

    # Create submission record (submitter_ip stores the hash, not the raw IP)
    submission = Submission(
        url=str(payload.url),
        note=payload.note,
        submitter_ip=ip_hash,
        status=SubmissionStatus.RECEIVED
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    # Queue for processing
    process_submission.delay(submission.id)

    return {
        "submission_id": submission.id,
        "status": submission.status.value
    }
