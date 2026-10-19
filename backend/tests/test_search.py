"""Tests for semantic search retrieval over policy chunks with lifecycle and regional filters."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import uuid
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import AuthenticatedUser, ProfileInfo, UserInfo, get_current_user
from app.config import get_settings
from app.db.models import Base, Policy, PolicyChunk, PolicyLifecycleStatus, PolicyVersion, UserRole
from app.db.repository import policy_chunk_repo
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


def make_user(role: str = UserRole.EMPLOYEE.value, region: str = "US") -> AuthenticatedUser:
    uid = uuid.uuid4()
    return AuthenticatedUser(user=UserInfo(id=uid, email=f"{role}@test.com"), profile=ProfileInfo(id=uuid.uuid4(), user_id=uid, role=role, region=region, is_hr_administrator=(role == UserRole.HR_ADMINISTRATOR.value)))


def create_client(test_db, monkeypatch, user: AuthenticatedUser | None = None) -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co"); monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: test_db
    if user: app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def add_policy_with_chunk(db: Session, title: str, region: str, status: str, text: str, ef_from=None, ef_to=None, version_label="1.0") -> tuple[Policy, PolicyVersion, PolicyChunk]:
    pol = Policy(title=title, category="General", region=region)
    ver = PolicyVersion(policy_id=pol.id, version_label=version_label, status=status, storage_path=f"/{title}.pdf", content_hash="hash", effective_from=ef_from, effective_to=ef_to)
    chk = PolicyChunk(policy_id=pol.id, policy_version_id=ver.id, page_number=1, chunk_index=0, text=text, char_count=len(text), embedding=[0.01] * 768)
    db.add_all([pol, ver, chk]); db.commit()
    return pol, ver, chk


def test_search_authentication_and_query_validation(test_db, monkeypatch):
    client = create_client(test_db, monkeypatch)
    assert client.post("/api/v1/search", json={"query": "test"}).status_code == 401

    auth_client = create_client(test_db, monkeypatch, make_user())
    assert auth_client.post("/api/v1/search", json={"query": ""}).status_code == 422
    assert auth_client.post("/api/v1/search", json={"query": "   "}).status_code == 400


def test_search_excludes_draft_and_archived_policies(test_db, monkeypatch):
    add_policy_with_chunk(test_db, "Active Policy", "GLOBAL", PolicyLifecycleStatus.PUBLISHED.value, "Active published text")
    add_policy_with_chunk(test_db, "Draft Policy", "GLOBAL", PolicyLifecycleStatus.DRAFT.value, "Draft text")
    add_policy_with_chunk(test_db, "Archived Policy", "GLOBAL", PolicyLifecycleStatus.ARCHIVED.value, "Archived text")

    client = create_client(test_db, monkeypatch, make_user(region="US"))
    with patch("app.search.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        res = client.post("/api/v1/search", json={"query": "policy"})
    assert res.status_code == 200
    texts = [r["text"] for r in res.json()["results"]]
    assert texts == ["Active published text"]
    assert "Draft text" not in texts and "Archived text" not in texts


def test_search_excludes_expired_and_future_policies(test_db, monkeypatch):
    now = datetime.now(timezone.utc)
    add_policy_with_chunk(test_db, "Valid Policy", "GLOBAL", PolicyLifecycleStatus.PUBLISHED.value, "Valid current text", ef_from=now - timedelta(days=10), ef_to=now + timedelta(days=10))
    add_policy_with_chunk(test_db, "Expired Policy", "GLOBAL", PolicyLifecycleStatus.PUBLISHED.value, "Expired text", ef_to=now - timedelta(days=1))
    add_policy_with_chunk(test_db, "Future Policy", "GLOBAL", PolicyLifecycleStatus.PUBLISHED.value, "Future text", ef_from=now + timedelta(days=5))

    client = create_client(test_db, monkeypatch, make_user())
    with patch("app.search.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        res = client.post("/api/v1/search", json={"query": "rules"})
    assert res.status_code == 200
    texts = [r["text"] for r in res.json()["results"]]
    assert texts == ["Valid current text"]
    assert "Expired text" not in texts and "Future text" not in texts


def test_search_regional_scoping_and_applicable_policy_filter(test_db, monkeypatch):
    p_us, _, _ = add_policy_with_chunk(test_db, "US Health", "US", PolicyLifecycleStatus.PUBLISHED.value, "US text")
    add_policy_with_chunk(test_db, "Global Safety", "GLOBAL", PolicyLifecycleStatus.PUBLISHED.value, "Global text")
    add_policy_with_chunk(test_db, "UK Pension", "UK", PolicyLifecycleStatus.PUBLISHED.value, "UK text")

    # 1. US employee sees US and GLOBAL, but NOT UK
    emp_client = create_client(test_db, monkeypatch, make_user(UserRole.EMPLOYEE.value, region="US"))
    with patch("app.search.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        emp_res = emp_client.post("/api/v1/search", json={"query": "benefits"})
    assert emp_res.status_code == 200
    regions = {r["policy_region"] for r in emp_res.json()["results"]}
    assert regions == {"US", "GLOBAL"}

    # 2. Filter by specific applicable policy_id
    with patch("app.search.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        pol_res = emp_client.post("/api/v1/search", json={"query": "benefits", "policy_id": str(p_us.id)})
    assert pol_res.status_code == 200 and len(pol_res.json()["results"]) == 1
    assert pol_res.json()["results"][0]["policy_title"] == "US Health"

    # 3. GET /search works and returns metadata
    with patch("app.search.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        get_res = emp_client.get(f"/api/v1/search?query=benefits&policy_id={p_us.id}")
    assert get_res.status_code == 200
    r0 = get_res.json()["results"][0]
    assert r0["page_number"] == 1 and r0["version_label"] == "1.0" and "page_metadata" in r0

    # 4. HR Admin can see all regions
    hr_client = create_client(test_db, monkeypatch, make_user(UserRole.HR_ADMINISTRATOR.value, region="US"))
    with patch("app.search.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        hr_res = hr_client.post("/api/v1/search", json={"query": "all"})
    assert hr_res.status_code == 200 and len(hr_res.json()["results"]) == 3


def test_pgvector_sql_generation_and_order_by():
    q_emb = [0.05] * 768
    stmt = sa.select(PolicyChunk).order_by(PolicyChunk.embedding.cosine_distance(q_emb).asc())
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "<=>" in compiled and "policy_chunks.embedding" in compiled and "ORDER BY" in compiled
