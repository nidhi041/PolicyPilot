"""Unit, integration, and migration verification tests for the profiles schema."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import uuid
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models import Base, Profile, Region, UserRole


def test_default_profile_safe_role():
    uid = uuid.uuid4()
    p = Profile(user_id=uid)
    assert p.user_id == uid and isinstance(p.id, uuid.UUID)
    assert p.role == UserRole.EMPLOYEE.value and p.region == Region.GLOBAL.value
    assert p.is_hr_administrator is False


def test_hr_administrator_role_explicit():
    p = Profile(user_id=uuid.uuid4(), role=UserRole.HR_ADMINISTRATOR)
    assert p.role == "hr_administrator" and p.is_hr_administrator is True


@pytest.mark.parametrize("role", ["employee", "hr_administrator", UserRole.EMPLOYEE, UserRole.HR_ADMINISTRATOR])
def test_valid_roles(role):
    p = Profile(user_id=uuid.uuid4(), role=role)
    assert p.role == (role.value if isinstance(role, UserRole) else role)


@pytest.mark.parametrize("invalid_role", ["admin", "superadmin", "manager", "hr", "", 123, None])
def test_invalid_roles_rejected(invalid_role):
    with pytest.raises(ValueError, match="Invalid role"):
        Profile(user_id=uuid.uuid4(), role=invalid_role)


@pytest.mark.parametrize("region", ["GLOBAL", "US", "EU", "UK", "APAC", "EMEA", "CA", "LATAM", "IN", "us"])
def test_valid_regions(region):
    p = Profile(user_id=uuid.uuid4(), region=region)
    assert p.region == (region.upper() if isinstance(region, str) else region)


@pytest.mark.parametrize("invalid_region", ["MARS", "ATLANTIS", "invalid", "", 123, None])
def test_invalid_regions_rejected(invalid_region):
    with pytest.raises(ValueError, match="Invalid region"):
        Profile(user_id=uuid.uuid4(), region=invalid_region)


def test_user_id_validation():
    uid_str = "12345678-1234-5678-1234-567812345678"
    assert Profile(user_id=uid_str).user_id == uuid.UUID(uid_str)
    for bad in ["not-a-uuid", 123, None]:
        with pytest.raises(ValueError, match="Invalid user_id"):
            Profile(user_id=bad)


@pytest.fixture
def sqlite_engine():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


def test_db_persistence_and_unique_user_id(sqlite_engine):
    uid = uuid.uuid4()
    with Session(sqlite_engine) as session:
        session.add(Profile(user_id=uid, role="employee", region="US"))
        session.commit()
        q = session.query(Profile).filter_by(user_id=uid).one()
        assert q.role == "employee" and q.region == "US" and not q.is_hr_administrator

    with Session(sqlite_engine) as session:
        session.add(Profile(user_id=uid, role="hr_administrator", region="UK"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_db_check_constraints(sqlite_engine):
    with sqlite_engine.connect() as conn:
        for bad_role, bad_reg in [("admin", "US"), ("employee", "INVALID")]:
            with pytest.raises(IntegrityError):
                conn.execute(sa.text(f"INSERT INTO profiles (id, user_id, role, region, created_at, updated_at) VALUES ('1', '2', '{bad_role}', '{bad_reg}', '2026-01-01', '2026-01-01')"))


def test_migration_upgrade_and_downgrade():
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "20261015_001_create_profiles.py"
    spec = importlib.util.spec_from_file_location("migration_001", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()
        inspector = sa.inspect(conn)
        assert "profiles" in inspector.get_table_names()
        cols = {c["name"] for c in inspector.get_columns("profiles")}
        assert {"id", "user_id", "role", "region", "created_at", "updated_at"}.issubset(cols)

        with Operations.context(ctx):
            migration.downgrade()
        assert "profiles" not in sa.inspect(conn).get_table_names()
