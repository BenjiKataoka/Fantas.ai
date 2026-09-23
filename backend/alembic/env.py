import asyncio
import sys
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection

from alembic import context

# Make sure backend/ is on the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base
from config import DATABASE_URL

# Import all models so Alembic can detect them for autogenerate
import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our models' metadata
target_metadata = Base.metadata

# Override the URL from .env (never hardcode in alembic.ini)
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Use a sync driver (psycopg2-style URL) for Alembic, swap asyncpg → psycopg2
    # Alembic doesn't support asyncpg directly, so we use the sync pool here only
    sync_url = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")
    from sqlalchemy import create_engine
    connectable = create_engine(
        sync_url,
        connect_args={"sslmode": "require"},
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
