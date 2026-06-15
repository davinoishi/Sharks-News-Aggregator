"""add 'unsupported' source_status and retire unimplemented-method sources (R2-F1)

Revision ID: 0003_source_status_unsupported
Revises: 0002_timezone_aware
Create Date: 2026-06-15

Round 2 review (R2-F1). Sources whose ``ingest_method`` is one of the
unimplemented stubs (html/api/reddit/twitter) were left ``approved``, so the
scheduler kept dispatching them to the ``_mark_source_unimplemented`` stub every
cycle, which bumped ``fetch_error_count`` to the broken threshold and produced a
permanent stream of false "broken source" alerts.

This migration introduces a dedicated ``unsupported`` status (excluded from
``get_active_sources``) and moves the existing offenders onto it. The synthetic
"User Submissions" source is intentionally left ``approved`` — it legitimately
uses the API method but is already excluded from scheduling by its base_url, and
other code keys off its approved status.

``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction and the new label
cannot be used in the same transaction it is created, so the enum change runs in
an autocommit block before the UPDATE.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_source_status_unsupported"
down_revision: Union[str, None] = "0002_timezone_aware"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with app.core.constants.USER_SUBMISSION_SOURCE_URL.
_USER_SUBMISSION_SOURCE_URL = "https://submissions.internal/"


def upgrade() -> None:
    # Add the enum label first, outside the migration's transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE source_status ADD VALUE IF NOT EXISTS 'unsupported'")

    # Retire real sources whose ingest method has no implementation. The
    # User Submissions source is excluded — it stays approved by design.
    op.execute(
        """
        UPDATE sources
        SET status = 'unsupported'
        WHERE status = 'approved'
          AND ingest_method IN ('html', 'api', 'reddit', 'twitter')
          AND base_url <> '%s'
        """ % _USER_SUBMISSION_SOURCE_URL
    )


def downgrade() -> None:
    # Move the retired sources back to approved. The 'unsupported' enum label is
    # left in place: Postgres cannot drop a single enum value without recreating
    # the type, and an unused label is harmless.
    op.execute(
        """
        UPDATE sources
        SET status = 'approved'
        WHERE status = 'unsupported'
          AND base_url <> '%s'
        """ % _USER_SUBMISSION_SOURCE_URL
    )
