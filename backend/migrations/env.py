"""Alembic environment.

Resolves the database URL from the application settings (env-based,
``LEARNY_DATABASE_URL``) and targets the shared Identity metadata so
autogeneration and ``--sql`` offline mode stay in sync with the schema.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.infrastructure.db.metadata import metadata

config = context.config

# Deliberately NOT calling ``logging.config.fileConfig(config.config_file_name)``
# here (the alembic boilerplate default). The application owns logging via
# ``app.core.logging.configure_logging`` (including the sensitive-data redaction
# filter, NFR-SEC-004); ``fileConfig`` reconfigures the root logger from
# ``alembic.ini`` — replacing handlers and dropping that filter — whenever
# ``env.py`` loads (every in-process ``command.upgrade``/``downgrade``). Letting
# it run would strip redaction if migrations ever run after startup, and it
# resets pytest's log-capture handlers under test. Alembic's own INFO output is
# not needed programmatically.

# Inject the runtime DB URL (never hard-coded in alembic.ini).
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = metadata


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
    """Run migrations in 'online' mode against a live connection."""
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
