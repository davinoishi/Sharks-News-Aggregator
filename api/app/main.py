from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, HttpUrl
import ipaddress

from app.core.config import settings
from app.core.database import get_db


# ============================================================================
# FastAPI App Initialization
# ============================================================================

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


# ============================================================================
# Pydantic Models (Request/Response Schemas)
# ============================================================================

class HealthResponse(BaseModel):
    ok: bool
    timestamp: datetime
    last_scan_at: Optional[datetime] = None


class SubmitLinkRequest(BaseModel):
    url: HttpUrl
    note: Optional[str] = None


class SubmitLinkResponse(BaseModel):
    submission_id: int
    status: str  # received|published|pending_review|rejected


class ClusterItem(BaseModel):
    id: int
    headline: str
    event_type: str
    first_seen_at: datetime
    last_seen_at: datetime
    source_count: int
    click_count: int
    tags: List[dict]
    entities: List[dict]


class FeedResponse(BaseModel):
    clusters: List[ClusterItem]
    cursor: Optional[str] = None
    has_more: bool = False


class VariantItem(BaseModel):
    variant_id: int
    title: str
    url: str
    published_at: datetime
    content_type: str
    source_name: str
    source_category: str


class ClusterDetailResponse(BaseModel):
    cluster_id: int
    headline: str
    event_type: str
    first_seen_at: datetime
    last_seen_at: datetime
    tags: List[dict]
    entities: List[dict]
    variants: List[VariantItem]


class SiteStatsResponse(BaseModel):
    page_views: int
    total_stories: int
    total_sources: int


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    """
    Health check endpoint.
    Returns OK if service is running and last RSS scan time.
    """
    from app.models import Source
    from sqlalchemy import func

    # Get the most recent last_fetched_at across all sources
    last_scan_at = db.query(func.max(Source.last_fetched_at)).scalar()

    return {
        "ok": True,
        "timestamp": datetime.utcnow(),
        "last_scan_at": last_scan_at
    }


