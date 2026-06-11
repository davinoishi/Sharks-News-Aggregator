"""Alembic environment (brief 07, C6).

Reads the database URL from the application settings (single source of truth)
and uses the SQLAlchemy models' metadata as the autogenerate target. Importing
``app.models`` registers every table on ``Base.metadata``.
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Importing the models package registers all tables on Base.metadata.
import app.models  # noqa: F401
from alembic import context
from app.core.config import settings
from app.core.database import Base

config = context.config

# Inject the application's DATABASE_URL so we never duplicate it in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with a live connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
