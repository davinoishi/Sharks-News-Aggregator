"""
Entity model - represents players, coaches, teams, and staff.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class Entity(Base):
    """
    Entity model - players, coaches, teams, staff.

    Used for clustering and filtering stories.

    Attributes:
        id: Primary key
        name: Full name (e.g., "Macklin Celebrini")
        slug: URL-friendly slug (e.g., "macklin-celebrini")
        entity_type: 'player', 'coach', 'team', 'staff'
        metadata: Additional data (position, number, etc.)
    """
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    entity_type = Column(String(50), nullable=False)
    extra_metadata = Column('metadata', JSON, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    cluster_entities = relationship("ClusterEntity", back_populates="entity")

    def __repr__(self):
        return f"<Entity(id={self.id}, name='{self.name}', type={self.entity_type})>"

    @classmethod
    def make_slug(cls, name: str) -> str:
        """
        Convert name to URL-friendly slug.

        Args:
            name: Entity name

        Returns:
            Lowercase slug with hyphens
        """
        import re
        # Lowercase, replace spaces and special chars with hyphens
        slug = name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
