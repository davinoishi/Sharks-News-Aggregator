"""
ClusterRelation model - "related stories" links between near-miss clusters.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint

from app.core.database import Base
from app.core.datetime_utils import utcnow


class ClusterRelation(Base):
    """Two clusters the matcher considered merging and decided not to.

    Briefs 14 and 15 deliberately split more: over-merging costs the reader the
    story outright, over-splitting costs them a duplicate glance. This is the
    repayment — without it a split card is a dead end, and the near-miss
    comparison the matcher already computed is thrown away.

    **Stored once per unordered pair**, canonicalised so ``cluster_a_id`` is
    always the smaller id. Relations are symmetric ("A relates to B" and "B
    relates to A" are the same fact) and storing both directions would double
    the rows and invite them to disagree.

    Attributes:
        cluster_a_id: Lower cluster id of the pair.
        cluster_b_id: Higher cluster id of the pair.
        score: The similarity that fell short of the merge bar. Kept so the
            surface can show the strongest relations first and a hub cluster's
            weakest links can be pruned.
        created_at: When the near-miss was observed.
    """
    __tablename__ = "cluster_relations"
    __table_args__ = (
        UniqueConstraint("cluster_a_id", "cluster_b_id", name="uq_cluster_relation"),
        # Lookups come in as "relations for this cluster", which may match on
        # either column, so both need an index.
        Index("ix_cluster_relations_a", "cluster_a_id"),
        Index("ix_cluster_relations_b", "cluster_b_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    cluster_a_id = Column(
        Integer, ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False
    )
    cluster_b_id = Column(
        Integer, ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False
    )
    score = Column(Numeric(5, 3), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    # No ORM relationship() to Cluster on purpose. The delete path for clusters
    # is bulk `query.delete(synchronize_session=False)` precisely because ORM
    # cascades NULL not-null FKs instead of deferring to the database (see
    # run_purge_old_items); a relationship here would invite the same trap back.
    # ON DELETE CASCADE at the column handles cleanup.

    def __repr__(self):
        return (
            f"<ClusterRelation(a={self.cluster_a_id}, b={self.cluster_b_id}, "
            f"score={self.score})>"
        )

    @staticmethod
    def ordered(cluster_id_1: int, cluster_id_2: int) -> tuple:
        """Canonical (a, b) ordering for a pair, so it is stored exactly once."""
        return (
            (cluster_id_1, cluster_id_2)
            if cluster_id_1 < cluster_id_2
            else (cluster_id_2, cluster_id_1)
        )
