"""Tests for the database access layer: config, DB probe, and health endpoint."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.config import Settings, get_settings
from app.db.health import DbHealthResult, check_db_connectivity
from app.main import create_app


def test_database_url_config():
    assert Settings().database_url is None
    for raw, exp in [
        ("postgresql://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
    ]:
        assert Settings(database_url=raw).database_url == exp


def test_service_role_key_is_secret():
    s = Settings(supabase_service_role_key="mysecret")
    assert "mysecret" not in repr(s.supabase_service_role_key)
    assert s.supabase_service_role_key.get_secret_value() == "mysecret"  # type: ignore[union-attr]


def _mock_engine(exc=None):
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    conn.execute = AsyncMock(side_effect=exc) if exc else AsyncMock()
    return MagicMock(connect=MagicMock(return_value=conn))


@pytest.mark.asyncio
async def test_db_probes():
    with patch("app.db.health.get_engine", return_value=_mock_engine()):
        res = await check_db_connectivity()
        assert res.status == "ok" and "reachable" in res.message.lower()

    eng = MagicMock()
    eng.connect.side_effect = OperationalError("refused", None, None)
    with patch("app.db.health.get_engine", return_value=eng):
        assert (await check_db_connectivity()).status == "error"

    with patch("app.db.health.get_engine", return_value=_mock_engine(RuntimeError("timeout"))):
        res = await check_db_connectivity()
        assert res.status == "error" and "timeout" in res.message


def _client(monkeypatch, db_url=None):
    get_settings.cache_clear()
    if db_url:
        monkeypatch.setenv("DATABASE_URL", db_url)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(create_app())


def test_health_endpoints(monkeypatch):
    try:
        assert _client(monkeypatch, None).get("/health").json()["database"]["status"] == "unconfigured"

        c = _client(monkeypatch, "postgresql+asyncpg://fake:fake@localhost/fake")
        with patch("app.db.health.check_db_connectivity", new=AsyncMock(return_value=DbHealthResult("ok", "ok"))):
            res = c.get("/health").json()
            assert res["status"] == "healthy" and res["database"]["status"] == "ok"

        with patch("app.db.health.check_db_connectivity", new=AsyncMock(return_value=DbHealthResult("error", "refused"))):
            res = c.get("/health").json()
            assert res["status"] == "degraded" and res["database"]["status"] == "error"
    finally:
        get_settings.cache_clear()
