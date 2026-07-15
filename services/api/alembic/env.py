"""
Alembic async environment for the Real-Time Inference Platform.

- Uses asyncpg via the postgresql+asyncpg:// dialect.
- Target metadata is pulled from SQLModel so autogenerate works.
- DATABASE_URL environment variable is required at migration time.
"""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

# Import all models so SQLModel.metadata includes every table.
import models  # noqa: F401 — side-effect: registers table metadata

target_metadata = SQLModel.metadata


def _get_url() -> str:
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live connection (CI / review)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # Autogenerate ignores these Postgres-specific objects managed by raw SQL
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(_get_url(), echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
