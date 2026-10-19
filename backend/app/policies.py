"""Policy registration and lifecycle management endpoints."""
from __future__ import annotations
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import AuthenticatedUser, require_authenticated_user, require_hr_admin
from app.config import get_settings
from app.db.models import Policy, PolicyLifecycleStatus, PolicyVersion, ProcessingStatus, Region
from app.db.repository import _maybe_await
from app.db.session import get_session
from app.errors import AppError
from app.storage import storage_service, validate_pdf
from app.workflow import policy_processing_workflow


class PublishPolicyRequest(BaseModel):
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class ReviewPolicyRequest(BaseModel):
    status: str = PolicyLifecycleStatus.UNDER_REVIEW.value


def serialize_version(v: PolicyVersion) -> dict[str, Any]:
    return {"id": str(v.id), "policy_id": str(v.policy_id), "version_label": v.version_label, "status": v.status, "processing_status": v.processing_status, "processing_error": v.processing_error, "effective_from": v.effective_from.isoformat() if v.effective_from else None, "effective_to": v.effective_to.isoformat() if v.effective_to else None, "storage_path": v.storage_path, "content_hash": v.content_hash, "published_at": v.published_at.isoformat() if v.published_at else None, "published_by": str(v.published_by) if v.published_by else None, "created_at": v.created_at.isoformat() if v.created_at else None}


def serialize_policy(p: Policy, versions: Optional[list[PolicyVersion]] = None) -> dict[str, Any]:
    data = {"id": str(p.id), "title": p.title, "category": p.category, "region": p.region, "created_at": p.created_at.isoformat() if p.created_at else None, "updated_at": p.updated_at.isoformat() if p.updated_at else None}
    if versions is not None:
        data["versions"] = [serialize_version(v) for v in versions]
        if versions: data["version"] = serialize_version(versions[0])
    return data


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


@policies_router.get("", status_code=200)
async def list_policies(region: Optional[str] = Query(None), category: Optional[str] = Query(None), status: Optional[str] = Query(None), search: Optional[str] = Query(None), current_user: AuthenticatedUser = Depends(require_authenticated_user), session: AsyncSession = Depends(get_db_session)) -> list[dict[str, Any]]:
    stmt = select(Policy).order_by(Policy.title.asc())
    if not current_user.profile.is_hr_administrator:
        stmt = stmt.where(Policy.region.in_([current_user.profile.region, Region.GLOBAL.value]))
    elif region:
        stmt = stmt.where(Policy.region == region.upper())
    if category: stmt = stmt.where(sa.func.lower(Policy.category) == category.lower().strip())
    if search: stmt = stmt.where(Policy.title.ilike(f"%{search.strip()}%"))
    policies = list((await _maybe_await(session.execute(stmt))).scalars().all())
    results: list[dict[str, Any]] = []
    for pol in policies:
        v_res = await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.policy_id == pol.id).order_by(PolicyVersion.created_at.desc())))
        pol_versions = list(v_res.scalars().all())
        if not current_user.profile.is_hr_administrator:
            published = [v for v in pol_versions if v.status == PolicyLifecycleStatus.PUBLISHED.value]
            if published: results.append(serialize_policy(pol, versions=[published[0]]))
        else:
            if status and not any(v.status == status.lower() for v in pol_versions): continue
            results.append(serialize_policy(pol, versions=pol_versions))
    return results


@policies_router.get("/{policy_id}", status_code=200)
async def get_policy_detail(policy_id: uuid.UUID, current_user: AuthenticatedUser = Depends(require_authenticated_user), session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    pol = (await _maybe_await(session.execute(select(Policy).where(Policy.id == policy_id)))).scalar_one_or_none()
    if not pol: raise AppError("Policy not found", 404, "NOT_FOUND")
    v_res = await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.policy_id == pol.id).order_by(PolicyVersion.created_at.desc())))
    pol_versions = list(v_res.scalars().all())
    if not current_user.profile.is_hr_administrator:
        if pol.region not in (current_user.profile.region, Region.GLOBAL.value): raise AppError("Forbidden: Policy outside authorized region", 403, "FORBIDDEN")
        published = [v for v in pol_versions if v.status == PolicyLifecycleStatus.PUBLISHED.value]
        if not published: raise AppError("Policy not found", 404, "NOT_FOUND")
        return serialize_policy(pol, versions=published)
    return serialize_policy(pol, versions=pol_versions)


