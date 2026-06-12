"""Admin endpoints (brief 07, Q3).

Every route here is registered on a single ``APIRouter`` with
``prefix="/admin"`` and ``dependencies=[Depends(require_admin)]`` so the auth
check is structural — no endpoint can forget to call it
(auth-bypass-by-omission, S1/Q3).

The candidate-source stub endpoints were removed in brief 07 (C3); the
``CandidateSource`` model stays because the data pipeline may still write
candidates.
"""
from datetime import timedelta
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.datetime_utils import utcnow
from app.core.db_utils import METRIC_LLM_FAILOPEN, get_site_metric
from app.dependencies import require_admin
from app.models import (
    Cluster,
    ClusterStatus,
    RawItem,
    Source,
    SourceStatus,
    Submission,
    SubmissionStatus,
    ValidationLog,
    ValidationMethod,
    ValidationResult,
)
from app.models.bluesky_post import BlueSkyPost, PostStatus
from app.schemas import (
    BlueSkyHealthResponse,
    BlueSkyStatsResponse,
    LLMHealthResponse,
    ValidationStatsResponse,
)
from app.services.bluesky import health_check as bluesky_health_check
from app.services.openrouter import health_check as openrouter_health_check
from app.tasks.bluesky import post_cluster
from app.utils import parse_llm_approved, parse_since_parameter

