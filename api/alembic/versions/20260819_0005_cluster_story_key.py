"""add clusters.story_key — the canonical topic slug used for clustering

Revision ID: 0005_cluster_story_key
Revises: 0004_description_unreliable
Create Date: 2026-08-19

Brief 15 / RM-4. Entity overlap tells the matcher two articles are about the
same *person*; nothing told it whether they were about the same *story*. That
gap put a rookie-card auction and The Athletic's pipeline rankings on one card,
and grew a 116-variant cluster spanning 435 hours.

The classifier now emits a ``story_key`` — a lowercase hyphenated slug naming
the event rather than the subject — in the JSON it already returns, so this
costs no extra LLM calls. This column carries the cluster's key.

Nullable on purpose, and it stays nullable: every cluster that exists before
this deploys has no key, as does anything classified through the keyword
fallback path. The matcher reads absent as "no information" and falls back to
the brief 14 behaviour — never as a mismatch, which is the "missing data as
evidence" bug ``calculate_similarity_score`` already documents.

Indexed because the matcher looks clusters up by key on every candidate pass.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_cluster_story_key"
down_revision: Union[str, None] = "0004_description_unreliable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with STORY_KEY_MAX_LEN in app/services/openrouter.py and the
# column definition in app/models/cluster.py.
_MAX_LEN = 80


def upgrade() -> None:
    op.add_column(
        "clusters",
        sa.Column("story_key", sa.String(length=_MAX_LEN), nullable=True),
    )
    op.create_index("ix_clusters_story_key", "clusters", ["story_key"])


def downgrade() -> None:
    op.drop_index("ix_clusters_story_key", table_name="clusters")
    op.drop_column("clusters", "story_key")
