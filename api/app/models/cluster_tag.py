"""
ClusterTag model - mapping table between clusters and tags.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class ClusterTag(Base):
    """
    ClusterTag model - maps tags to clusters.

    A many-to-many relationship between Clusters and Tags.

    Attributes:
        id: Primary key
        cluster_id: Foreign key to clusters
        tag_id: Foreign key to tags
        created_at: When this tag was added
    """
    __tablename__ = "cluster_tags"
    __table_args__ = (
        UniqueConstraint('cluster_id', 'tag_id', name='uq_cluster_tag'),
    )

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="cluster_tags")
    tag = relationship("Tag", back_populates="cluster_tags")

    def __repr__(self):
        return f"<ClusterTag(cluster_id={self.cluster_id}, tag_id={self.tag_id})>"
