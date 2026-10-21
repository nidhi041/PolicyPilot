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


def test_conversation_persistence_and_user_ownership(test_db, monkeypatch):
    client_a = create_client(test_db, monkeypatch, make_user())
    client_b = create_client(test_db, monkeypatch, make_user())

    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        res = client_a.post("/api/v1/chat", json={"message": "What is company policy?"})
    assert res.status_code == 200
    conv_id = res.json()["conversation_id"]

    list_a = client_a.get("/api/v1/conversations").json()
    assert len(list_a) == 1 and list_a[0]["id"] == conv_id

    detail_a = client_a.get(f"/api/v1/conversations/{conv_id}").json()
    assert detail_a["id"] == conv_id and len(detail_a["messages"]) == 2
    assert [m["role"] for m in detail_a["messages"]] == ["user", "assistant"]

    assert client_b.get("/api/v1/conversations").json() == []
    assert client_b.get(f"/api/v1/conversations/{conv_id}").status_code == 403

    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        append_res = client_b.post("/api/v1/chat", json={"message": "Hacking?", "conversation_id": conv_id})
    assert append_res.status_code == 403


def test_chat_feedback_persistence_and_ownership(test_db, monkeypatch):
    user_a = make_user()
    user_b = make_user()
    client_a = create_client(test_db, monkeypatch, user_a)
    client_b = create_client(test_db, monkeypatch, user_b)

    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.01] * 768])):
        chat_res = client_a.post("/api/v1/chat", json={"message": "Tell me about parental leave"})
    assert chat_res.status_code == 200
    conv_id = chat_res.json()["conversation_id"]
    asst_msg_id = chat_res.json()["message_id"]
    assert asst_msg_id is not None

    conv_detail = client_a.get(f"/api/v1/conversations/{conv_id}").json()
    user_msg_id = [m["id"] for m in conv_detail["messages"] if m["role"] == "user"][0]

    # 1. Unauthenticated rating fails
    client_anon = create_client(test_db, monkeypatch)
    assert client_anon.post(f"/api/v1/chat/messages/{asst_msg_id}/feedback", json={"rating": "up"}).status_code == 401

    # 2. Invalid rating values fail
    for invalid_rating in ["", "super", "5-stars", "neutral"]:
        res_inv = client_a.post(f"/api/v1/chat/messages/{asst_msg_id}/feedback", json={"rating": invalid_rating})
        assert res_inv.status_code == 400

    # 3. Nonexistent message fails
    fake_msg_id = uuid.uuid4()
    assert client_a.post(f"/api/v1/chat/messages/{fake_msg_id}/feedback", json={"rating": "up"}).status_code == 404

    # 4. Rating a user role message fails
    res_user_msg = client_a.post(f"/api/v1/chat/messages/{user_msg_id}/feedback", json={"rating": "up"})
    assert res_user_msg.status_code == 400

    # 5. Ownership violation: User B cannot rate User A's answer
    res_steal = client_b.post(f"/api/v1/chat/messages/{asst_msg_id}/feedback", json={"rating": "down"})
    assert res_steal.status_code == 403

    # 6. User A rates their answer "up"
    res_fb1 = client_a.post(f"/api/v1/chat/messages/{asst_msg_id}/feedback", json={"rating": "up"})
    assert res_fb1.status_code == 200
    fb_data = res_fb1.json()
    assert fb_data["rating"] == "up"
    assert fb_data["message_id"] == asst_msg_id
    assert fb_data["user_id"] == str(user_a.user.id)

    # 7. Verify feedback is reflected in conversation detail
    detail_with_fb = client_a.get(f"/api/v1/conversations/{conv_id}").json()
    asst_msg_item = [m for m in detail_with_fb["messages"] if m["id"] == asst_msg_id][0]
    assert asst_msg_item["feedback"] == "up"

    # 8. User A updates their rating to "down" (upsert modification)
    res_fb2 = client_a.post(f"/api/v1/chat/messages/{asst_msg_id}/feedback", json={"rating": "down"})
    assert res_fb2.status_code == 200
    assert res_fb2.json()["rating"] == "down"
    assert res_fb2.json()["id"] == fb_data["id"]

    detail_updated = client_a.get(f"/api/v1/conversations/{conv_id}").json()
    asst_msg_updated = [m for m in detail_updated["messages"] if m["id"] == asst_msg_id][0]
    assert asst_msg_updated["feedback"] == "down"

    # 9. User B still sees no access or modification rights
    assert client_b.post(f"/api/v1/chat/messages/{asst_msg_id}/feedback", json={"rating": "up"}).status_code == 403

