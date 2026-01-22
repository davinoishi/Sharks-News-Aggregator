"""
ClusterVariant model - mapping table between clusters and variants.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, Numeric, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class ClusterVariant(Base):
    """
    ClusterVariant model - maps variants to clusters.

    A many-to-many relationship between Clusters and StoryVariants.
    In practice, each variant belongs to exactly one cluster.

    Attributes:
        id: Primary key
        cluster_id: Foreign key to clusters
        variant_id: Foreign key to story_variants
        similarity_score: Score that matched this variant to cluster
        added_at: When this variant was added to cluster
    """
    __tablename__ = "cluster_variants"
    __table_args__ = (
        UniqueConstraint('cluster_id', 'variant_id', name='uq_cluster_variant'),
    )

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    variant_id = Column(Integer, ForeignKey("story_variants.id", ondelete="CASCADE"), nullable=False)
    similarity_score = Column(Numeric(5, 3), nullable=True)
    added_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="cluster_variants")
    variant = relationship("StoryVariant", back_populates="cluster_variants")

    def __repr__(self):
        return f"<ClusterVariant(cluster_id={self.cluster_id}, variant_id={self.variant_id}, score={self.similarity_score})>"
