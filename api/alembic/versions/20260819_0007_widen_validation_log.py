"""widen validation_logs.llm_response and store the parsed verdict

Revision ID: 0007_widen_validation_log
Revises: 0006_cluster_relations
Create Date: 2026-08-19

Brief 16, EV-1. ``llm_response`` was ``String(100)``, which truncates the JSON
OpenRouter returns: 577 of 581 stored responses in the 2026-08-19 corpus are cut
at exactly 100 characters. RM-2's analysis had to recover verdicts with a
``LIKE '%"relevant": true%'`` prefix hack, and brief 16 would have paid the same
tax on every future comparison.

Two changes:

1. ``llm_response`` becomes ``Text``, so **new** rows are stored whole.
2. ``llm_relevant`` is added as a nullable boolean holding the parsed verdict,
   so the common query is ordinary SQL rather than string matching.

**This does not recover the past.** Widening a column cannot restore bytes that
were never written; every existing row stays truncated. What it does recover is
the *verdict*, which survives truncation because ``{"relevant": ...}`` sits at
the front of the JSON — the backfill below mirrors the truncated-row branch of
``app.utils.parse_llm_approved`` so the two agree.

``llm_relevant`` stays nullable rather than defaulting to false: a row whose
verdict cannot be recovered is unknown, not rejected. Collapsing those into
"false" is the same missing-data-as-evidence mistake this codebase has already
made twice (see RM-4 and ``calculate_similarity_score``'s docstring).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_widen_validation_log"
down_revision: Union[str, None] = "0006_cluster_relations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind):
    return {c["name"]: c for c in sa.inspect(bind).get_columns("validation_logs")}


def upgrade() -> None:
    # Idempotent for the same reason 0006 is: 0001_baseline runs
    # Base.metadata.create_all against the CURRENT models, so on a fresh
    # database these are already in place before this revision is reached, and
    # a bare alter/add would fail. The API starts with
    # `alembic upgrade head && uvicorn`, so a failed migration means no service.
    bind = op.get_bind()
    columns = _columns(bind)

    if not isinstance(columns["llm_response"]["type"], sa.Text):
        op.alter_column(
            "validation_logs",
            "llm_response",
            existing_type=sa.String(length=100),
            type_=sa.Text(),
            existing_nullable=True,
        )

    if "llm_relevant" not in columns:
        op.add_column(
            "validation_logs",
            sa.Column("llm_relevant", sa.Boolean(), nullable=True),
        )

    # Backfill from what survived truncation. Mirrors the truncated-row branch
    # of parse_llm_approved: presence of the key decides that a verdict is
    # readable, and the literal decides which way. Rows with no recoverable
    # verdict are deliberately left NULL.
    #
    # Colons are escaped as \: throughout. op.execute() routes the string
    # through sqlalchemy.text(), which reads `:name` as a bind parameter — an
    # unescaped '%"relevant":true%' fails with "A value is required for bind
    # parameter 'true'". The space-separated form is not safe either; both are
    # escaped so neither can regress into the other.
    op.execute(
        r"""
        UPDATE validation_logs
        SET llm_relevant = (
            lower(llm_response) LIKE '%"relevant"\: true%'
            OR lower(llm_response) LIKE '%"relevant"\:true%'
        )
        WHERE llm_response IS NOT NULL
          AND llm_response LIKE '%"relevant"%'
          AND llm_relevant IS NULL
        """
    )
    # Legacy Ollama-era rows, which predate JSON storage entirely.
    op.execute(
        """
        UPDATE validation_logs
        SET llm_relevant = (
            upper(llm_response) LIKE 'YES%' OR upper(llm_response) LIKE '%DECISION: YES%'
        )
        WHERE llm_response IS NOT NULL
          AND llm_response NOT LIKE '%"relevant"%'
          AND llm_relevant IS NULL
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind)

    if "llm_relevant" in columns:
        op.drop_column("validation_logs", "llm_relevant")

    # Narrowing truncates: anything already longer than 100 characters would be
    # rejected by Postgres, so trim explicitly rather than failing the migration.
    op.execute("UPDATE validation_logs SET llm_response = left(llm_response, 100)")
    op.alter_column(
        "validation_logs",
        "llm_response",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
