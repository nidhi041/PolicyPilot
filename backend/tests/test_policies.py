"""Unit, validation, relationship, and migration tests for policies and policy_versions."""
from __future__ import annotations
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import uuid
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models import Base, Policy, PolicyLifecycleStatus, PolicyVersion, Region


@pytest.fixture
def sqlite_engine():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


def test_policy_defaults_and_validation():
    p = Policy(title="Remote Work Policy", category="Workplace")
    assert p.title == "Remote Work Policy" and p.category == "Workplace" and p.region == Region.GLOBAL.value
    assert isinstance(p.id, uuid.UUID)

    for bad_title in ["", "   ", None]:
        with pytest.raises(ValueError, match="title cannot be empty"):
            Policy(title=bad_title, category="Workplace")

    with pytest.raises(ValueError, match="Invalid region"):
        Policy(title="Valid", category="Workplace", region="INVALID_REGION")


def test_policy_version_defaults_and_validation():
    pid = uuid.uuid4()
    pv = PolicyVersion(policy_id=pid, version_label="1.0", storage_path="/p/1.0.pdf", content_hash="hash123")
    assert pv.status == "draft" and pv.published_at is None and pv.published_by is None

    with pytest.raises(ValueError, match="Invalid status"):
        PolicyVersion(policy_id=pid, version_label="1.0", storage_path="/p.pdf", content_hash="h", status="invalid_status")


def test_effective_dates_validation():
    pid = uuid.uuid4()
    earlier, later = datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc)
    pv = PolicyVersion(policy_id=pid, version_label="1.0", storage_path="/p.pdf", content_hash="h", effective_from=earlier, effective_to=later)
    assert pv.effective_from == earlier and pv.effective_to == later

    with pytest.raises(ValueError, match="effective_to cannot be earlier"):
        PolicyVersion(policy_id=pid, version_label="1.0", storage_path="/p.pdf", content_hash="h", effective_from=later, effective_to=earlier)


def test_lifecycle_status_transitions():
    pv = PolicyVersion(policy_id=uuid.uuid4(), version_label="1.0", storage_path="/p.pdf", content_hash="h")
    assert pv.status == "draft"

    # Invalid jump draft -> published
    with pytest.raises(ValueError, match="Invalid transition from draft to published"):
        pv.transition_to(PolicyLifecycleStatus.PUBLISHED)

    # Valid transitions: draft -> under_review -> published -> archived
    pv.transition_to(PolicyLifecycleStatus.UNDER_REVIEW)
    assert pv.status == "under_review"

    pub_user = uuid.uuid4()
    pv.transition_to(PolicyLifecycleStatus.PUBLISHED, published_by=pub_user)
    assert pv.status == "published" and pv.published_by == pub_user and pv.published_at is not None

    pv.transition_to(PolicyLifecycleStatus.ARCHIVED)
    assert pv.status == "archived"

    # Invalid: cannot transition from archived
    with pytest.raises(ValueError, match="Invalid transition from archived"):
        pv.transition_to(PolicyLifecycleStatus.PUBLISHED)


def test_db_persistence_and_relationships(sqlite_engine):
    with Session(sqlite_engine) as session:
        pol = Policy(title="Leave Policy", category="Leave", region="US")
        pol.versions.extend([
            PolicyVersion(version_label="1.0", storage_path="/leave/1.0.pdf", content_hash="h1"),
            PolicyVersion(version_label="1.1", storage_path="/leave/1.1.pdf", content_hash="h2"),
        ])
        session.add(pol)
        session.commit()

        queried = session.query(Policy).filter_by(title="Leave Policy").one()
        assert {v.version_label for v in queried.versions} == {"1.0", "1.1"}

        # Duplicate version label for same policy raises IntegrityError
        session.add(PolicyVersion(policy_id=pol.id, version_label="1.0", storage_path="/p.pdf", content_hash="h3"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Cascade delete
        session.delete(queried)
        session.commit()
        assert session.query(PolicyVersion).count() == 0


def test_migration_upgrade_and_downgrade():
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "20261019_001_create_policies_and_versions.py"
    spec = importlib.util.spec_from_file_location("migration_002", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()
        inspector = sa.inspect(conn)
        assert {"policies", "policy_versions"}.issubset(set(inspector.get_table_names()))
        p_cols = {c["name"] for c in inspector.get_columns("policies")}
        assert {"id", "title", "category", "region", "created_at", "updated_at"}.issubset(p_cols)
        pv_cols = {c["name"] for c in inspector.get_columns("policy_versions")}
        assert {"id", "policy_id", "version_label", "status", "effective_from", "effective_to", "storage_path", "content_hash", "published_at", "published_by"}.issubset(pv_cols)

        with Operations.context(ctx):
            migration.downgrade()
        assert "policies" not in sa.inspect(conn).get_table_names()
