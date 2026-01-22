"""
ClusterEntity model - mapping table between clusters and entities.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class ClusterEntity(Base):
    """
    ClusterEntity model - maps entities to clusters.

    A many-to-many relationship between Clusters and Entities.

    Attributes:
        id: Primary key
        cluster_id: Foreign key to clusters
        entity_id: Foreign key to entities
        created_at: When this entity was added
    """
    __tablename__ = "cluster_entities"
    __table_args__ = (
        UniqueConstraint('cluster_id', 'entity_id', name='uq_cluster_entity'),
    )

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="cluster_entities")
    entity = relationship("Entity", back_populates="cluster_entities")

    def __repr__(self):
        return f"<ClusterEntity(cluster_id={self.cluster_id}, entity_id={self.entity_id})>"
