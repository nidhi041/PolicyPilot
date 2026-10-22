"""Supabase Storage integration for policy PDFs."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
from typing import Any, Optional
import uuid
from collections.abc import AsyncGenerator
import inspect
from fastapi import APIRouter, Depends, File, Response, UploadFile
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import AuthenticatedUser, require_authenticated_user, require_hr_admin
from app.config import Settings, get_settings
from app.db.models import Policy, PolicyLifecycleStatus, PolicyVersion, Region
from app.db.session import get_session
from app.errors import AppError


def validate_pdf(content: bytes, filename: Optional[str] = None, max_size_bytes: Optional[int] = None) -> None:
    max_size = max_size_bytes or get_settings().max_policy_file_size_bytes
    if len(content) > max_size:
        raise AppError(f"File size exceeds limit of {max_size} bytes", 413, "FILE_TOO_LARGE")
    if not content:
        raise AppError("Uploaded file is empty", 400, "INVALID_FILE")
    if (filename and not filename.lower().endswith(".pdf")) or not content.startswith(b"%PDF-"):
        raise AppError("Invalid file type: expected valid PDF document", 400, "INVALID_FILE_TYPE")


def sanitize_object_path(filename: str, prefix: Optional[str] = None) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", Path(filename).name.strip())
    name = f"{clean if clean.lower().endswith('.pdf') else clean + '.pdf'}" if clean else "document.pdf"
    unique = f"{uuid.uuid4()}_{name}"
    pfx = re.sub(r"[^a-zA-Z0-9_\-/]", "", prefix or "").replace("..", "").strip("/")
    return f"{pfx}/{unique}" if pfx else unique


def validate_storage_path(path: str) -> str:
    if ".." in path or "\\" in path or path.startswith("/"):
        raise AppError("Invalid storage path", 400, "INVALID_PATH")
    return path


class StorageService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    @property
    def headers(self) -> dict[str, str]:
        if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
            raise AppError("Storage service unconfigured", 503, "STORAGE_UNCONFIGURED")
        key = self.settings.supabase_service_role_key.get_secret_value()
        return {"Authorization": f"Bearer {key}", "apikey": key}

    def _url(self, path: str, endpoint: str = "object") -> str:
        if not self.settings.supabase_url:
            raise AppError("Storage service unconfigured", 503, "STORAGE_UNCONFIGURED")
        return f"{self.settings.supabase_url.rstrip('/')}/storage/v1/{endpoint}/{self.settings.policy_storage_bucket}/{path.lstrip('/')}"

    async def upload_pdf(self, content: bytes, filename: str, prefix: Optional[str] = None) -> dict[str, Any]:
        validate_pdf(content, filename=filename, max_size_bytes=self.settings.max_policy_file_size_bytes)
        storage_path = sanitize_object_path(filename, prefix=prefix)
        url, hdrs = self._url(storage_path), {**self.headers, "Content-Type": "application/pdf", "x-upsert": "true"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=hdrs, content=content)
        except Exception:
            raise AppError("Storage service unavailable", 503, "STORAGE_UNAVAILABLE")
        if resp.status_code not in (200, 201):
            raise AppError(f"Storage upload failed: {resp.text}", 502, "STORAGE_ERROR")
        return {"storage_path": storage_path, "content_hash": hashlib.sha256(content).hexdigest(), "size_bytes": len(content), "bucket": self.settings.policy_storage_bucket}

    async def create_signed_url(self, storage_path: str, expires_in: Optional[int] = None) -> dict[str, Any]:
        validate_storage_path(storage_path)
        expiry = expires_in or self.settings.storage_signed_url_expiry
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._url(storage_path, "object/sign"), headers=self.headers, json={"expiresIn": expiry})
        except Exception:
            raise AppError("Storage service unavailable", 503, "STORAGE_UNAVAILABLE")
        if resp.status_code != 200:
            raise AppError(f"Failed to generate signed URL: {resp.text}", 502, "STORAGE_ERROR")
        rel = (resp.json().get("signedURL") or resp.json().get("signedUrl") or "")
        signed_url = f"{self.settings.supabase_url.rstrip('/')}{rel}" if rel.startswith("/") else rel
        return {"signed_url": signed_url, "expires_in": expiry, "storage_path": storage_path}

    async def download_pdf(self, storage_path: str) -> bytes:
        validate_storage_path(storage_path)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self._url(storage_path, "object/authenticated"), headers=self.headers)
        except Exception:
            raise AppError("Storage service unavailable", 503, "STORAGE_UNAVAILABLE")
        if resp.status_code == 404:
            raise AppError("File not found in storage", 404, "NOT_FOUND")
        if resp.status_code != 200:
            raise AppError(f"Failed to retrieve file from storage: {resp.text}", 502, "STORAGE_ERROR")
        return resp.content

    async def delete_file(self, storage_path: str) -> None:
        validate_storage_path(storage_path)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(self._url(storage_path), headers=self.headers)
        except Exception:
            pass


storage_service = StorageService()
storage_router = APIRouter(prefix="/storage", tags=["Storage"])


async def _maybe_await(val: Any) -> Any:
    return await val if inspect.isawaitable(val) else val


async def get_optional_db_session() -> AsyncGenerator[Optional[AsyncSession], None]:
    if not get_settings().database_url:
        yield None
    else:
        async for s in get_session():
            yield s


async def authorize_document_access(session: Any, storage_path: str, user: AuthenticatedUser) -> None:
    if user.profile.is_hr_administrator or session is None:
        return
    stmt = (
        select(PolicyVersion.status, Policy.region)
        .join(Policy, PolicyVersion.policy_id == Policy.id)
        .where(PolicyVersion.storage_path == storage_path)
    )
    res = (await _maybe_await(session.execute(stmt))).first()
    if not res:
        raise AppError("Document not found", 404, "NOT_FOUND")
    status, region = res
    if status != PolicyLifecycleStatus.PUBLISHED.value:
        raise AppError("Forbidden: Document version is not published", 403, "FORBIDDEN")
    if region not in (user.profile.region, Region.GLOBAL.value):
        raise AppError("Forbidden: Document outside authorized region", 403, "FORBIDDEN")


@storage_router.post("/policies/upload")
async def upload_policy(file: UploadFile = File(...), _: AuthenticatedUser = Depends(require_hr_admin)) -> dict[str, Any]:
    return await storage_service.upload_pdf(await file.read(), filename=file.filename or "policy.pdf")


@storage_router.get("/policies/{path:path}/signed-url")
async def get_policy_signed_url(
    path: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: Any = Depends(get_optional_db_session),
) -> dict[str, Any]:
    await authorize_document_access(session, path, user)
    return await storage_service.create_signed_url(path)


@storage_router.get("/policies/{path:path}/download")
async def download_policy(
    path: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: Any = Depends(get_optional_db_session),
) -> Response:
    await authorize_document_access(session, path, user)
    return Response(content=await storage_service.download_pdf(path), media_type="application/pdf", headers={"Content-Disposition": "inline"})
