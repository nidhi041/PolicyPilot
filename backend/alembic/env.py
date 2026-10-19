"""Alembic env.py — reads DATABASE_URL from app Settings at runtime."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.db.models import Base

target_metadata = Base.metadata


def _db_url(required: bool = True) -> str:
    settings = get_settings()
    if not settings.database_url:
        if required:
            raise RuntimeError("DATABASE_URL is not configured.")
        return "postgresql://postgres:postgres@localhost:5432/postgres"
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", settings.database_url)


def run_migrations_offline() -> None:
    context.configure(url=_db_url(required=False), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


import asyncio
from sqlalchemy.ext.asyncio import create_async_engine


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    settings = get_settings()
    url = settings.database_url or "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    connectable = create_async_engine(url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
