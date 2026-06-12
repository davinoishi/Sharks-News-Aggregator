"""Pydantic request/response schemas for the API (brief 07, Q3).

Extracted from ``app.main`` so the route modules in ``app.routers`` can share
them without importing the application object.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, HttpUrl


class HealthResponse(BaseModel):
    ok: bool
    timestamp: datetime
    last_scan_at: Optional[datetime] = None
    # True when the ingestion pipeline is degraded (stale ingest or broken
    # sources). Lets an external uptime pinger alert on it (brief 09, O3).
    degraded: bool = False


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
    # Top-ranked source URL (official→press→other), so the frontend can make the
    # headline a real link without an extra round-trip (U3). None if no variants.
    top_url: Optional[str] = None


class EntityItem(BaseModel):
    id: int
    name: str
    slug: str
    type: str


class EntitiesResponse(BaseModel):
    entities: List[EntityItem]


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
    # Lifetime count of LLM relevance fail-opens (OpenRouter errored and the
    # pipeline fell back to keyword matching). A rising value means the LLM
    # filter is degraded (brief 09, C5).
    fail_open: int = 0


class LLMHealthResponse(BaseModel):
    healthy: bool
    model: str
    enabled: bool


class BlueSkyHealthResponse(BaseModel):
    healthy: bool
    enabled: bool
    handle: str


class BlueSkyPostItem(BaseModel):
    id: int
    cluster_id: int
    cluster_headline: Optional[str] = None
    status: str
    post_uri: Optional[str] = None
    post_text: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    posted_at: Optional[datetime] = None
    created_at: datetime


class BlueSkyStatsResponse(BaseModel):
    total_posts: int
    posted: int
    failed: int
    pending: int
    skipped: int
    last_posted_at: Optional[datetime] = None
