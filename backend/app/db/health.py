"""Non-destructive SELECT 1 database connectivity probe."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.session import get_engine


@dataclass(frozen=True, slots=True)
class DbHealthResult:
    status: Literal["ok", "error"]
    message: str


async def check_db_connectivity() -> DbHealthResult:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return DbHealthResult(status="ok", message="Database reachable")
    except SQLAlchemyError as exc:
        return DbHealthResult(status="error", message=str(exc))
    except Exception as exc:  # noqa: BLE001
        return DbHealthResult(status="error", message=f"Unexpected error: {exc}")
