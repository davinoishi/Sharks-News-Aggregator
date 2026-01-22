"""
Source model - represents ingestion sources (RSS feeds, websites, APIs).
"""
from datetime import datetime
from typing import Optional
import enum
from sqlalchemy import Column, Integer, String, Enum, Text, DateTime, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class SourceCategory(str, enum.Enum):
    """Source category enum matching database type."""
    OFFICIAL = "official"
    PRESS = "press"
    OTHER = "other"


class SourceStatus(str, enum.Enum):
    """Source status lifecycle enum."""
    CANDIDATE = "candidate"
    QUEUED_FOR_REVIEW = "queued_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class IngestMethod(str, enum.Enum):
    """Ingestion method enum."""
    RSS = "rss"
    HTML = "html"
    API = "api"
    REDDIT = "reddit"
    TWITTER = "twitter"


class Source(Base):
    """
    Source model - external sources for news/rumors.

    Attributes:
        id: Primary key
        name: Display name of source
        category: official/press/other
        ingest_method: How to fetch content
        base_url: Main website URL
        feed_url: RSS feed URL (if applicable)
        status: Lifecycle status
        priority: Priority for ingestion order (lower = higher priority)
        last_fetched_at: Last successful fetch timestamp
        fetch_error_count: Consecutive fetch errors
        extra_metadata: Additional configuration (JSON)
    """
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(Enum(SourceCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    ingest_method = Column(Enum(IngestMethod, values_callable=lambda x: [e.value for e in x]), nullable=False)
    base_url = Column(Text, nullable=False)
    feed_url = Column(Text, nullable=True)
    status = Column(Enum(SourceStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=SourceStatus.APPROVED)
    priority = Column(Integer, default=100)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    fetch_error_count = Column(Integer, default=0)
    extra_metadata = Column('metadata', JSON, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    raw_items = relationship("RawItem", back_populates="source", cascade="all, delete-orphan")
    story_variants = relationship("StoryVariant", back_populates="source")

    def __repr__(self):
        return f"<Source(id={self.id}, name='{self.name}', category={self.category})>"

    @property
    def source_signal(self) -> int:
        """
        Get source signal score for headline ranking.
        official=3, press=2, other=1
        """
        return {
            SourceCategory.OFFICIAL: 3,
            SourceCategory.PRESS: 2,
            SourceCategory.OTHER: 1,
        }.get(self.category, 1)