@policies_router.post("", status_code=201)
async def register_policy(file: UploadFile = File(...), title: str = Form(...), category: str = Form(...), region: str = Form("GLOBAL"), version_label: str = Form("1.0"), effective_from: Optional[datetime] = Form(None), effective_to: Optional[datetime] = Form(None), _: AuthenticatedUser = Depends(require_hr_admin), session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    t, c, r, v = validate_policy_metadata(title, category, region, version_label, effective_from, effective_to)
    content = await file.read(); validate_pdf(content, filename=file.filename or f"{t}.pdf")
    if (await _maybe_await(session.execute(select(Policy).where(sa.func.lower(Policy.title) == t.lower(), Policy.region == r)))).scalar_one_or_none() is not None:
        raise AppError(f"Policy '{t}' already exists in region '{r}'", 409, "DUPLICATE_POLICY")
    upload_res = await storage_service.upload_pdf(content, filename=file.filename or f"{t}.pdf", prefix=f"policies/{r.lower()}")
    policy = Policy(id=uuid.uuid4(), title=t, category=c, region=r)
    version = PolicyVersion(id=uuid.uuid4(), policy_id=policy.id, version_label=v, status=PolicyLifecycleStatus.DRAFT.value, processing_status=ProcessingStatus.PENDING.value, effective_from=effective_from, effective_to=effective_to, storage_path=upload_res["storage_path"], content_hash=upload_res["content_hash"])
    try:
        session.add(policy); session.add(version)
        await _maybe_await(session.commit()); await _maybe_await(session.refresh(policy)); await _maybe_await(session.refresh(version))
    except Exception as exc:
        await _maybe_await(session.rollback()); await storage_service.delete_file(upload_res["storage_path"])
        raise AppError("Failed to register policy", 500, "REGISTRATION_FAILED") from exc
    return serialize_policy(policy, versions=[version])


@policies_router.post("/{policy_id}/versions", status_code=201)
async def replace_policy_version(policy_id: uuid.UUID, file: UploadFile = File(...), version_label: str = Form(...), effective_from: Optional[datetime] = Form(None), effective_to: Optional[datetime] = Form(None), _: AuthenticatedUser = Depends(require_hr_admin), session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    pol = (await _maybe_await(session.execute(select(Policy).where(Policy.id == policy_id)))).scalar_one_or_none()
    if not pol: raise AppError("Policy not found", 404, "NOT_FOUND")
    v_label = (version_label or "").strip()
    if not v_label: raise AppError("Version label cannot be empty", 400, "INVALID_METADATA")
    if effective_from and effective_to and effective_to < effective_from: raise AppError("effective_to cannot be earlier than effective_from", 400, "INVALID_METADATA")
    if (await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.policy_id == policy_id, PolicyVersion.version_label == v_label)))).scalar_one_or_none():
        raise AppError(f"Version '{v_label}' already exists for this policy", 409, "DUPLICATE_VERSION")
    content = await file.read(); validate_pdf(content, filename=file.filename or f"{v_label}.pdf")
    upload_res = await storage_service.upload_pdf(content, filename=file.filename or f"{v_label}.pdf", prefix=f"policies/{pol.region.lower()}")
    new_version = PolicyVersion(id=uuid.uuid4(), policy_id=pol.id, version_label=v_label, status=PolicyLifecycleStatus.DRAFT.value, processing_status=ProcessingStatus.PENDING.value, effective_from=effective_from, effective_to=effective_to, storage_path=upload_res["storage_path"], content_hash=upload_res["content_hash"])
    try:
        session.add(new_version); await _maybe_await(session.commit()); await _maybe_await(session.refresh(new_version))
    except Exception as exc:
        await _maybe_await(session.rollback()); await storage_service.delete_file(upload_res["storage_path"])
        raise AppError("Failed to create policy version", 500, "CREATION_FAILED") from exc
    return serialize_version(new_version)


