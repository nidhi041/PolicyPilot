"""Supabase Auth verification and profile association."""
from __future__ import annotations
from collections.abc import AsyncGenerator
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.db.models import Profile, Region, UserRole
from app.db.session import get_session
from app.errors import AppError


class AuthError(AppError):
    def __init__(self, message: str, code: str = "INVALID_TOKEN", status_code: int = 401) -> None:
        super().__init__(message=message, status_code=status_code, code=code)


class UserInfo(BaseModel):
    id: uuid.UUID
    email: Optional[str] = None


class ProfileInfo(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    region: str
    is_hr_administrator: bool


class AuthenticatedUser(BaseModel):
    user: UserInfo
    profile: ProfileInfo


AuthMeResponse = AuthenticatedUser
bearer_scheme = HTTPBearer(auto_error=False)


async def get_auth_session() -> AsyncGenerator[Optional[AsyncSession], None]:
    if get_settings().database_url:
        async for s in get_session():
            yield s
    else:
        yield None


async def verify_supabase_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_url:
        raise AuthError("Authentication service unconfigured", "AUTH_UNCONFIGURED", 503)
    key = settings.supabase_anon_key.get_secret_value() if settings.supabase_anon_key else (
        settings.supabase_service_role_key.get_secret_value() if settings.supabase_service_role_key else ""
    )
    headers = {"Authorization": f"Bearer {token}", **({"apikey": key} if key else {})}
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except Exception:
        raise AuthError("Authentication service unavailable", "AUTH_UNAVAILABLE", 503)
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, dict) and "id" in data:
            return data
        raise AuthError("Invalid user payload from auth provider", "INVALID_TOKEN", 401)
    if "expired" in resp.text.lower():
        raise AuthError("Authentication token has expired", "EXPIRED_TOKEN", 401)
    raise AuthError("Invalid authentication credentials", "INVALID_TOKEN", 401)


async def get_or_create_profile(user_id: uuid.UUID, session: AsyncSession) -> Profile:
    res = await session.execute(select(Profile).where(Profile.user_id == user_id))
    profile = res.scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=user_id, role=UserRole.EMPLOYEE.value, region=Region.GLOBAL.value)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: Optional[AsyncSession] = Depends(get_auth_session),
) -> AuthenticatedUser:
    if not request.headers.get("authorization"):
        raise AuthError("Missing authentication credentials", "MISSING_CREDENTIALS", 401)
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AuthError("Invalid authentication scheme", "INVALID_CREDENTIALS", 401)
    data = await verify_supabase_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(data["id"]))
    except (ValueError, KeyError):
        raise AuthError("Invalid user identity in token", "INVALID_TOKEN", 401)
    if session is None:
        raise AppError("Database service unconfigured", 503, "DATABASE_UNCONFIGURED")
    p = await get_or_create_profile(user_id, session)
    return AuthenticatedUser(
        user=UserInfo(id=user_id, email=data.get("email")),
        profile=ProfileInfo(id=p.id, user_id=p.user_id, role=p.role, region=p.region, is_hr_administrator=p.is_hr_administrator),
    )


async def require_authenticated_user(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    return current_user


async def require_employee(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if current_user.profile.role not in (UserRole.EMPLOYEE.value, UserRole.HR_ADMINISTRATOR.value):
        raise AppError("Forbidden: Employee access required", 403, "FORBIDDEN")
    return current_user


async def require_hr_admin(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if not current_user.profile.is_hr_administrator:
        raise AppError("Forbidden: HR Administrator access required", 403, "FORBIDDEN")
    return current_user


require_hr_administrator = require_hr_admin


def require_roles(*roles: str | UserRole):
    allowed = {r.value if isinstance(r, UserRole) else str(r) for r in roles}

    async def _role_checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if current_user.profile.role not in allowed:
            raise AppError("Forbidden: Insufficient permissions", 403, "FORBIDDEN")
        return current_user

    return _role_checker


auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.get("/me", response_model=AuthMeResponse)
async def get_me(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthMeResponse:
    return AuthMeResponse(user=current_user.user, profile=current_user.profile)
