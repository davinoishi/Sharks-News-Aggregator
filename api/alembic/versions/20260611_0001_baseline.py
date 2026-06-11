"""baseline schema (matches current SQLAlchemy models)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-11

Brief 07 (C6). This is the Alembic baseline. It builds the full current schema
directly from the SQLAlchemy models (``Base.metadata``) so a *fresh* install can
``alembic upgrade head`` instead of relying on the raw SQL in
``infra/postgres/init`` (now deprecated, see ``api/migrations/legacy``).

For the *existing* production database (the Pi), do NOT run this revision — the
schema already exists. Instead ``alembic stamp 0001_baseline`` and then
``alembic upgrade head`` so only the later revisions (e.g. the timezone-aware
column conversion) apply. See ``docs/MIGRATIONS.md``.
"""
from typing import Sequence, Union

# Importing the models package registers every table on Base.metadata.
import app.models  # noqa: F401,E402
from alembic import context
from app.core.database import Base

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op_bind()
    # checkfirst online (safe re-run / partial schemas); emit-everything offline.
    Base.metadata.create_all(bind=bind, checkfirst=not context.is_offline_mode())


def downgrade() -> None:
    bind = op_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=not context.is_offline_mode())


def op_bind():
    from alembic import op
    return op.get_bind()