@policies_router.post("/{policy_id}/versions/{version_id}/review", status_code=200)
async def review_policy_version(policy_id: uuid.UUID, version_id: uuid.UUID, payload: Optional[ReviewPolicyRequest] = None, _: AuthenticatedUser = Depends(require_hr_admin), session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    target = (payload.status if payload else PolicyLifecycleStatus.UNDER_REVIEW.value).lower()
    if target not in (PolicyLifecycleStatus.UNDER_REVIEW.value, PolicyLifecycleStatus.DRAFT.value): raise AppError("Invalid review status: must be 'under_review' or 'draft'", 400, "INVALID_STATUS")
    version = (await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.id == version_id, PolicyVersion.policy_id == policy_id)))).scalar_one_or_none()
    if not version: raise AppError("Policy version not found", 404, "NOT_FOUND")
    try:
        version.transition_to(target); await _maybe_await(session.commit()); await _maybe_await(session.refresh(version))
    except ValueError as exc: raise AppError(str(exc), 400, "INVALID_TRANSITION") from exc
    return serialize_version(version)


@policies_router.post("/{policy_id}/versions/{version_id}/publish", status_code=200)
async def publish_policy_version(policy_id: uuid.UUID, version_id: uuid.UUID, payload: Optional[PublishPolicyRequest] = None, current_user: AuthenticatedUser = Depends(require_hr_admin), session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    version = (await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.id == version_id, PolicyVersion.policy_id == policy_id)))).scalar_one_or_none()
    if not version: raise AppError("Policy version not found", 404, "NOT_FOUND")
    if version.processing_status != ProcessingStatus.COMPLETED.value: raise AppError("Cannot publish unprocessed policy document", 400, "UNPROCESSED_DOCUMENT")
    ef_from = payload.effective_from if payload and payload.effective_from is not None else version.effective_from
    ef_to = payload.effective_to if payload and payload.effective_to is not None else version.effective_to
    if ef_from and ef_to and ef_to < ef_from: raise AppError("effective_to cannot be earlier than effective_from", 400, "INVALID_EFFECTIVE_DATES")
    try:
        version.effective_from, version.effective_to = ef_from, ef_to
        version.transition_to(PolicyLifecycleStatus.PUBLISHED, published_by=current_user.user.id)
    except ValueError as exc: raise AppError(str(exc), 400, "INVALID_TRANSITION") from exc
    priors = (await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.policy_id == policy_id, PolicyVersion.id != version.id, PolicyVersion.status == PolicyLifecycleStatus.PUBLISHED.value)))).scalars().all()
    for prior in priors: prior.transition_to(PolicyLifecycleStatus.ARCHIVED)
    await _maybe_await(session.commit()); await _maybe_await(session.refresh(version))
    return serialize_version(version)


@policies_router.post("/{policy_id}/versions/{version_id}/archive", status_code=200)
async def archive_policy_version(policy_id: uuid.UUID, version_id: uuid.UUID, _: AuthenticatedUser = Depends(require_hr_admin), session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    version = (await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.id == version_id, PolicyVersion.policy_id == policy_id)))).scalar_one_or_none()
    if not version: raise AppError("Policy version not found", 404, "NOT_FOUND")
    try:
        version.transition_to(PolicyLifecycleStatus.ARCHIVED); await _maybe_await(session.commit()); await _maybe_await(session.refresh(version))
    except ValueError as exc: raise AppError(str(exc), 400, "INVALID_TRANSITION") from exc
    return serialize_version(version)


@policies_router.post("/{policy_id}/versions/{version_id}/process", status_code=200)
async def process_policy_version(policy_id: uuid.UUID, version_id: uuid.UUID, _: AuthenticatedUser = Depends(require_hr_admin), session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    return await policy_processing_workflow.process_version(session, version_id)
