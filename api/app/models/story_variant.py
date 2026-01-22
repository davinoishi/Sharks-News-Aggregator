"""
StoryVariant model - represents one source's version of a story.
"""
from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, Enum, Text, DateTime, ForeignKey, ARRAY, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.cluster import EventType


class ContentType(str, enum.Enum):
    """Content type enum."""
    ARTICLE = "article"
    VIDEO = "video"
    PODCAST = "podcast"
    SOCIAL_POST = "social_post"
    FORUM_POST = "forum_post"


class VariantStatus(str, enum.Enum):
    """Variant status enum."""
    ACTIVE = "active"
    PENDING_CLUSTER = "pending_cluster"
    ARCHIVED = "archived"


class StoryVariant(Base):
    """
    StoryVariant model - one source's version of a story.

    After a RawItem is enriched, it becomes a StoryVariant.
    Variants are clustered together to form Clusters.

    Attributes:
        id: Primary key
        raw_item_id: Foreign key to raw_items
        source_id: Foreign key to sources
        url: Canonical link-out URL
        title: Article/post title
        content_type: article/video/podcast/etc
        published_at: Original publication timestamp
        tokens: Normalized tokens for clustering
        entities: Entity IDs found in content
        event_type: Classified event type
        source_signal: Signal score from source (1-3)
        status: active/pending_cluster/archived
        metadata: Additional data (JSON)
    """
    __tablename__ = "story_variants"

    id = Column(Integer, primary_key=True, index=True)
    raw_item_id = Column(Integer, ForeignKey("raw_items.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    url = Column(Text, nullable=False, unique=True)
    title = Column(Text, nullable=False)
    content_type = Column(Enum(ContentType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ContentType.ARTICLE)
    published_at = Column(DateTime(timezone=True), nullable=False)
    tokens = Column(ARRAY(Text), default=[])
    entities = Column(ARRAY(Integer), default=[])
    event_type = Column(Enum(EventType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=EventType.OTHER)
    source_signal = Column(Integer, default=1)
    status = Column(Enum(VariantStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=VariantStatus.ACTIVE)
    extra_metadata = Column('metadata', JSON, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    raw_item = relationship("RawItem", back_populates="story_variants")
    source = relationship("Source", back_populates="story_variants")
    cluster_variants = relationship("ClusterVariant", back_populates="variant")
    submissions = relationship("Submission", back_populates="variant")

    def __repr__(self):
        return f"<StoryVariant(id={self.id}, title='{self.title[:50]}...', url='{self.url[:50]}...')>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "variant_id": self.id,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "content_type": self.content_type.value,
            "source_name": self.source.name if self.source else None,
            "source_category": self.source.category.value if self.source else None,
        }
