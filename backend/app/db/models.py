"""Database models for PolicyPilot."""
from __future__ import annotations
from datetime import datetime, timezone
import enum
from typing import Any, Optional
import uuid
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates
from pgvector.sqlalchemy import Vector


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


class PolicyLifecycleStatus(str, enum.Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"under_review", "archived"},
    "under_review": {"draft", "published", "archived"},
    "published": {"archived"},
    "archived": set(),
}


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        sa.CheckConstraint("region IN ('GLOBAL', 'US', 'EU', 'UK', 'APAC', 'EMEA', 'CA', 'LATAM', 'IN')", name="ck_policies_region"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    category: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    region: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=Region.GLOBAL.value, server_default=sa.text("'GLOBAL'"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=sa.func.now(), onupdate=lambda: datetime.now(timezone.utc))

    versions: Mapped[list[PolicyVersion]] = relationship("PolicyVersion", back_populates="policy", cascade="all, delete-orphan", order_by="desc(PolicyVersion.created_at)")

    def __init__(self, **kwargs: Any) -> None:
        defaults = {"id": uuid.uuid4(), "region": Region.GLOBAL.value, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
        super().__init__(**{**defaults, **kwargs})

    @validates("region")
    def validate_region(self, key: str, value: Any) -> str:
        val = value.value if isinstance(value, Region) else (value.upper() if isinstance(value, str) else None)
        if val not in Region._value2member_map_:
            raise ValueError(f"Invalid region: {value!r}")
        return val

    @validates("title")
    def validate_title(self, key: str, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Policy title cannot be empty")
        return value.strip()


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = (
        sa.UniqueConstraint("policy_id", "version_label", name="uq_policy_versions_policy_id_version_label"),
        sa.CheckConstraint("status IN ('draft', 'under_review', 'published', 'archived')", name="ck_policy_versions_status"),
        sa.CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_policy_versions_effective_dates"),
        sa.CheckConstraint("processing_status IN ('pending', 'processing', 'completed', 'failed')", name="ck_policy_versions_processing_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=PolicyLifecycleStatus.DRAFT.value, server_default=sa.text("'draft'"))
    processing_status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=ProcessingStatus.PENDING.value, server_default=sa.text("'pending'"))
    processing_error: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    storage_path: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    published_by: Mapped[Optional[uuid.UUID]] = mapped_column(sa.Uuid(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=sa.func.now(), onupdate=lambda: datetime.now(timezone.utc))

    policy: Mapped[Policy] = relationship("Policy", back_populates="versions")
    chunks: Mapped[list[PolicyChunk]] = relationship("PolicyChunk", back_populates="version", cascade="all, delete-orphan", order_by="PolicyChunk.chunk_index")

    def __init__(self, **kwargs: Any) -> None:
        defaults = {
            "id": uuid.uuid4(),
            "status": PolicyLifecycleStatus.DRAFT.value,
            "processing_status": ProcessingStatus.PENDING.value,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        super().__init__(**{**defaults, **kwargs})

    @validates("status")
    def validate_status(self, key: str, value: Any) -> str:
        val = value.value if isinstance(value, PolicyLifecycleStatus) else value
        if not isinstance(val, str) or val not in PolicyLifecycleStatus._value2member_map_:
            raise ValueError(f"Invalid status: {value!r}")
        return val

    @validates("processing_status")
    def validate_processing_status(self, key: str, value: Any) -> str:
        val = value.value if isinstance(value, ProcessingStatus) else value
        if not isinstance(val, str) or val not in ProcessingStatus._value2member_map_:
            raise ValueError(f"Invalid processing_status: {value!r}")
        return val

    @validates("effective_from", "effective_to")
    def validate_dates(self, key: str, value: Any) -> Optional[datetime]:
        if key == "effective_to" and value is not None and self.effective_from is not None and value < self.effective_from:
            raise ValueError("effective_to cannot be earlier than effective_from")
        if key == "effective_from" and value is not None and self.effective_to is not None and value > self.effective_to:
            raise ValueError("effective_from cannot be later than effective_to")
        return value

    def transition_to(self, new_status: PolicyLifecycleStatus | str, published_by: Optional[uuid.UUID] = None, published_at: Optional[datetime] = None) -> None:
        target = new_status.value if isinstance(new_status, PolicyLifecycleStatus) else new_status
        if target not in PolicyLifecycleStatus._value2member_map_:
            raise ValueError(f"Invalid status: {new_status!r}")
        if target not in VALID_STATUS_TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Invalid transition from {self.status} to {target}")
        self.status = target
        if target == PolicyLifecycleStatus.PUBLISHED.value:
            self.published_at = published_at or datetime.now(timezone.utc)
            if published_by:
                self.published_by = published_by
        self.updated_at = datetime.now(timezone.utc)


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    __table_args__ = (
        sa.UniqueConstraint("policy_version_id", "chunk_index", name="uq_policy_chunks_version_chunk_index"),
        sa.CheckConstraint("page_number >= 1", name="ck_policy_chunks_page_number"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_policy_chunks_chunk_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), sa.ForeignKey("policy_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    char_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=sa.func.now())

    version: Mapped[PolicyVersion] = relationship("PolicyVersion", back_populates="chunks")

    def __init__(self, **kwargs: Any) -> None:
        defaults = {"id": uuid.uuid4(), "created_at": datetime.now(timezone.utc)}
        super().__init__(**{**defaults, **kwargs})

