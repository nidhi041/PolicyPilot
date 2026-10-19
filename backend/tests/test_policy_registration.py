"""Tests for HR-admin policy and initial version registration API."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from fastapi.testclient import TestClient
import httpx
import pytest
from app.auth import AuthenticatedUser, ProfileInfo, UserInfo, get_current_user
from app.config import get_settings
from app.db.models import Policy, PolicyVersion, UserRole
from app.errors import AppError
from app.main import create_app
from app.policies import get_db_session, validate_policy_metadata


class FakePolicySession:
    def __init__(self, existing_policies: list[Policy] | None = None, fail_commit: bool = False) -> None:
        self.policies, self.versions = list(existing_policies or []), []
        self.fail_commit, self.rolled_back = fail_commit, False

    async def execute(self, stmt: Any) -> MagicMock:
        params = stmt.compile().params
        t = next((v for k, v in params.items() if "lower" in k or "title" in k), None)
        r = next((v for k, v in params.items() if "region" in k), None)
        match = next((p for p in self.policies if (not t or p.title.lower() == str(t).lower()) and (not r or p.region == r)), None)
        res = MagicMock()
        res.scalar_one_or_none.return_value = match
        return res

    def add(self, obj: Any) -> None:
        (self.policies if isinstance(obj, Policy) else self.versions).append(obj)

    async def commit(self) -> None:
        if self.fail_commit: raise RuntimeError("Database connection lost during commit")

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, obj: Any) -> None: pass


def make_user(role: str = UserRole.HR_ADMINISTRATOR.value) -> AuthenticatedUser:
    uid = uuid.uuid4()
    return AuthenticatedUser(user=UserInfo(id=uid, email="hr@test.com"), profile=ProfileInfo(id=uuid.uuid4(), user_id=uid, role=role, region="GLOBAL", is_hr_administrator=(role == UserRole.HR_ADMINISTRATOR.value)))


def test_validate_policy_metadata():
    assert validate_policy_metadata("Remote Work", "Workplace", "US", "1.0") == ("Remote Work", "Workplace", "US", "1.0")

    for t, c, r, v in [("", "C", "US", "1.0"), ("T", "", "US", "1.0"), ("T", "C", "US", "")]:
        with pytest.raises(AppError, match="cannot be empty"):
            validate_policy_metadata(t, c, r, v)

    with pytest.raises(AppError, match="Invalid region"):
        validate_policy_metadata("Title", "Cat", "INVALID_REG", "1.0")

    now, earlier = datetime.now(timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(AppError, match="effective_to cannot be earlier"):
        validate_policy_metadata("Title", "Cat", "US", "1.0", effective_from=now, effective_to=earlier)


def test_register_policy_unauthorized_and_forbidden(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    get_settings.cache_clear()
    app, client, pdf = create_app(), TestClient(create_app()), b"%PDF-1.4 sample content"

    # Unauthorized & Forbidden
    assert client.post("/api/v1/policies", data={"title": "P1", "category": "C1"}, files={"file": ("p.pdf", pdf, "application/pdf")}).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.EMPLOYEE.value)
    assert TestClient(app).post("/api/v1/policies", data={"title": "P1", "category": "C1"}, files={"file": ("p.pdf", pdf, "application/pdf")}).status_code == 403

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_register_policy_success_and_draft_status(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    get_settings.cache_clear()
    app, fake_session = create_app(), FakePolicySession()
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.HR_ADMINISTRATOR.value)
    app.dependency_overrides[get_db_session] = lambda: fake_session

    pdf = b"%PDF-1.4 authorized policy pdf content"
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json={"Key": "p.pdf"}))):
        res = TestClient(app).post("/api/v1/policies", data={"title": "Data Privacy Policy", "category": "Security", "region": "EU", "version_label": "1.0"}, files={"file": ("privacy.pdf", pdf, "application/pdf")})
        assert res.status_code == 201
        data = res.json()
        assert data["title"] == "Data Privacy Policy" and data["region"] == "EU"
        v = data["version"]
        assert v["version_label"] == "1.0" and v["status"] == "draft" and v["published_at"] is None and v["published_by"] is None
        assert v["storage_path"].startswith("policies/eu/") and len(fake_session.policies) == 1 and len(fake_session.versions) == 1

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_register_policy_duplicate_submission(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.HR_ADMINISTRATOR.value)
    app.dependency_overrides[get_db_session] = lambda: FakePolicySession(existing_policies=[Policy(title="Existing Policy", category="General", region="GLOBAL")])

    res = TestClient(app).post("/api/v1/policies", data={"title": "Existing Policy", "category": "General", "region": "GLOBAL", "version_label": "1.0"}, files={"file": ("p.pdf", b"%PDF-1.4 valid", "application/pdf")})
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUPLICATE_POLICY"

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_register_policy_invalid_metadata_and_storage_error(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    get_settings.cache_clear()
    app, fake_session = create_app(), FakePolicySession()
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.HR_ADMINISTRATOR.value)
    app.dependency_overrides[get_db_session] = lambda: fake_session
    client = TestClient(app)

    # Invalid metadata
    res = client.post("/api/v1/policies", data={"title": "  ", "category": "C"}, files={"file": ("p.pdf", b"%PDF-1.4", "application/pdf")})
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_METADATA"

    # Storage error handling
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")):
        res = client.post("/api/v1/policies", data={"title": "P1", "category": "C1"}, files={"file": ("p.pdf", b"%PDF-1.4 ok", "application/pdf")})
        assert res.status_code == 503 and res.json()["error"]["code"] == "STORAGE_UNAVAILABLE" and len(fake_session.policies) == 0

    # Partial failure DB rollback and cleanup
    fail_session = FakePolicySession(fail_commit=True)
    app.dependency_overrides[get_db_session] = lambda: fail_session
    del_mock = AsyncMock()
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json={"Key": "k"}))), patch("app.storage.StorageService.delete_file", new=del_mock):
        res = client.post("/api/v1/policies", data={"title": "P2", "category": "C2"}, files={"file": ("p.pdf", b"%PDF-1.4 ok", "application/pdf")})
        assert res.status_code == 500 and res.json()["error"]["code"] == "REGISTRATION_FAILED" and fail_session.rolled_back is True and del_mock.called

    app.dependency_overrides.clear()
    get_settings.cache_clear()
