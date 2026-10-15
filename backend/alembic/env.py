"""Alembic env.py — reads DATABASE_URL from app Settings at runtime."""
from __future__ import annotations

import re
from alembic import context
from sqlalchemy import create_engine, pool
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


def run_migrations_online() -> None:
    with create_engine(_db_url(), poolclass=pool.NullPool).connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
