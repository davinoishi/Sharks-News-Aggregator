"""
RawItem model - represents raw ingested content before processing.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class RawItem(Base):
    """
    RawItem model - raw ingested content from sources.

    This is the first stage of ingestion. Raw items are processed into
    StoryVariants by the enrichment worker.

    Attributes:
        id: Primary key
        source_id: Foreign key to sources table
        source_item_id: External ID from RSS/API (for idempotency)
        ingestion_origin: 'scheduled' or 'user_submitted'
        original_url: URL as found in source
        canonical_url: Normalized URL for deduplication
        raw_title: Title text as ingested
        raw_description: Description/summary text
        raw_content: Full content if available
        published_at: Original publication timestamp
        fetched_at: When we fetched this item
        ingest_hash: Hash for deduplication fallback
        metadata: Additional data (JSON)
    """
    __tablename__ = "raw_items"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    source_item_id = Column(String(500), nullable=True)
    ingestion_origin = Column(String(50), default="scheduled")
    original_url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)
    raw_title = Column(Text, nullable=True)
    raw_description = Column(Text, nullable=True)
    raw_content = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    ingest_hash = Column(String(64), nullable=True)
    extra_metadata = Column('metadata', JSON, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    source = relationship("Source", back_populates="raw_items")
    story_variants = relationship("StoryVariant", back_populates="raw_item")
    submissions = relationship("Submission", back_populates="raw_item")

    def __repr__(self):
        return f"<RawItem(id={self.id}, source_id={self.source_id}, url='{self.original_url[:50]}...')>"

    @property
    def display_title(self) -> str:
        """Get the best available title."""
        return self.raw_title or self.raw_description or "Untitled"
