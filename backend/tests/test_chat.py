"""Integration tests for the authenticated POST /api/v1/chat endpoint."""
from __future__ import annotations
import json
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
from app.db.models import Base, Policy, PolicyChunk, PolicyLifecycleStatus, PolicyVersion, UserRole
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
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: test_db
    if user: app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def add_test_chunk(db: Session, title: str, region: str, text: str, page: int = 1, ver: str = "1.0"):
    p = Policy(title=title, category="General", region=region)
    v = PolicyVersion(policy_id=p.id, version_label=ver, status=PolicyLifecycleStatus.PUBLISHED.value, storage_path="/p.pdf", content_hash="h")
    c = PolicyChunk(policy_id=p.id, policy_version_id=v.id, page_number=page, chunk_index=0, text=text, char_count=len(text), embedding=[0.01] * 768)
    db.add_all([p, v, c]); db.commit()
    return p, v, c


def test_chat_access_violations_unauthenticated(test_db, monkeypatch):
    client = create_client(test_db, monkeypatch)
    assert client.post("/api/v1/chat", json={"message": "hello"}).status_code == 401


def test_chat_invalid_input(test_db, monkeypatch):
    client = create_client(test_db, monkeypatch, make_user())
    assert client.post("/api/v1/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/v1/chat", json={"message": "   "}).status_code == 400


def test_chat_success_with_verified_citations(test_db, monkeypatch):
    add_test_chunk(test_db, "Remote Work Policy", "US", "Employees in the US may work remotely 2 days per week with approval.")
    client = create_client(test_db, monkeypatch, make_user(region="US"))

    mock_llm = {
        "choices": [{"message": {"content": json.dumps({
            "answer": "Eligible US employees can work remotely 2 days per week.",
            "citations": [{"policy_title": "Remote Work Policy", "version": "1.0", "page_number": 1}],
        })}}]
    }

    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])), \
         patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json=mock_llm))):
        res = client.post("/api/v1/chat", json={"message": "What is the remote work policy?"})

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "answered" and data["is_grounded"] is True
    assert "2 days" in data["answer"]
    assert len(data["citations"]) == 1
    assert data["citations"][0]["policy_title"] == "Remote Work Policy"
    assert "conversation_id" in data


def test_chat_abstention_on_insufficient_evidence(test_db, monkeypatch):
    client = create_client(test_db, monkeypatch, make_user())
    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        res = client.post("/api/v1/chat", json={"message": "How do I claim gym allowance?"})

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "abstention" and data["is_grounded"] is False
    assert "Unable to answer" in data["answer"] or "insufficient" in data["answer"].lower()
    assert len(data["citations"]) == 0


def test_chat_abstention_on_fabricated_citation(test_db, monkeypatch):
    add_test_chunk(test_db, "Safety Rules", "GLOBAL", "Always wear safety glasses in warehouse areas.")
    client = create_client(test_db, monkeypatch, make_user())

    mock_llm = {
        "choices": [{"message": {"content": json.dumps({
            "answer": "Employees receive 50 days leave.",
            "citations": [{"policy_title": "Hallucinated Policy", "version": "9.9", "page_number": 99}],
        })}}]
    }

    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])), \
         patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json=mock_llm))):
        res = client.post("/api/v1/chat", json={"message": "Vacation rules?"})

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "abstention" and data["is_grounded"] is False
    assert len(data["citations"]) == 0
