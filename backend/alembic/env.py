"""
Alembic Environment Configuration for SmartGuard AI.

Reads DATABASE_URL from the environment (via pydantic-settings), not from alembic.ini.
Imports all SQLAlchemy models so autogenerate works correctly.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# Make the backend package importable from this script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before importing app settings
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Import declarative base AND all models so Alembic can discover the schema
from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402, F401 — side-effect import registers all models

# Alembic Config object
config = context.config

# Apply logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata target for autogenerate
target_metadata = Base.metadata


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Copy backend/.env.example to backend/.env and fill in your Supabase credentials."
        )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live connection needed)."""
    url = get_database_url()
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
    """Run migrations in 'online' mode (requires live connection)."""
    url = get_database_url()

    # Supabase requires SSL
    connect_args = {}
    if url.startswith("postgresql"):
        connect_args["sslmode"] = "require"

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
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
