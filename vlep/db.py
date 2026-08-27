"""
VLEP Pipeline — Database Engine & Session Management.

Provides both async (for API/services) and sync (for scripts/migrations)
database access via SQLAlchemy 2.0.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from vlep.config import get_settings

# ── Async engine (API / services) ──────────────────────────────────────────

_settings = get_settings()

async_engine = create_async_engine(
    _settings.database_url,
    echo=_settings.db_echo,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async session; auto-rollback on exception."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Sync engine (scripts / migrations) ─────────────────────────────────────

sync_engine = create_engine(
    _settings.database_url_sync,
    echo=_settings.db_echo,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
)


def get_sync_session() -> Session:
    """Return a synchronous session for script use."""
    return SyncSessionLocal()
