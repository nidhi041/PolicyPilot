"""Tests for policy listing, filtering, detail, review, publication, replacement, and archival."""
from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid
from fastapi.testclient import TestClient
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import AuthenticatedUser, ProfileInfo, UserInfo, get_current_user
from app.config import get_settings
from app.db.models import Base, Policy, PolicyLifecycleStatus, PolicyVersion, ProcessingStatus, UserRole
from app.main import create_app
from app.policies import get_db_session


@pytest.fixture
def test_db():
    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.connect() as conn: conn.execute(sa.text("PRAGMA foreign_keys=ON;"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(sa.text("PRAGMA foreign_keys=ON;"))
        yield session
    Base.metadata.drop_all(engine)


def make_user(role: str = UserRole.HR_ADMINISTRATOR.value, region: str = "US") -> AuthenticatedUser:
    uid = uuid.uuid4()
    return AuthenticatedUser(user=UserInfo(id=uid, email=f"{role}@test.com"), profile=ProfileInfo(id=uuid.uuid4(), user_id=uid, role=role, region=region, is_hr_administrator=(role == UserRole.HR_ADMINISTRATOR.value)))


def create_client(test_db, monkeypatch, user: AuthenticatedUser) -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co"); monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_list_and_filter_policies_by_role_and_region(test_db, monkeypatch):
    p_us, p_eu, p_gl = Policy(title="US Safety", category="Safety", region="US"), Policy(title="EU Privacy", category="Privacy", region="EU"), Policy(title="Global Conduct", category="Ethics", region="GLOBAL")
    test_db.add_all([p_us, p_eu, p_gl])
    test_db.add_all([
        PolicyVersion(policy_id=p_us.id, version_label="1.0", status=PolicyLifecycleStatus.PUBLISHED.value, processing_status=ProcessingStatus.COMPLETED.value, storage_path="/u.pdf", content_hash="h1"),
        PolicyVersion(policy_id=p_eu.id, version_label="1.0", status=PolicyLifecycleStatus.PUBLISHED.value, processing_status=ProcessingStatus.COMPLETED.value, storage_path="/e.pdf", content_hash="h2"),
        PolicyVersion(policy_id=p_gl.id, version_label="1.0", status=PolicyLifecycleStatus.DRAFT.value, processing_status=ProcessingStatus.COMPLETED.value, storage_path="/g.pdf", content_hash="h3"),
    ])
    test_db.commit()

    emp_res = create_client(test_db, monkeypatch, make_user(UserRole.EMPLOYEE.value, region="US")).get("/api/v1/policies")
    assert emp_res.status_code == 200 and [p["title"] for p in emp_res.json()] == ["US Safety"]

    hr_client = create_client(test_db, monkeypatch, make_user(UserRole.HR_ADMINISTRATOR.value))
    assert len(hr_client.get("/api/v1/policies").json()) == 3
    assert len(hr_client.get("/api/v1/policies?category=Safety").json()) == 1
    assert len(hr_client.get("/api/v1/policies?region=EU").json()) == 1
    assert len(hr_client.get("/api/v1/policies?search=Conduct").json()) == 1
    assert len(hr_client.get("/api/v1/policies?status=draft").json()) == 1


def test_get_policy_detail_authorization(test_db, monkeypatch):
    pol = Policy(title="Leave", category="Leave", region="US")
    test_db.add(pol)
    test_db.add_all([
        PolicyVersion(policy_id=pol.id, version_label="1.0", status=PolicyLifecycleStatus.PUBLISHED.value, processing_status=ProcessingStatus.COMPLETED.value, storage_path="/p1.pdf", content_hash="h1"),
        PolicyVersion(policy_id=pol.id, version_label="2.0", status=PolicyLifecycleStatus.DRAFT.value, processing_status=ProcessingStatus.PENDING.value, storage_path="/p2.pdf", content_hash="h2"),
    ])
    test_db.commit()

    assert create_client(test_db, monkeypatch, make_user(UserRole.EMPLOYEE.value, region="UK")).get(f"/api/v1/policies/{pol.id}").status_code == 403
    emp_res = create_client(test_db, monkeypatch, make_user(UserRole.EMPLOYEE.value, region="US")).get(f"/api/v1/policies/{pol.id}")
    assert emp_res.status_code == 200 and len(emp_res.json()["versions"]) == 1 and emp_res.json()["versions"][0]["version_label"] == "1.0"
    hr_res = create_client(test_db, monkeypatch, make_user(UserRole.HR_ADMINISTRATOR.value)).get(f"/api/v1/policies/{pol.id}")
    assert hr_res.status_code == 200 and len(hr_res.json()["versions"]) == 2


def test_review_and_archive_endpoints(test_db, monkeypatch):
    pol = Policy(title="Remote", category="IT", region="GLOBAL")
    v = PolicyVersion(policy_id=pol.id, version_label="1.0", status=PolicyLifecycleStatus.DRAFT.value, processing_status=ProcessingStatus.COMPLETED.value, storage_path="/r.pdf", content_hash="h")
    test_db.add_all([pol, v]); test_db.commit()

    emp_client = create_client(test_db, monkeypatch, make_user(UserRole.EMPLOYEE.value))
    assert emp_client.post(f"/api/v1/policies/{pol.id}/versions/{v.id}/review").status_code == 403
    assert emp_client.post(f"/api/v1/policies/{pol.id}/versions/{v.id}/archive").status_code == 403

    hr_client = create_client(test_db, monkeypatch, make_user(UserRole.HR_ADMINISTRATOR.value))
    res_rev = hr_client.post(f"/api/v1/policies/{pol.id}/versions/{v.id}/review", json={"status": "under_review"})
    assert res_rev.status_code == 200 and res_rev.json()["status"] == "under_review"

    res_arch = hr_client.post(f"/api/v1/policies/{pol.id}/versions/{v.id}/archive")
    assert res_arch.status_code == 200 and res_arch.json()["status"] == "archived"

    res_bad = hr_client.post(f"/api/v1/policies/{pol.id}/versions/{v.id}/review", json={"status": "under_review"})
    assert res_bad.status_code == 400 and res_bad.json()["error"]["code"] == "INVALID_TRANSITION"


def test_publish_enforces_processing_dates_and_archives_prior(test_db, monkeypatch):
    hr_client = create_client(test_db, monkeypatch, make_user(UserRole.HR_ADMINISTRATOR.value))
    pol = Policy(title="Benefits", category="HR", region="GLOBAL")
    v_old = PolicyVersion(policy_id=pol.id, version_label="1.0", status=PolicyLifecycleStatus.PUBLISHED.value, processing_status=ProcessingStatus.COMPLETED.value, storage_path="/b1.pdf", content_hash="h1")
    v_new = PolicyVersion(policy_id=pol.id, version_label="2.0", status=PolicyLifecycleStatus.UNDER_REVIEW.value, processing_status=ProcessingStatus.PENDING.value, storage_path="/b2.pdf", content_hash="h2")
    test_db.add_all([pol, v_old, v_new]); test_db.commit()

    res_unproc = hr_client.post(f"/api/v1/policies/{pol.id}/versions/{v_new.id}/publish")
    assert res_unproc.status_code == 400 and res_unproc.json()["error"]["code"] == "UNPROCESSED_DOCUMENT"

    v_new.processing_status = ProcessingStatus.COMPLETED.value; test_db.commit()

    res_bad_dates = hr_client.post(f"/api/v1/policies/{pol.id}/versions/{v_new.id}/publish", json={"effective_from": datetime.now(timezone.utc).isoformat(), "effective_to": datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()})
    assert res_bad_dates.status_code == 400 and res_bad_dates.json()["error"]["code"] == "INVALID_EFFECTIVE_DATES"

    res_pub = hr_client.post(f"/api/v1/policies/{pol.id}/versions/{v_new.id}/publish")
    assert res_pub.status_code == 200 and res_pub.json()["status"] == "published" and res_pub.json()["published_at"] is not None
    test_db.refresh(v_old)
    assert v_old.status == "archived"


def test_replace_version_endpoint(test_db, monkeypatch):
    hr_client = create_client(test_db, monkeypatch, make_user(UserRole.HR_ADMINISTRATOR.value))
    pol = Policy(title="Expenses", category="Finance", region="GLOBAL")
    v1 = PolicyVersion(policy_id=pol.id, version_label="1.0", status=PolicyLifecycleStatus.PUBLISHED.value, processing_status=ProcessingStatus.COMPLETED.value, storage_path="/e1.pdf", content_hash="h1")
    test_db.add_all([pol, v1]); test_db.commit()

    pdf = b"%PDF-1.4 new version content"
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json={"Key": "k"}))):
        res_dup = hr_client.post(f"/api/v1/policies/{pol.id}/versions", data={"version_label": "1.0"}, files={"file": ("v.pdf", pdf, "application/pdf")})
        assert res_dup.status_code == 409 and res_dup.json()["error"]["code"] == "DUPLICATE_VERSION"

        res = hr_client.post(f"/api/v1/policies/{pol.id}/versions", data={"version_label": "1.1"}, files={"file": ("v.pdf", pdf, "application/pdf")})
        assert res.status_code == 201 and res.json()["version_label"] == "1.1" and res.json()["status"] == "draft"

    test_db.refresh(v1)
    assert v1.status == "published"