# Every /admin/* route is registered on this router so the auth dependency is
# enforced centrally — no endpoint can forget to call it (auth-bypass-by-omission).
router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("/sources")
def list_sources(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    List all sources with their current health status.

    Returns each source with:
    - Basic info (name, category, feed URL)
    - Health status (active/broken/stale)
    - Last fetch time and error count
    - Recent ingestion stats
    """
    sources = db.query(Source).order_by(Source.name).all()

    # Recent-item counts for ALL sources in one grouped query (was N+1).
    cutoff = utcnow() - timedelta(days=7)
    recent_counts = dict(
        db.query(RawItem.source_id, func.count(RawItem.id))
        .filter(RawItem.created_at >= cutoff)
        .group_by(RawItem.source_id)
        .all()
    )

    items = []
    for source in sources:
        # Determine health status
        if source.status != SourceStatus.APPROVED:
            health = "disabled"
        elif source.fetch_error_count and source.fetch_error_count >= 3:
            health = "broken"
        elif source.last_fetched_at:
            hours_since = (utcnow() - source.last_fetched_at).total_seconds() / 3600
            health = "stale" if hours_since > 2 else "active"
        else:
            health = "unknown"

        recent_items = recent_counts.get(source.id, 0)

        items.append({
            "id": source.id,
            "name": source.name,
            "category": source.category.value,
            "feed_url": source.feed_url,
            "status": source.status.value,
            "health": health,
            "last_fetched_at": source.last_fetched_at.isoformat() if source.last_fetched_at else None,
            "fetch_error_count": source.fetch_error_count or 0,
            "recent_items_7d": recent_items,
        })

    return {
        "sources": items,
        "total": len(items),
        "healthy": sum(1 for s in items if s["health"] == "active"),
        "broken": sum(1 for s in items if s["health"] == "broken"),
    }


@router.post("/sources/{source_id}/disable")
def disable_source(
    source_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Disable a source by setting its status to 'rejected'.
    """
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source.status = SourceStatus.REJECTED
    db.commit()

    return {"status": "disabled", "source_id": source_id, "name": source.name}


@router.post("/sources/{source_id}/enable")
def enable_source(
    source_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Re-enable a disabled source by setting its status to 'approved'.
    """
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source.status = SourceStatus.APPROVED
    source.fetch_error_count = 0
    db.commit()

    return {"status": "enabled", "source_id": source_id, "name": source.name}


@router.get("/submissions")
def list_submissions(
    status: Optional[str] = Query(
        None, description="Filter by status: received|published|pending_review|rejected|duplicate"
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Report of user-submitted links (newest first) for review.

    Submitted links flow through the normal ingestion/enrichment pipeline
    automatically; this report exists so new domains can be reviewed and
    promoted to sources if useful. Raw submitter IPs are never stored, so they
    are not returned.
    """
    query = db.query(Submission)
    if status:
        try:
            status_enum = SubmissionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        query = query.filter(Submission.status == status_enum)

    total = query.count()
    # Secondary sort on id keeps ordering deterministic when several rows share
    # the same created_at timestamp (newest first).
    rows = (
        query.order_by(desc(Submission.created_at), desc(Submission.id))
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        {
            "id": s.id,
            "url": s.url,
            "domain": s.domain or urlparse(s.url).netloc,
            "status": s.status.value,
            "note": s.note,
            "rejection_reason": s.rejection_reason,
            "raw_item_id": s.raw_item_id,
            "cluster_id": s.cluster_id,
            "created_at": s.created_at,
            "processed_at": s.processed_at,
        }
        for s in rows
    ]

    # Status breakdown across all submissions (not just this page).
    by_status = {}
    for value, count in (
        db.query(Submission.status, func.count(Submission.id))
        .group_by(Submission.status)
        .all()
    ):
        by_status[value.value if hasattr(value, "value") else str(value)] = count

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "by_status": by_status,
    }


@router.get("/validations")
def list_validations(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    method: Optional[str] = Query(None, description="Filter by method: llm, keyword, skip"),
    result: Optional[str] = Query(None, description="Filter by result: approved, rejected, error"),
    db: Session = Depends(get_db)
):
    """
    List all validation logs with optional filters.
    """
    # Select the joined RawItem alongside each log (was a per-log re-query, N+1).
    query = db.query(ValidationLog, RawItem).join(
        RawItem, ValidationLog.raw_item_id == RawItem.id
    )

    if method:
        try:
            method_enum = ValidationMethod(method)
            query = query.filter(ValidationLog.method == method_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid method: {method}")

    if result:
        try:
            result_enum = ValidationResult(result)
            query = query.filter(ValidationLog.result == result_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid result: {result}")

    total = query.count()

    rows = query.order_by(desc(ValidationLog.created_at)).offset(offset).limit(limit).all()

    items = []
    for log, raw_item in rows:
        items.append({
            "id": log.id,
            "raw_item_id": log.raw_item_id,
            "raw_item_title": raw_item.raw_title[:100] if raw_item and raw_item.raw_title else None,
            "raw_item_url": raw_item.canonical_url if raw_item else None,
            "method": log.method.value,
            "result": log.result.value,
            "llm_response": log.llm_response,
            "llm_model": log.llm_model,
            "keyword_matched": log.keyword_matched,
            "entities_found": log.entities_found or [],
            "reason": log.reason,
            "latency_ms": log.latency_ms,
            "error_message": log.error_message,
            "created_at": log.created_at
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/validations/stats", response_model=ValidationStatsResponse)
def get_validation_stats(
    request: Request,
    since: Optional[str] = Query(None, description="Time filter: 24h, 7d, 30d"),
    db: Session = Depends(get_db)
):
    """
    Get aggregated validation statistics.
    """
    since_datetime = parse_since_parameter(since) if since else None

    query = db.query(ValidationLog)
    if since_datetime:
        query = query.filter(ValidationLog.created_at >= since_datetime)

    total = query.count()

    approved = query.filter(ValidationLog.result == ValidationResult.APPROVED).count()
    rejected = query.filter(ValidationLog.result == ValidationResult.REJECTED).count()
    errors = query.filter(ValidationLog.result == ValidationResult.ERROR).count()

    by_method = {
        "llm": query.filter(ValidationLog.method == ValidationMethod.LLM).count(),
        "keyword": query.filter(ValidationLog.method == ValidationMethod.KEYWORD).count(),
        "skip": query.filter(ValidationLog.method == ValidationMethod.SKIP).count()
    }

    # Average latency for LLM checks
    avg_latency = db.query(func.avg(ValidationLog.latency_ms)).filter(
        ValidationLog.method == ValidationMethod.LLM,
        ValidationLog.latency_ms.isnot(None)
    )
    if since_datetime:
        avg_latency = avg_latency.filter(ValidationLog.created_at >= since_datetime)
    avg_latency_result = avg_latency.scalar()

    error_rate = (errors / total * 100) if total > 0 else 0.0

    # Lifetime LLM fail-open count (C5). It's a running counter rather than a
    # per-row column, so it isn't affected by the `since` window.
    fail_open = get_site_metric(db, METRIC_LLM_FAILOPEN)

    return {
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "errors": errors,
        "by_method": by_method,
        "avg_latency_ms": round(avg_latency_result, 2) if avg_latency_result else None,
        "error_rate": round(error_rate, 2),
        "fail_open": fail_open,
    }


@router.get("/validations/rejected")
def list_rejected_validations(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    List articles that were rejected by validation.

    Useful for reviewing potential false negatives.
    """
    query = db.query(ValidationLog).join(
        RawItem, ValidationLog.raw_item_id == RawItem.id
    ).filter(
        ValidationLog.result == ValidationResult.REJECTED
    )

    total = query.count()

    logs = query.order_by(desc(ValidationLog.created_at)).offset(offset).limit(limit).all()

    items = []
    for log in logs:
        raw_item = db.query(RawItem).filter(RawItem.id == log.raw_item_id).first()
        items.append({
            "id": log.id,
            "raw_item_id": log.raw_item_id,
            "raw_item_title": raw_item.raw_title if raw_item else None,
            "raw_item_url": raw_item.canonical_url if raw_item else None,
            "raw_item_description": raw_item.raw_description[:300] if raw_item and raw_item.raw_description else None,
            "method": log.method.value,
            "llm_response": log.llm_response,
            "keyword_matched": log.keyword_matched,
            "reason": log.reason,
            "created_at": log.created_at
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/llm/health", response_model=LLMHealthResponse)
def check_llm_health(request: Request):
    """
    Check LLM service health status (OpenRouter).
    """
    is_healthy = openrouter_health_check()

    return {
        "healthy": is_healthy,
        "model": settings.openrouter_model,
        "enabled": settings.llm_relevance_enabled
    }


@router.get("/validations/llm-report")
def get_llm_evaluation_report(
    request: Request,
    since: Optional[str] = Query(None, description="Time filter: 24h, 7d, 30d"),
    db: Session = Depends(get_db)
):
    """
    LLM Evaluation Report - Compare LLM decisions with keyword decisions.

    Shows agreement/disagreement between LLM and keyword checks.
    Useful for tuning the LLM or identifying false positives/negatives.
    """
    since_datetime = parse_since_parameter(since) if since else None

    query = db.query(ValidationLog)
    if since_datetime:
        query = query.filter(ValidationLog.created_at >= since_datetime)

    # Get all validation logs that have both LLM response and keyword result
    logs = query.filter(
        ValidationLog.llm_response.isnot(None),
        ValidationLog.keyword_matched.isnot(None)
    ).order_by(desc(ValidationLog.created_at)).all()

    # Analyze agreement
    total_compared = 0
    agreements = 0
    disagreements = []

    for log in logs:
        total_compared += 1
        llm_approved = parse_llm_approved(log.llm_response)
        keyword_approved = log.keyword_matched

        if llm_approved == keyword_approved:
            agreements += 1
        else:
            raw_item = db.query(RawItem).filter(RawItem.id == log.raw_item_id).first()
            disagreements.append({
                "id": log.id,
                "raw_item_id": log.raw_item_id,
                "title": raw_item.raw_title[:100] if raw_item and raw_item.raw_title else None,
                "url": raw_item.canonical_url if raw_item else None,
                "llm_said": "YES" if llm_approved else "NO",
                "keyword_said": "YES" if keyword_approved else "NO",
                "llm_response": log.llm_response,
                "decision_method": log.method.value,
                "final_result": log.result.value,
                "created_at": log.created_at
            })

    agreement_rate = (agreements / total_compared * 100) if total_compared > 0 else 0

    # Categorize disagreements
    llm_yes_keyword_no = [d for d in disagreements if d["llm_said"] == "YES"]
    llm_no_keyword_yes = [d for d in disagreements if d["llm_said"] == "NO"]

    return {
        "summary": {
            "total_compared": total_compared,
            "agreements": agreements,
            "disagreements": len(disagreements),
            "agreement_rate": round(agreement_rate, 1),
            "llm_more_permissive": len(llm_yes_keyword_no),
            "llm_more_strict": len(llm_no_keyword_yes),
            "evaluation_mode": settings.llm_evaluation_mode
        },
        "llm_approved_keyword_rejected": llm_yes_keyword_no[:20],
        "llm_rejected_keyword_approved": llm_no_keyword_yes[:20]
    }


@router.get("/bluesky/health", response_model=BlueSkyHealthResponse)
def check_bluesky_health(request: Request):
    """
    Check BlueSky service health status.
    """
    is_healthy = bluesky_health_check()

    return {
        "healthy": is_healthy,
        "enabled": settings.bluesky_enabled,
        "handle": settings.bluesky_handle or "(not configured)"
    }


@router.get("/bluesky/stats", response_model=BlueSkyStatsResponse)
def get_bluesky_stats(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get BlueSky posting statistics.
    """
    total = db.query(BlueSkyPost).count()
    posted = db.query(BlueSkyPost).filter(BlueSkyPost.status == PostStatus.POSTED).count()
    failed = db.query(BlueSkyPost).filter(BlueSkyPost.status == PostStatus.FAILED).count()
    pending = db.query(BlueSkyPost).filter(BlueSkyPost.status == PostStatus.PENDING).count()
    skipped = db.query(BlueSkyPost).filter(BlueSkyPost.status == PostStatus.SKIPPED).count()

    # Get last posted time
    last_post = db.query(BlueSkyPost).filter(
        BlueSkyPost.status == PostStatus.POSTED
    ).order_by(desc(BlueSkyPost.posted_at)).first()

    return {
        "total_posts": total,
        "posted": posted,
        "failed": failed,
        "pending": pending,
        "skipped": skipped,
        "last_posted_at": last_post.posted_at if last_post else None
    }


@router.get("/bluesky/posts")
def list_bluesky_posts(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status: pending, posted, failed, skipped"),
    db: Session = Depends(get_db)
):
    """
    List BlueSky post records.
    """
    # Outer-join the cluster (was a per-post re-query, N+1); LEFT join so posts
    # whose cluster was purged still appear.
    query = db.query(BlueSkyPost, Cluster).outerjoin(
        Cluster, Cluster.id == BlueSkyPost.cluster_id
    )

    if status:
        try:
            status_enum = PostStatus(status)
            query = query.filter(BlueSkyPost.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    total = query.count()

    rows = query.order_by(desc(BlueSkyPost.created_at)).offset(offset).limit(limit).all()

    items = []
    for post, cluster in rows:
        items.append({
            "id": post.id,
            "cluster_id": post.cluster_id,
            "cluster_headline": cluster.headline[:100] if cluster else None,
            "status": post.status.value,
            "post_uri": post.post_uri,
            "post_text": post.post_text,
            "error_message": post.error_message,
            "retry_count": post.retry_count,
            "posted_at": post.posted_at,
            "created_at": post.created_at
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/bluesky/post/{cluster_id}")
def trigger_bluesky_post(
    cluster_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Manually trigger a BlueSky post for a specific cluster.
    """
    # Verify cluster exists
    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_id,
        Cluster.status == ClusterStatus.ACTIVE
    ).first()

    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Trigger the task
    result = post_cluster.delay(cluster_id)

    return {
        "status": "queued",
        "task_id": result.id,
        "cluster_id": cluster_id,
        "headline": cluster.headline
    }


__all__ = ["router", "list_submissions"]
