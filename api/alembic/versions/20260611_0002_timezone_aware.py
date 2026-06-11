"""convert naive timestamp columns to timestamptz (C2)

Revision ID: 0002_timezone_aware
Revises: 0001_baseline
Create Date: 2026-06-11

Brief 07 (C2). The models and the current ``infra`` SQL already declare
``TIMESTAMPTZ`` columns, but the live Pi database predates that and may still
have naive ``timestamp without time zone`` columns (which is what motivated the
scattered ``.replace(tzinfo=None)`` patches now removed in the app code).

This migration is intentionally idempotent: it converts *only* columns that are
currently ``timestamp without time zone`` in the ``public`` schema, interpreting
the stored values as UTC. On a fresh install (built from the baseline, already
timestamptz) the loop matches nothing and this is a no-op; on the Pi it upgrades
the legacy columns in place.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_timezone_aware"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPGRADE = """
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type = 'timestamp without time zone'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE ''UTC''',
            r.table_name, r.column_name, r.column_name
        );
    END LOOP;
END $$;
"""

# Structural inverse: re-naturalize timestamptz columns back to naive UTC.
_DOWNGRADE = """
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type = 'timestamp with time zone'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE timestamp without time zone USING %I AT TIME ZONE ''UTC''',
            r.table_name, r.column_name, r.column_name
        );
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    op.execute(_DOWNGRADE)
