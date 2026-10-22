"""Async SQLAlchemy engine and session factory for PolicyPilot."""
from __future__ import annotations
from collections.abc import AsyncGenerator
from typing import Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import get_settings

_engine: Optional[AsyncEngine] = None
_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    global _engine, _factory
    if _engine is None:
        s = get_settings()
        connect_args = {}
        if s.database_url and ("6543" in s.database_url or "pooler.supabase" in s.database_url):
            connect_args = {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
        _engine = create_async_engine(
            s.database_url,  # type: ignore[arg-type]
            connect_args=connect_args,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=s.debug,
        )
        _factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    get_engine()
    async with _factory() as session:  # type: ignore[misc]
        yield session


async def close_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _factory = None
