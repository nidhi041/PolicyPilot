"""Database models for PolicyPilot."""
from __future__ import annotations
from datetime import datetime, timezone
import enum
from typing import Any
import uuid
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    EMPLOYEE = "employee"
    HR_ADMINISTRATOR = "hr_administrator"


class Region(str, enum.Enum):
    GLOBAL = "GLOBAL"
    US = "US"
    EU = "EU"
    UK = "UK"
    APAC = "APAC"
    EMEA = "EMEA"
    CA = "CA"
    LATAM = "LATAM"
    IN = "IN"


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        sa.CheckConstraint("role IN ('employee', 'hr_administrator')", name="ck_profiles_role"),
        sa.CheckConstraint("region IN ('GLOBAL', 'US', 'EU', 'UK', 'APAC', 'EMEA', 'CA', 'LATAM', 'IN')", name="ck_profiles_region"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=UserRole.EMPLOYEE.value, server_default=sa.text("'employee'"))
    region: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=Region.GLOBAL.value, server_default=sa.text("'GLOBAL'"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=sa.func.now(), onupdate=lambda: datetime.now(timezone.utc))

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("role", UserRole.EMPLOYEE.value)
        kwargs.setdefault("region", Region.GLOBAL.value)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        kwargs.setdefault("updated_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    @validates("role")
    def validate_role(self, key: str, value: Any) -> str:
        val = value.value if isinstance(value, UserRole) else value
        if not isinstance(val, str) or val not in UserRole._value2member_map_:
            raise ValueError(f"Invalid role: {value!r}")
        return val

    @validates("region")
    def validate_region(self, key: str, value: Any) -> str:
        val = value.value if isinstance(value, Region) else (value.upper() if isinstance(value, str) else None)
        if val not in Region._value2member_map_:
            raise ValueError(f"Invalid region: {value!r}")
        return val

    @validates("user_id")
    def validate_user_id(self, key: str, value: Any) -> uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            try:
                return uuid.UUID(value)
            except ValueError:
                pass
        raise ValueError(f"Invalid user_id: {value!r}")

    @property
    def is_hr_administrator(self) -> bool:
        return self.role == UserRole.HR_ADMINISTRATOR.value
