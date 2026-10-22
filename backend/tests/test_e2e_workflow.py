"""End-to-end integration test suite covering the critical PolicyPilot workflow."""
from __future__ import annotations
import json
from unittest.mock import AsyncMock, patch
import uuid
from fastapi.testclient import TestClient
import httpx
import pymupdf
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import AuthenticatedUser, ProfileInfo, UserInfo, get_current_user
from app.config import get_settings
from app.db.models import Base, Profile, UserRole
from app.main import create_app
from app.policies import get_db_session

PARENTAL_LEAVE_PASSAGE = "Employees in the United States are entitled to 12 weeks of fully paid parental leave upon the birth or adoption of a child."


@pytest.fixture
def e2e_db():
    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.connect() as conn: conn.execute(sa.text("PRAGMA foreign_keys=ON;"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(sa.text("PRAGMA foreign_keys=ON;"))
        yield session
    Base.metadata.drop_all(engine)


def make_test_pdf(text: str = PARENTAL_LEAVE_PASSAGE) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def make_user(role: str = UserRole.EMPLOYEE.value, region: str = "US") -> AuthenticatedUser:
    uid = uuid.uuid4()
    return AuthenticatedUser(
        user=UserInfo(id=uid, email=f"{role}_{region}@test.com"),
        profile=ProfileInfo(id=uuid.uuid4(), user_id=uid, role=role, region=region, is_hr_administrator=(role == UserRole.HR_ADMINISTRATOR.value)),
    )


def create_client(db: Session, monkeypatch, user: AuthenticatedUser) -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co"); monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "secret"); get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_e2e_critical_policypilot_workflow(e2e_db, monkeypatch):
    """End-to-end verification of HR upload, processing, review, publication, employee chat, citations, abstention, and analytics."""
    hr_user = make_user(role=UserRole.HR_ADMINISTRATOR.value, region="GLOBAL")
    emp_us = make_user(role=UserRole.EMPLOYEE.value, region="US")
    emp_eu = make_user(role=UserRole.EMPLOYEE.value, region="EU")

    # Persist user profiles so analytics and scoped joins resolve
    e2e_db.add_all([
        Profile(id=hr_user.profile.id, user_id=hr_user.user.id, role="hr_administrator", region="GLOBAL"),
        Profile(id=emp_us.profile.id, user_id=emp_us.user.id, role="employee", region="US"),
        Profile(id=emp_eu.profile.id, user_id=emp_eu.user.id, role="employee", region="EU"),
    ])
    e2e_db.commit()

    hr_client = create_client(e2e_db, monkeypatch, hr_user)
    us_client = create_client(e2e_db, monkeypatch, emp_us)
    eu_client = create_client(e2e_db, monkeypatch, emp_eu)

    # 1. Employee cannot upload policies (least privilege / authorization check)
    pdf_bytes = make_test_pdf()
    res_deny_upload = us_client.post("/api/v1/policies", data={"title": "Hack", "category": "General", "region": "US", "version_label": "1.0"}, files={"file": ("p.pdf", pdf_bytes, "application/pdf")})
    assert res_deny_upload.status_code == 403

    # 2. HR Admin uploads policy and initial version
    with patch("app.policies.storage_service.upload_pdf", new=AsyncMock(return_value={"storage_path": "policies/us/leave.pdf", "content_hash": "hash123"})):
        res_upload = hr_client.post(
            "/api/v1/policies",
            data={"title": "US Parental Leave Policy", "category": "Leave", "region": "US", "version_label": "1.0"},
            files={"file": ("leave.pdf", pdf_bytes, "application/pdf")},
        )
    assert res_upload.status_code == 201
    pol_id = res_upload.json()["id"]
    ver_id = res_upload.json()["versions"][0]["id"]
    assert res_upload.json()["versions"][0]["status"] == "draft"
    assert res_upload.json()["versions"][0]["processing_status"] == "pending"

    # 3. Document processing workflow extracts chunks and embeddings
    with patch("app.workflow.storage_service.download_pdf", new=AsyncMock(return_value=pdf_bytes)), \
         patch("app.workflow.embedding_service.embed_chunks", new=AsyncMock(return_value=[[0.05] * 768])):
        res_proc = hr_client.post(f"/api/v1/policies/{pol_id}/versions/{ver_id}/process")
    assert res_proc.status_code == 200
    assert res_proc.json()["processing_status"] == "completed"
    assert res_proc.json()["chunks_count"] >= 1

    # 4. Review & Publication lifecycle
    res_rev = hr_client.post(f"/api/v1/policies/{pol_id}/versions/{ver_id}/review", json={"status": "under_review"})
    assert res_rev.status_code == 200 and res_rev.json()["status"] == "under_review"

    assert us_client.post(f"/api/v1/policies/{pol_id}/versions/{ver_id}/publish").status_code == 403
    res_pub = hr_client.post(f"/api/v1/policies/{pol_id}/versions/{ver_id}/publish")
    assert res_pub.status_code == 200 and res_pub.json()["status"] == "published"

    # 5. Cross-Region Access Denial: EU employee cannot view US policy detail
    assert eu_client.get(f"/api/v1/policies/{pol_id}").status_code == 403
    assert us_client.get(f"/api/v1/policies/{pol_id}").status_code == 200

    # 6. Employee Chat: Grounded Answer with Verified Citation
    mock_llm_answered = {
        "choices": [{"message": {"content": json.dumps({
            "answer": "US employees are entitled to 12 weeks of fully paid parental leave.",
            "citations": [{"policy_title": "US Parental Leave Policy", "version": "1.0", "page_number": 1, "quote": "12 weeks of fully paid parental leave"}],
        })}}]
    }
    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.05] * 768])), \
         patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json=mock_llm_answered))):
        chat_res = us_client.post("/api/v1/chat", json={"message": "How many weeks of parental leave do US employees get?"})

    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert chat_data["status"] == "answered"
    assert chat_data["is_grounded"] is True
    assert len(chat_data["citations"]) == 1
    assert chat_data["citations"][0]["policy_title"] == "US Parental Leave Policy"
    asst_msg_id = chat_data["message_id"]

    # 7. Feedback submission
    fb_res = us_client.post(f"/api/v1/chat/messages/{asst_msg_id}/feedback", json={"rating": "up"})
    assert fb_res.status_code == 200 and fb_res.json()["rating"] == "up"

    # 8. Employee Chat: Abstention on Out-of-Scope Query (no matching evidence)
    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.05] * 768])):
        abstain_res = us_client.post("/api/v1/chat", json={"message": "Does the company provide pet insurance?", "policy_id": str(uuid.uuid4())})
    assert abstain_res.status_code == 200
    assert abstain_res.json()["status"] == "abstention"
    assert abstain_res.json()["is_grounded"] is False
    assert len(abstain_res.json()["citations"]) == 0

    # 9. HR Analytics Verification & Authorization
    assert us_client.get("/api/v1/analytics/overview").status_code == 403
    analytics_res = hr_client.get("/api/v1/analytics/overview")
    assert analytics_res.status_code == 200
    metrics = analytics_res.json()

    assert metrics["question_volume"]["total_questions"] == 2
    assert metrics["question_volume"]["total_conversations"] >= 1
    assert metrics["answer_outcomes"]["grounded_answers_count"] == 1
    assert metrics["answer_outcomes"]["abstention_count"] == 1
    assert metrics["feedback_summary"]["positive_feedback_count"] == 1
    assert metrics["answer_outcomes"]["confirmed_resolved_count"] == 1
    topics = {t["category"]: t["count"] for t in metrics["popular_topics"]}
    assert topics.get("Leave") == 1
