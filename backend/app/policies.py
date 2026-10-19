"""Policy registration endpoints and business logic."""
from __future__ import annotations
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, File, Form, UploadFile
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import AuthenticatedUser, require_hr_admin
from app.config import get_settings
from app.db.models import Policy, PolicyLifecycleStatus, PolicyVersion, ProcessingStatus, Region
from app.db.session import get_session
from app.errors import AppError
from app.storage import storage_service, validate_pdf
from app.workflow import policy_processing_workflow


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if not get_settings().database_url:
        raise AppError("Database service unconfigured", 503, "DATABASE_UNCONFIGURED")
    async for s in get_session():
        yield s


def validate_policy_metadata(title: str, category: str, region: str, version_label: str, effective_from: Optional[datetime] = None, effective_to: Optional[datetime] = None) -> tuple[str, str, str, str]:
    t, c, v = (title or "").strip(), (category or "").strip(), (version_label or "").strip()
    r = (region or "").strip().upper()
    if not t or not c or not v:
        raise AppError("Title, category, and version label cannot be empty", 400, "INVALID_METADATA")
    if r not in Region._value2member_map_:
        raise AppError(f"Invalid region: {region!r}", 400, "INVALID_METADATA")
    if effective_from and effective_to and effective_to < effective_from:
        raise AppError("effective_to cannot be earlier than effective_from", 400, "INVALID_METADATA")
    return t, c, r, v


policies_router = APIRouter(prefix="/policies", tags=["Policies"])


@policies_router.post("", status_code=201)
async def register_policy(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
    region: str = Form("GLOBAL"),
    version_label: str = Form("1.0"),
    effective_from: Optional[datetime] = Form(None),
    effective_to: Optional[datetime] = Form(None),
    _: AuthenticatedUser = Depends(require_hr_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    t, c, r, v = validate_policy_metadata(title, category, region, version_label, effective_from, effective_to)
    content = await file.read()
    validate_pdf(content, filename=file.filename or f"{t}.pdf")

    # Guard against duplicate submissions before uploading
    existing = (await session.execute(select(Policy).where(sa.func.lower(Policy.title) == t.lower(), Policy.region == r))).scalar_one_or_none()
    if existing is not None:
        raise AppError(f"Policy '{t}' already exists in region '{r}'", 409, "DUPLICATE_POLICY")

    upload_res = await storage_service.upload_pdf(content, filename=file.filename or f"{t}.pdf", prefix=f"policies/{r.lower()}")
    storage_path = upload_res["storage_path"]

    policy = Policy(id=uuid.uuid4(), title=t, category=c, region=r)
    version = PolicyVersion(
        id=uuid.uuid4(),
        policy_id=policy.id,
        version_label=v,
        status=PolicyLifecycleStatus.DRAFT.value,
        processing_status=ProcessingStatus.PENDING.value,
        effective_from=effective_from,
        effective_to=effective_to,
        storage_path=storage_path,
        content_hash=upload_res["content_hash"],
    )
    try:
        session.add(policy)
        session.add(version)
        await session.commit()
        await session.refresh(policy)
        await session.refresh(version)
    except Exception as exc:
        await session.rollback()
        await storage_service.delete_file(storage_path)
        raise AppError("Failed to register policy", 500, "REGISTRATION_FAILED") from exc

    return {
        "id": str(policy.id), "title": policy.title, "category": policy.category, "region": policy.region,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
        "version": {
            "id": str(version.id), "policy_id": str(policy.id), "version_label": version.version_label,
            "status": version.status, "processing_status": version.processing_status,
            "effective_from": version.effective_from.isoformat() if version.effective_from else None,
            "effective_to": version.effective_to.isoformat() if version.effective_to else None,
            "storage_path": version.storage_path, "content_hash": version.content_hash,
            "published_at": None, "published_by": None,
        },
    }


@policies_router.post("/{policy_id}/versions/{version_id}/process", status_code=200)
async def process_policy_version(
    policy_id: uuid.UUID,
    version_id: uuid.UUID,
    _: AuthenticatedUser = Depends(require_hr_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    return await policy_processing_workflow.process_version(session, version_id)

