"""
Async database engine and session factory.

Usage in a FastAPI route
------------------------

    from database import get_session
    from sqlmodel.ext.asyncio.session import AsyncSession

    @app.get("/cameras")
    async def list_cameras(session: AsyncSession = Depends(get_session)):
        result = await session.exec(select(Camera))
        return result.all()
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

log = structlog.get_logger()

# ── Engine ────────────────────────────────────────────────

def _build_url() -> str:
    """Convert a postgresql:// URL to the asyncpg dialect."""
    url = os.environ["DATABASE_URL"]
    # SQLAlchemy needs postgresql+asyncpg://
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global engine
    if engine is None:
        engine = create_async_engine(
            _build_url(),
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,      # detect stale connections
            pool_recycle=1800,       # recycle connections every 30 min
        )
    return engine


# ── Session factory ───────────────────────────────────────

_session_factory: sessionmaker | None = None


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # safe for async — objects stay usable after commit
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a scoped async session per request."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Lifecycle helpers ─────────────────────────────────────

async def connect() -> None:
    """Call on application startup to warm the connection pool."""
    eng = get_engine()
    async with eng.begin() as conn:
        # Verify the connection is live
        await conn.run_sync(lambda _: None)
    log.info("database_connected", url=_build_url().split("@")[-1])  # hide credentials


async def disconnect() -> None:
    """Call on application shutdown to drain the pool gracefully."""
    global engine, _session_factory
    if engine is not None:
        await engine.dispose()
        engine = None
        _session_factory = None
        log.info("database_disconnected")
