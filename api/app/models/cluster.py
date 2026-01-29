"""
Cluster model - represents a single real-world event/story.
"""
from datetime import datetime
from typing import List
import enum
from sqlalchemy import Column, Integer, String, Enum, Text, DateTime, ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base


class ClusterStatus(str, enum.Enum):
    """Cluster status enum."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    MERGED = "merged"


class EventType(str, enum.Enum):
    """Event type classification enum."""
    TRADE = "trade"
    INJURY = "injury"
    LINEUP = "lineup"
    RECALL = "recall"
    WAIVER = "waiver"
    SIGNING = "signing"
    PROSPECT = "prospect"
    GAME = "game"
    OPINION = "opinion"
    OTHER = "other"


class Cluster(Base):
    """
    Cluster model - represents a single real-world event.

    Multiple story variants (articles/posts) about the same event
    are grouped into one cluster. The feed displays clusters, not
    individual variants.

    Attributes:
        id: Primary key
        headline: Canonical headline for this cluster
        headline_source_signal: Signal score of source that generated headline
        event_type: Classification (trade, injury, etc.)
        status: active/archived/merged
        first_seen_at: Timestamp of first variant
        last_seen_at: Timestamp of most recent variant
        tokens: Aggregated normalized tokens for clustering
        entities_agg: Aggregated entity IDs for clustering
        source_count: Number of variants in this cluster
    """
    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True, index=True)
    headline = Column(Text, nullable=False)
    headline_source_signal = Column(Integer, default=1)
    event_type = Column(Enum(EventType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=EventType.OTHER)
    status = Column(Enum(ClusterStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ClusterStatus.ACTIVE)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    tokens = Column(ARRAY(Text), default=[])
    entities_agg = Column(ARRAY(Integer), default=[])
    source_count = Column(Integer, default=0)
    click_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster_variants = relationship("ClusterVariant", back_populates="cluster", cascade="all, delete-orphan")
    cluster_tags = relationship("ClusterTag", back_populates="cluster", cascade="all, delete-orphan")
    cluster_entities = relationship("ClusterEntity", back_populates="cluster", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="cluster")

    def __repr__(self):
        return f"<Cluster(id={self.id}, headline='{self.headline[:50]}...', variants={self.source_count})>"

    def update_source_count(self, db_session):
        """Update the source_count field based on actual variant count."""
        from sqlalchemy import func
        from app.models.cluster_variant import ClusterVariant

        count = db_session.query(func.count(ClusterVariant.id)).filter(
            ClusterVariant.cluster_id == self.id
        ).scalar()

        self.source_count = count or 0

    def get_tags(self, db_session) -> List[dict]:
        """Get all tags for this cluster as dictionaries."""
        return [ct.tag.to_dict() for ct in self.cluster_tags]

    def get_entities(self, db_session) -> List[dict]:
        """Get all entities for this cluster as dictionaries."""
        return [{
            "id": ce.entity.id,
            "name": ce.entity.name,
            "slug": ce.entity.slug,
            "type": ce.entity.entity_type,
        } for ce in self.cluster_entities]
