"""Tests for Supabase Auth verification, profile retrieval, and error handling."""
from __future__ import annotations
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from fastapi import Depends
from fastapi.testclient import TestClient
import httpx
import pytest
from app.auth import (
    AuthError,
    AuthenticatedUser,
    get_auth_session,
    get_or_create_profile,
    require_hr_admin,
    verify_supabase_token,
)
from app.config import get_settings
from app.db.models import Profile, Region, UserRole
from app.main import create_app


class FakeAsyncSession:
    def __init__(self, initial_profiles: list[Profile] | None = None) -> None:
        self.store: dict[uuid.UUID, Profile] = {p.user_id: p for p in (initial_profiles or [])}

    async def execute(self, stmt: Any) -> MagicMock:
        uid = next((v for k, v in stmt.compile().params.items() if "user_id" in k), None)
        res = MagicMock()
        res.scalar_one_or_none.return_value = self.store.get(uid)
        return res

    def add(self, obj: Any) -> None:
        if isinstance(obj, Profile): self.store[obj.user_id] = obj

    async def commit(self) -> None: pass
    async def refresh(self, obj: Any) -> None: pass


@pytest.mark.asyncio
async def test_verify_token_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    get_settings.cache_clear()
    uid = str(uuid.uuid4())
    resp = httpx.Response(200, json={"id": uid, "email": "u@test.com"}, request=MagicMock())
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=resp)):
        assert (await verify_supabase_token("jwt"))["id"] == uid
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,exc,sb_url,exp_code,exp_status", [
    (401, '{"message":"JWT expired"}', None, "https://test.supabase.co", "EXPIRED_TOKEN", 401),
    (401, '{"message":"bad signature"}', None, "https://test.supabase.co", "INVALID_TOKEN", 401),
    (None, None, None, None, "AUTH_UNCONFIGURED", 503),
    (None, None, httpx.ConnectError("refused"), "https://test.supabase.co", "AUTH_UNAVAILABLE", 503),
])
async def test_verify_token_errors(monkeypatch, status, body, exc, sb_url, exp_code, exp_status):
    if sb_url:
        monkeypatch.setenv("SUPABASE_URL", sb_url)
    else:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
    get_settings.cache_clear()
    resp = httpx.Response(status, text=body, request=MagicMock()) if status else None
    mock_get = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=resp)
    with patch("httpx.AsyncClient.get", new=mock_get):
        with pytest.raises(AuthError) as err:
            await verify_supabase_token("tok")
        assert err.value.code == exp_code and err.value.status_code == exp_status
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_get_or_create_profile_lifecycle() -> None:
    s = FakeAsyncSession()
    uid = uuid.uuid4()
    p1 = await get_or_create_profile(uid, s)  # type: ignore[arg-type]
    assert p1.user_id == uid and p1.role == UserRole.EMPLOYEE.value and p1.region == Region.GLOBAL.value
    assert (await get_or_create_profile(uid, s)) is p1  # type: ignore[arg-type]


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    get_settings.cache_clear()
    app = create_app()
    session = FakeAsyncSession()

    @app.get("/admin-only")
    async def admin_only(_: AuthenticatedUser = Depends(require_hr_admin)) -> dict:
        return {"admin": True}

    async def override_get_session() -> Any:
        yield session

    app.dependency_overrides[get_auth_session] = override_get_session
    app.state.fake_session = session
    client = TestClient(app)
    yield client
    get_settings.cache_clear()


@pytest.mark.parametrize("headers,mock_body,mock_status,exp_code", [
    ({}, None, None, "MISSING_CREDENTIALS"),
    ({"Authorization": "Basic 12345"}, None, None, "INVALID_CREDENTIALS"),
    ({"Authorization": "Bearer bad"}, '{"message":"bad"}', 401, "INVALID_TOKEN"),
    ({"Authorization": "Bearer exp"}, '{"message":"JWT expired"}', 401, "EXPIRED_TOKEN"),
])
def test_auth_me_failure_cases(auth_client, headers, mock_body, mock_status, exp_code):
    resp = httpx.Response(mock_status, text=mock_body, request=MagicMock()) if mock_status else None
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=resp)):
        r = auth_client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == exp_code


def test_auth_me_success_cases(auth_client: TestClient) -> None:
    uid1 = str(uuid.uuid4())
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200, json={"id": uid1, "email": "new@test.com"}, request=MagicMock()))):
        r1 = auth_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer tok1"})
        assert r1.status_code == 200 and r1.json()["profile"]["role"] == "employee"

    uid2 = uuid.uuid4()
    auth_client.app.state.fake_session.store[uid2] = Profile(user_id=uid2, role=UserRole.HR_ADMINISTRATOR.value, region=Region.EU.value)  # type: ignore[attr-defined]
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200, json={"id": str(uid2), "email": "admin@test.com"}, request=MagicMock()))):
        r2 = auth_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer tok2"})
        assert r2.status_code == 200 and r2.json()["profile"]["is_hr_administrator"] is True


def test_anti_spoofing_ignores_browser_params(auth_client: TestClient) -> None:
    uid = uuid.uuid4()
    auth_client.app.state.fake_session.store[uid] = Profile(user_id=uid, role="employee", region="GLOBAL")  # type: ignore[attr-defined]
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200, json={"id": str(uid)}, request=MagicMock()))):
        headers = {"Authorization": "Bearer t", "X-User-Role": "hr_administrator", "X-User-Region": "EU", "X-User-ID": str(uuid.uuid4())}
        r = auth_client.get("/api/v1/auth/me?role=hr_administrator", headers=headers)
        assert r.status_code == 200 and r.json()["profile"]["role"] == "employee" and r.json()["profile"]["region"] == "GLOBAL"


def test_require_hr_admin_authorization(auth_client: TestClient) -> None:
    emp_uid = str(uuid.uuid4())
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200, json={"id": emp_uid}, request=MagicMock()))):
        assert auth_client.get("/admin-only", headers={"Authorization": "Bearer e"}).status_code == 403

    admin_uid = uuid.uuid4()
    auth_client.app.state.fake_session.store[admin_uid] = Profile(user_id=admin_uid, role=UserRole.HR_ADMINISTRATOR.value)  # type: ignore[attr-defined]
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200, json={"id": str(admin_uid)}, request=MagicMock()))):
        r = auth_client.get("/admin-only", headers={"Authorization": "Bearer a"})
        assert r.status_code == 200 and r.json() == {"admin": True}
