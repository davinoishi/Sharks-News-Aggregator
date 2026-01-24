"""
Tag model - represents story tags (News, Rumors, Injury, etc.).
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base


class Tag(Base):
    """
    Tag model - story categorization tags.

    Default tags include:
    - Rumors, Injury, Trade, Lineup, Recall, Waiver, Signing, Prospect, Game
    - Official, Barracuda

    Attributes:
        id: Primary key
        name: Display name (e.g., "Rumors Press")
        slug: URL-friendly slug (e.g., "rumors-press")
        display_color: Hex color code for UI
    """
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    slug = Column(String(100), nullable=False, unique=True)
    display_color = Column(String(7), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    cluster_tags = relationship("ClusterTag", back_populates="tag")

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}', slug='{self.slug}')>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "color": self.display_color,
        }
