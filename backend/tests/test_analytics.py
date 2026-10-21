"""Tests for the HR Analytics API endpoints, calculations, filters, and authorization."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import uuid
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import AuthenticatedUser, ProfileInfo, UserInfo, get_current_user
from app.config import get_settings
from app.db.models import Base, Conversation, Message, MessageFeedback, Policy, Profile, UserRole
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

def make_user(role: str = UserRole.HR_ADMINISTRATOR.value, region: str = "GLOBAL") -> AuthenticatedUser:
    uid = uuid.uuid4()
    return AuthenticatedUser(
        user=UserInfo(id=uid, email=f"{role}_{region}@test.com"),
        profile=ProfileInfo(id=uuid.uuid4(), user_id=uid, role=role, region=region, is_hr_administrator=(role == UserRole.HR_ADMINISTRATOR.value)),
    )

def create_client(test_db, monkeypatch, user: AuthenticatedUser | None = None) -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co"); monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: test_db
    if user: app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)

def test_analytics_permissions_and_region_boundaries(test_db, monkeypatch):
    assert create_client(test_db, monkeypatch).get("/api/v1/analytics/overview").status_code == 401
    assert create_client(test_db, monkeypatch, make_user(role=UserRole.EMPLOYEE.value)).get("/api/v1/analytics/overview").status_code == 403
    us_hr = create_client(test_db, monkeypatch, make_user(role=UserRole.HR_ADMINISTRATOR.value, region="US"))
    assert us_hr.get("/api/v1/analytics/overview?region=EU").status_code == 403
    res_us = us_hr.get("/api/v1/analytics/overview?region=US")
    assert res_us.status_code == 200 and res_us.json()["filters"]["region"] == "US"

def test_analytics_invalid_date_range(test_db, monkeypatch):
    hr = create_client(test_db, monkeypatch, make_user())
    assert hr.get("/api/v1/analytics/overview?start_date=2026-10-20&end_date=2026-10-10").status_code == 400

def test_analytics_safe_empty_state(test_db, monkeypatch):
    res = create_client(test_db, monkeypatch, make_user()).get("/api/v1/analytics/overview")
    assert res.status_code == 200
    d = res.json()
    assert d["question_volume"]["total_questions"] == 0 and d["question_volume"]["daily_trend"] == []
    assert d["answer_outcomes"]["total_answers"] == 0 and d["answer_outcomes"]["grounded_rate"] == 0.0
    assert d["feedback_summary"]["total_feedback_count"] == 0 and d["popular_topics"] == [] and d["unanswered_questions"] == []

def test_analytics_metrics_calculations_and_filters(test_db, monkeypatch):
    user_us, user_eu = make_user(role=UserRole.EMPLOYEE.value, region="US"), make_user(role=UserRole.EMPLOYEE.value, region="EU")
    test_db.add_all([
        Profile(id=user_us.profile.id, user_id=user_us.user.id, role="employee", region="US"),
        Profile(id=user_eu.profile.id, user_id=user_eu.user.id, role="employee", region="EU"),
        Policy(id=uuid.uuid4(), title="Parental Leave Policy", category="Leave", region="GLOBAL"),
        Policy(id=uuid.uuid4(), title="Health Benefits Policy", category="Benefits", region="US"),
    ])
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    conv_us, conv_eu = Conversation(id=uuid.uuid4(), user_id=user_us.user.id, title="Leave", created_at=now), Conversation(id=uuid.uuid4(), user_id=user_eu.user.id, title="EU", created_at=now)
    q1 = Message(id=uuid.uuid4(), conversation_id=conv_us.id, role="user", content="How many weeks leave?", created_at=now - timedelta(hours=2))
    a1 = Message(id=uuid.uuid4(), conversation_id=conv_us.id, role="assistant", content="16 weeks.", status="answered", is_grounded=True, citations=[{"policy_title": "Parental Leave Policy"}], created_at=now - timedelta(hours=2))
    fb1 = MessageFeedback(id=uuid.uuid4(), message_id=a1.id, user_id=user_us.user.id, rating="up", created_at=now - timedelta(hours=2))
    q2 = Message(id=uuid.uuid4(), conversation_id=conv_us.id, role="user", content="Can I bring my pet iguana?", created_at=now - timedelta(hours=1))
    a2 = Message(id=uuid.uuid4(), conversation_id=conv_us.id, role="assistant", content="Unable to answer.", status="abstention", is_grounded=False, citations=[], created_at=now - timedelta(hours=1))
    fb2 = MessageFeedback(id=uuid.uuid4(), message_id=a2.id, user_id=user_us.user.id, rating="down", created_at=now - timedelta(hours=1))
    q3 = Message(id=uuid.uuid4(), conversation_id=conv_eu.id, role="user", content="What are health benefits?", created_at=now)
    a3 = Message(id=uuid.uuid4(), conversation_id=conv_eu.id, role="assistant", content="Benefits cover medical.", status="answered", is_grounded=True, citations=[{"policy_title": "Health Benefits Policy"}], created_at=now)
    test_db.add_all([conv_us, conv_eu, q1, a1, fb1, q2, a2, fb2, q3, a3])
    test_db.commit()

    hr = create_client(test_db, monkeypatch, make_user(role=UserRole.HR_ADMINISTRATOR.value, region="GLOBAL"))
    res = hr.get("/api/v1/analytics/overview")
    assert res.status_code == 200
    d = res.json()
    assert d["question_volume"]["total_questions"] == 3 and d["question_volume"]["total_conversations"] == 2
    assert d["answer_outcomes"]["grounded_answers_count"] == 2 and d["answer_outcomes"]["grounded_rate"] == 66.7
    assert d["answer_outcomes"]["abstention_count"] == 1 and d["answer_outcomes"]["abstention_rate"] == 33.3
    assert d["answer_outcomes"]["confirmed_resolved_count"] == 1 and d["answer_outcomes"]["confirmed_unresolved_count"] == 2
    assert d["feedback_summary"]["total_feedback_count"] == 2 and d["feedback_summary"]["positive_feedback_count"] == 1
    assert d["feedback_summary"]["satisfaction_rate"] == 50.0 and d["feedback_summary"]["response_rate"] == 66.7
    cats = {t["category"]: t["count"] for t in d["popular_topics"]}
    assert cats.get("Leave") == 1 and cats.get("Benefits") == 1
    assert len(d["unanswered_questions"]) == 1 and d["unanswered_questions"][0]["question"] == "Can I bring my pet iguana?"

    res_us = hr.get("/api/v1/analytics/overview?region=US")
    assert res_us.status_code == 200
    d_us = res_us.json()
    assert d_us["question_volume"]["total_questions"] == 2 and d_us["answer_outcomes"]["total_answers"] == 2
    assert d_us["popular_topics"][0]["category"] == "Leave"