@app.get("/feed", response_model=FeedResponse)
def get_feed(
    tags: Optional[str] = Query(None, description="Comma-separated tag slugs"),
    entities: Optional[str] = Query(None, description="Comma-separated entity slugs"),
    since: Optional[str] = Query(None, description="Time filter: 24h|7d|30d or ISO timestamp"),
    limit: int = Query(50, ge=1, le=100, description="Number of clusters to return"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    db: Session = Depends(get_db)
):
    """
    Get the main feed of clustered stories.

    Query Parameters:
    - tags: Filter by tags (e.g., "rumors-press,injury")
    - entities: Filter by entities (e.g., "macklin-celebrini,will-smith")
    - since: Time filter (24h, 7d, 30d, or ISO timestamp)
    - limit: Number of results (default 50, max 100)
    - cursor: Pagination cursor from previous response

    Returns:
    - List of clusters with headline, tags, source count, etc.
    """
    from app.core.queries import build_feed_query, format_cluster_for_feed

    # Parse time filter
    since_datetime = parse_since_parameter(since)

    # Parse tag and entity filters
    tag_list = tags.split(',') if tags else None
    entity_list = entities.split(',') if entities else None

    # Build and execute query
    clusters, total = build_feed_query(
        db=db,
        tag_slugs=tag_list,
        entity_slugs=entity_list,
        since=since_datetime,
        limit=limit,
        offset=int(cursor) if cursor else 0
    )

    # Format results
    cluster_items = [format_cluster_for_feed(db, cluster) for cluster in clusters]

    # Calculate pagination
    next_cursor = None
    has_more = False
    if cursor:
        current_offset = int(cursor)
        if len(clusters) == limit and current_offset + limit < total:
            next_cursor = str(current_offset + limit)
            has_more = True
    elif len(clusters) == limit and limit < total:
        next_cursor = str(limit)
        has_more = True

    return {
        "clusters": cluster_items,
        "cursor": next_cursor,
        "has_more": has_more
    }


@app.get("/cluster/{cluster_id}", response_model=ClusterDetailResponse)
def get_cluster(
    cluster_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific cluster.

    Returns:
    - Cluster metadata
    - All source links (variants) grouped by category
    - Tags and entities
    """
    from app.models import Cluster, ClusterTag, ClusterEntity, Tag, Entity, ClusterStatus
    from app.core.queries import get_cluster_variants_sorted

    # Load cluster
    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_id,
        Cluster.status == ClusterStatus.ACTIVE
    ).first()

    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Load tags
    cluster_tags = db.query(Tag).join(ClusterTag).filter(
        ClusterTag.cluster_id == cluster_id
    ).all()

    tags = [{"id": tag.id, "name": tag.name, "slug": tag.slug} for tag in cluster_tags]

    # Load entities
    cluster_entities = db.query(Entity).join(ClusterEntity).filter(
        ClusterEntity.cluster_id == cluster_id
    ).all()

    entities = [
        {"id": entity.id, "name": entity.name, "slug": entity.slug, "type": entity.entity_type}
        for entity in cluster_entities
    ]

    # Load variants sorted by source category
    variants_sorted = get_cluster_variants_sorted(db, cluster_id)

    variants = [
        {
            "variant_id": v.id,
            "title": v.title or "Untitled",
            "url": v.url,
            "published_at": v.published_at,
            "content_type": v.event_type.value,
            "source_name": v.source.name if v.source else "Unknown",
            "source_category": v.source.category.value if v.source else "other"
        }
        for v in variants_sorted
    ]

    return {
        "cluster_id": cluster.id,
        "headline": cluster.headline or (variants[0]["title"] if variants else "No headline"),
        "event_type": cluster.event_type.value,
        "first_seen_at": cluster.first_seen_at,
        "last_seen_at": cluster.last_seen_at,
        "tags": tags,
        "entities": entities,
        "variants": variants
    }


@app.post("/submit/link", response_model=SubmitLinkResponse)
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
    from app.models import Submission, SubmissionStatus

    # Get client IP for rate limiting
    client_ip = request.client.host

    # Check rate limit
    recent_submissions = db.query(Submission).filter(
        Submission.submitter_ip == client_ip,
        Submission.created_at >= datetime.utcnow() - timedelta(hours=1)
    ).count()

    if recent_submissions >= settings.submission_rate_limit_per_ip:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Maximum 10 submissions per hour.")

    # Create submission record
    submission = Submission(
        url=str(payload.url),
        note=payload.note,
        submitter_ip=client_ip,
        status=SubmissionStatus.RECEIVED
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    # Queue for processing
    from app.tasks.submissions import process_submission
    process_submission.delay(submission.id)

    return {
        "submission_id": submission.id,
        "status": submission.status.value
    }


# ============================================================================
# Metrics Endpoints (Anonymous, Privacy-Respecting)
# ============================================================================

@app.get("/stats", response_model=SiteStatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """
    Get site-wide statistics.

    Returns aggregate metrics without any user-identifying information:
    - Total page views (lifetime)
    - Total stories tracked
    - Total active sources
    """
    from app.models import SiteMetrics, Cluster, ClusterStatus, Source, SourceStatus
    from sqlalchemy import func

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


@app.post("/metrics/pageview")
def record_pageview(db: Session = Depends(get_db)):
    """
    Record a page view.

    Increments the global page view counter. No user information is stored.
    Called once per page load (not on SPA navigation or filter changes).
    """
    from app.models import SiteMetrics

    metric = db.query(SiteMetrics).filter(SiteMetrics.key == "page_views").first()
    if metric:
        metric.value += 1
    else:
        metric = SiteMetrics(key="page_views", value=1)
        db.add(metric)

    db.commit()

    return {"status": "ok"}


@app.post("/cluster/{cluster_id}/click")
def record_cluster_click(
    cluster_id: int,
    db: Session = Depends(get_db)
):
    """
    Record a click on a cluster's source link.

    Increments the click counter for the cluster. No user information is stored.
    Used to show trending/popular stories.
    """
    from app.models import Cluster, ClusterStatus

    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_id,
        Cluster.status == ClusterStatus.ACTIVE
    ).first()

    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster.click_count = (cluster.click_count or 0) + 1
    db.commit()

    return {"status": "ok", "click_count": cluster.click_count}


# ============================================================================
# Admin Endpoints (Protected)
# ============================================================================

@app.get("/admin/candidate-sources")
def list_candidate_sources(
    status: str = Query("queued_for_review", description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    List candidate sources for review.

    TODO: Add authentication/authorization
    """
    # TODO: Implement query
    # candidates = db.query(CandidateSource).filter(
    #     CandidateSource.status == status
    # ).all()

    return {"candidates": [], "count": 0}


@app.post("/admin/candidate-sources/{candidate_id}/approve")
def approve_candidate_source(
    candidate_id: int,
    db: Session = Depends(get_db)
):
    """
    Approve a candidate source and convert to active source.

    TODO: Add authentication/authorization
    """
    # TODO: Implement approval logic
    # 1. Load candidate
    # 2. Create new Source record
    # 3. Update candidate status
    # 4. Return confirmation

    raise HTTPException(status_code=501, detail="Not implemented yet")


@app.post("/admin/candidate-sources/{candidate_id}/reject")
def reject_candidate_source(
    candidate_id: int,
    db: Session = Depends(get_db)
):
    """
    Reject a candidate source.

    TODO: Add authentication/authorization
    """
    # TODO: Implement rejection logic

    raise HTTPException(status_code=501, detail="Not implemented yet")


# ============================================================================
# Admin Validation Endpoints (IP-protected)
# ============================================================================

def check_admin_access(request: Request):
    """
    Verify admin access via IP whitelist or API key.

    Raises HTTPException if access denied.
    """
    # Check API key header first (for external access)
    api_key = request.headers.get("X-Admin-API-Key")
    if settings.admin_api_key and api_key == settings.admin_api_key:
        return True

    # Get client IP
    client_ip = request.client.host

    # Try to parse and validate client IP
    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=f"Admin access denied for invalid IP {client_ip}"
        )

    # Always allow loopback addresses (localhost)
    if client_ip_obj.is_loopback:
        return True

    # Check if IP is in allowed networks list
    allowed_networks = settings.admin_allowed_ips.split(",")
    for network_str in allowed_networks:
        network_str = network_str.strip()
        if not network_str:
            continue
        try:
            if "/" in network_str:
                network = ipaddress.ip_network(network_str, strict=False)
                if client_ip_obj in network:
                    return True
            else:
                allowed_ip = ipaddress.ip_address(network_str)
                if client_ip_obj == allowed_ip:
                    return True
        except ValueError:
            continue

    # Also allow any private network IP (Docker, local proxies like noBGP agent)
    # These are inherently trusted as they're local connections
    if client_ip_obj.is_private:
        return True

    raise HTTPException(
        status_code=403,
        detail=f"Admin access denied for IP {client_ip}"
    )


class ValidationLogItem(BaseModel):
    id: int
    raw_item_id: int
    raw_item_title: Optional[str] = None
    raw_item_url: Optional[str] = None
    method: str
    result: str
    llm_response: Optional[str] = None
    llm_model: Optional[str] = None
    keyword_matched: Optional[bool] = None
    entities_found: List[int] = []
    reason: Optional[str] = None
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime


class ValidationStatsResponse(BaseModel):
    total: int
    approved: int
    rejected: int
    errors: int
    by_method: dict
    avg_latency_ms: Optional[float] = None
    error_rate: float


class OllamaHealthResponse(BaseModel):
    healthy: bool
    base_url: str
    model: str
    enabled: bool


@app.get("/admin/validations")
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

    Protected by IP whitelist or API key.
    """
    check_admin_access(request)

    from app.models import ValidationLog, ValidationMethod, ValidationResult, RawItem

    query = db.query(ValidationLog).join(RawItem, ValidationLog.raw_item_id == RawItem.id)

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

    logs = query.order_by(desc(ValidationLog.created_at)).offset(offset).limit(limit).all()

    items = []
    for log in logs:
        raw_item = db.query(RawItem).filter(RawItem.id == log.raw_item_id).first()
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


@app.get("/admin/validations/stats", response_model=ValidationStatsResponse)
def get_validation_stats(
    request: Request,
    since: Optional[str] = Query(None, description="Time filter: 24h, 7d, 30d"),
    db: Session = Depends(get_db)
):
    """
    Get aggregated validation statistics.

    Protected by IP whitelist or API key.
    """
    check_admin_access(request)

    from app.models import ValidationLog, ValidationMethod, ValidationResult

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

    return {
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "errors": errors,
        "by_method": by_method,
        "avg_latency_ms": round(avg_latency_result, 2) if avg_latency_result else None,
        "error_rate": round(error_rate, 2)
    }


@app.get("/admin/validations/rejected")
def list_rejected_validations(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    List articles that were rejected by validation.

    Useful for reviewing potential false negatives.
    Protected by IP whitelist or API key.
    """
    check_admin_access(request)

    from app.models import ValidationLog, ValidationResult, RawItem

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


@app.get("/admin/ollama/health", response_model=OllamaHealthResponse)
def check_ollama_health(request: Request):
    """
    Check Ollama service health status.

    Protected by IP whitelist or API key.
    """
    check_admin_access(request)

    from app.services.ollama import health_check

    is_healthy = health_check()

    return {
        "healthy": is_healthy,
        "base_url": settings.ollama_base_url,
        "model": settings.ollama_model,
        "enabled": settings.llm_relevance_enabled
    }


@app.get("/admin/validations/llm-report")
def get_llm_evaluation_report(
    request: Request,
    since: Optional[str] = Query(None, description="Time filter: 24h, 7d, 30d"),
    db: Session = Depends(get_db)
):
    """
    LLM Evaluation Report - Compare LLM decisions with keyword decisions.

    Shows agreement/disagreement between LLM and keyword checks.
    Useful for tuning the LLM or identifying false positives/negatives.

    Protected by IP whitelist or API key.
    """
    check_admin_access(request)

    from app.models import ValidationLog, ValidationMethod, ValidationResult, RawItem

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
        llm_approved = log.llm_response and log.llm_response.upper().startswith("YES")
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


# ============================================================================
# Utility Functions
# ============================================================================

def parse_since_parameter(since: Optional[str]) -> Optional[datetime]:
    """
    Parse the 'since' parameter into a datetime.

    Accepts:
    - '24h', '7d', '30d' (relative times)
    - ISO 8601 timestamp (absolute time)
    """
    if not since:
        return None

    # Relative time shortcuts
    if since.endswith('h'):
        hours = int(since[:-1])
        return datetime.utcnow() - timedelta(hours=hours)
    elif since.endswith('d'):
        days = int(since[:-1])
        return datetime.utcnow() - timedelta(days=days)
    else:
        # Try parsing as ISO timestamp
        try:
            return datetime.fromisoformat(since.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'since' parameter")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
