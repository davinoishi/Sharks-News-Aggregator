"""add cluster_relations — "related stories" links between near-miss clusters

Revision ID: 0006_cluster_relations
Revises: 0005_cluster_story_key
Create Date: 2026-08-19

Brief 15, SK-4. Briefs 14 and 15 deliberately split more, on the principle that
over-merging costs the reader the story outright while over-splitting costs
them a duplicate glance. This table is the repayment: without it a split card
is a dead end, and the near-miss comparison the matcher already computed is
thrown away.

One row per unordered pair, canonicalised so ``cluster_a_id`` is always the
smaller id — relations are symmetric, and storing both directions would double
the rows and let them disagree.

``ON DELETE CASCADE`` on both columns so the nightly purge removes relations
with their clusters. That matters more than it looks: the purge deletes
clusters with a bulk ``query.delete(synchronize_session=False)`` specifically
because ORM-level cascades NULL not-null child FKs and abort (see R2/#97), so
cleanup here has to be the database's job, not the ORM's.

**Idempotent, and it has to be.** ``0001_baseline`` runs
``Base.metadata.create_all(checkfirst=True)`` against the *current* models, so
on a fresh database (CI, a new deployment) it creates every table the code
knows about today — including this one — before this revision is reached. A
bare ``create_table`` then fails with DuplicateTable, and because the API
starts with ``alembic upgrade head && uvicorn``, a failed migration means the
service never comes up at all. docker-verify caught it exactly that way.
Guarding on the inspector mirrors what the baseline already does for itself.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_cluster_relations"
down_revision: Union[str, None] = "0005_cluster_story_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("cluster_relations"):
        # Already created by the baseline's create_all on a fresh database.
        return

    op.create_table(
        "cluster_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cluster_a_id", sa.Integer(), nullable=False),
        sa.Column("cluster_b_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(5, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["cluster_a_id"], ["clusters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_b_id"], ["clusters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cluster_a_id", "cluster_b_id", name="uq_cluster_relation"),
    )
    op.create_index("ix_cluster_relations_id", "cluster_relations", ["id"])
    op.create_index("ix_cluster_relations_a", "cluster_relations", ["cluster_a_id"])
    op.create_index("ix_cluster_relations_b", "cluster_relations", ["cluster_b_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("cluster_relations"):
        return

    op.drop_index("ix_cluster_relations_b", table_name="cluster_relations")
    op.drop_index("ix_cluster_relations_a", table_name="cluster_relations")
    op.drop_index("ix_cluster_relations_id", table_name="cluster_relations")
    op.drop_table("cluster_relations")
