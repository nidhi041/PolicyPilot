"""Unit, security, and integration tests for Supabase Storage policy PDF integration."""
from __future__ import annotations
import hashlib
from unittest.mock import AsyncMock, patch
import uuid
from fastapi.testclient import TestClient
import httpx
import pytest
from app.auth import AuthenticatedUser, ProfileInfo, UserInfo, get_current_user
from app.config import Settings, get_settings
from app.db.models import UserRole
from app.errors import AppError
from app.main import create_app
from app.storage import StorageService, sanitize_object_path, validate_pdf, validate_storage_path


def make_user(role: str = UserRole.EMPLOYEE.value) -> AuthenticatedUser:
    uid = uuid.uuid4()
    return AuthenticatedUser(user=UserInfo(id=uid, email="u@test.com"), profile=ProfileInfo(id=uuid.uuid4(), user_id=uid, role=role, region="GLOBAL", is_hr_administrator=(role == UserRole.HR_ADMINISTRATOR.value)))


def test_validate_pdf():
    valid = b"%PDF-1.4 header and sample content"
    validate_pdf(valid, filename="valid.pdf", max_size_bytes=1000)

    for bad_bytes in [b"Hello World", b"\x89PNG\r\n\x1a\n"]:
        with pytest.raises(AppError, match="Invalid file type") as exc:
            validate_pdf(bad_bytes, filename="fake.pdf")
        assert exc.value.code == "INVALID_FILE_TYPE"

    with pytest.raises(AppError, match="Invalid file type"):
        validate_pdf(valid, filename="valid.txt")
    with pytest.raises(AppError, match="Uploaded file is empty"):
        validate_pdf(b"", filename="empty.pdf")
    with pytest.raises(AppError, match="File size exceeds") as exc:
        validate_pdf(valid, filename="toolarge.pdf", max_size_bytes=10)
    assert exc.value.status_code == 413 and exc.value.code == "FILE_TOO_LARGE"


def test_sanitize_object_path_and_validation():
    path = sanitize_object_path("../../etc/passwd.pdf", prefix="../policies/../")
    assert ".." not in path and path.startswith("policies/") and path.endswith("_passwd.pdf")

    clean = sanitize_object_path("My Policy (v1) *new*.pdf")
    assert " " not in clean and "*" not in clean

    for bad in ["../test.pdf", "/root/test.pdf", "a\\b.pdf"]:
        with pytest.raises(AppError, match="Invalid storage path"):
            validate_storage_path(bad)
    assert validate_storage_path("valid/path/doc.pdf") == "valid/path/doc.pdf"


@pytest.mark.asyncio
async def test_storage_service_methods():
    svc = StorageService(Settings(supabase_url="https://test.supabase.co", supabase_service_role_key="service_role_secret", policy_storage_bucket="policy-test"))
    content = b"%PDF-1.4 test document"

    # Success upload
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json={"Key": "k"}))):
        res = await svc.upload_pdf(content, "test.pdf")
        assert res["content_hash"] == hashlib.sha256(content).hexdigest() and res["bucket"] == "policy-test"

    # Storage HTTP error & network error
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(500, text="err"))):
        with pytest.raises(AppError, match="Storage upload failed"):
            await svc.upload_pdf(content, "test.pdf")
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(AppError, match="Storage service unavailable"):
            await svc.upload_pdf(content, "test.pdf")

    # Signed URL success (verifies service secret is not exposed in signed URL)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json={"signedURL": "/storage/v1/object/sign/doc.pdf?token=123"}))):
        res = await svc.create_signed_url("file.pdf", expires_in=120)
        assert res["signed_url"] == "https://test.supabase.co/storage/v1/object/sign/doc.pdf?token=123"
        assert "service_role_secret" not in res["signed_url"]

    # Download success & 404
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200, content=content))):
        assert await svc.download_pdf("file.pdf") == content
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(404, text="Not Found"))):
        with pytest.raises(AppError, match="File not found"):
            await svc.download_pdf("missing.pdf")


def test_api_upload_authorization_and_validation(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    get_settings.cache_clear()
    app, pdf_bytes = create_app(), b"%PDF-1.4 authorized pdf upload"
    client = TestClient(app)

    # Unauthorized & Forbidden
    assert client.post("/api/v1/storage/policies/upload", files={"file": ("test.pdf", pdf_bytes, "application/pdf")}).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.EMPLOYEE.value)
    assert client.post("/api/v1/storage/policies/upload", files={"file": ("test.pdf", pdf_bytes, "application/pdf")}).status_code == 403

    # Authorized HR admin & invalid file type
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.HR_ADMINISTRATOR.value)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json={"Key": "k"}))):
        res = client.post("/api/v1/storage/policies/upload", files={"file": ("policy.pdf", pdf_bytes, "application/pdf")})
        assert res.status_code == 200 and res.json()["content_hash"] == hashlib.sha256(pdf_bytes).hexdigest()

    assert client.post("/api/v1/storage/policies/upload", files={"file": ("notes.txt", b"plain text", "text/plain")}).status_code == 400
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_api_signed_url_and_download(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    get_settings.cache_clear()
    app, client = create_app(), TestClient(create_app())

    # Unauthorized
    assert client.get("/api/v1/storage/policies/doc.pdf/signed-url").status_code == 401
    assert client.get("/api/v1/storage/policies/doc.pdf/download").status_code == 401

    # Authenticated employee
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.EMPLOYEE.value)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json={"signedURL": "/sign/doc.pdf?token=abc"}))):
        res = TestClient(app).get("/api/v1/storage/policies/doc.pdf/signed-url")
        assert res.status_code == 200 and "token=abc" in res.json()["signed_url"] and "service-key" not in res.json()["signed_url"]

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200, content=b"%PDF-1.4 dl"))):
        res = TestClient(app).get("/api/v1/storage/policies/doc.pdf/download")
        assert res.status_code == 200 and res.headers["content-type"] == "application/pdf" and res.content == b"%PDF-1.4 dl"

    app.dependency_overrides.clear()
    get_settings.cache_clear()
