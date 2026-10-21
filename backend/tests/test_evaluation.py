"""Deterministic evaluation benchmark tests for retrieval, citations, groundedness, and isolation."""
from __future__ import annotations
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch
import uuid
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import AuthenticatedUser, ProfileInfo, UserInfo, get_current_user
from app.citations import citation_validation_service, Citation, RAGAnswer
from app.config import get_settings
from app.db.models import Base, Policy, PolicyChunk, PolicyLifecycleStatus, PolicyVersion
from app.db.repository import policy_chunk_repo
from app.evidence import evidence_validation_service, EvidenceVerdict
from app.main import create_app
from app.policies import get_db_session
from fastapi.testclient import TestClient

DATASET_PATH = Path(__file__).parent / "eval_dataset.json"


def load_dataset() -> list[dict]:
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def create_in_memory_db() -> Session:
    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.connect() as conn: conn.execute(sa.text("PRAGMA foreign_keys=ON;"))
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_policy(db: Session, title: str, region: str, text: str, ver: str = "1.0", page: int = 1):
    p = Policy(title=title, category="General", region=region)
    v = PolicyVersion(policy_id=p.id, version_label=ver, status=PolicyLifecycleStatus.PUBLISHED.value, storage_path="/p.pdf", content_hash="h")
    c = PolicyChunk(policy_id=p.id, policy_version_id=v.id, page_number=page, chunk_index=0, text=text, char_count=len(text), embedding=[0.05] * 768)
    db.add_all([p, v, c]); db.commit()
    return p, v, c


def make_eval_client(db: Session, monkeypatch, region: str = "US") -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co"); monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k"); get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    uid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user=UserInfo(id=uid, email=f"user-{region}@test.com"),
        profile=ProfileInfo(id=uuid.uuid4(), user_id=uid, role="employee", region=region, is_hr_administrator=False),
    )
    return TestClient(app)


def test_eval_dataset_schema():
    dataset = load_dataset()
    assert len(dataset) >= 7, f"Expected at least 7 benchmark questions, found {len(dataset)}"
    for item in dataset:
        assert item["id"] and item["question"] and item["applicable_region"]
        assert item["expected_outcome"] in ("answered", "abstention")
        assert item["expected_verdict"] in ("sufficient", "insufficient_evidence", "ambiguous_regional_applicability", "conflicting_passages")


@pytest.mark.asyncio
async def test_eval_retrieval_relevance_and_regional_isolation():
    db = create_in_memory_db()
    seed_policy(db, "US Parental Leave Policy", "US", "US employees receive 12 weeks of fully paid parental leave.")
    seed_policy(db, "EU Time Off Policy", "EU", "EU employees receive up to 5 vacation carryover days.", ver="2.0", page=2)
    seed_policy(db, "Global Code of Conduct", "GLOBAL", "Outside employment must be approved by HR.")

    # US employee retrieval strictly excludes EU policy chunks
    us_chunks = await policy_chunk_repo.search_chunks(db, [0.05] * 768, user_region="US", is_hr_admin=False)
    us_regions = {c["policy_region"] for c in us_chunks}
    assert "EU" not in us_regions, "Regional isolation breach: US employee retrieved EU policy chunks"
    assert "US" in us_regions and "GLOBAL" in us_regions

    # EU employee retrieval strictly excludes US policy chunks
    eu_chunks = await policy_chunk_repo.search_chunks(db, [0.05] * 768, user_region="EU", is_hr_admin=False)
    eu_regions = {c["policy_region"] for c in eu_chunks}
    assert "US" not in eu_regions, "Regional isolation breach: EU employee retrieved US policy chunks"
    assert "EU" in eu_regions and "GLOBAL" in eu_regions


def test_eval_insufficient_evidence_and_conflicts():
    # 1. Empty retrieval -> insufficient evidence
    res_empty = evidence_validation_service.validate([])
    assert res_empty.verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE and not res_empty.is_sufficient

    # 2. Conflicting directives -> conflicting passages verdict
    conflicting_chunks = [
        {"text": "Weekend remote work is strictly prohibited and ineligible for staff.", "policy_region": "GLOBAL"},
        {"text": "Remote work is permitted and allowed for all employees on weekends.", "policy_region": "GLOBAL"},
    ]
    res_conflict = evidence_validation_service.validate(conflicting_chunks)
    assert res_conflict.verdict == EvidenceVerdict.CONFLICTING_PASSAGES and not res_conflict.is_sufficient


def test_eval_citation_correctness_and_groundedness():
    chunk = {"policy_id": "p-1", "policy_title": "US Leave", "version_label": "1.0", "page_number": 1, "text": "Employees get 12 weeks of paid leave."}

    # 1. Valid citation passes
    valid_cit = Citation(policy_title="US Leave", version="1.0", page_number=1, quote="12 weeks of paid leave")
    ans_valid = citation_validation_service.verify_answer(RAGAnswer(answer="12 weeks.", citations=[valid_cit], is_grounded=True), [chunk])
    assert ans_valid.is_grounded and len(ans_valid.citations) == 1

    # 2. Hallucinated citation (unsupported quote / wrong page) triggers safe abstention
    bad_cit = Citation(policy_title="US Leave", version="1.0", page_number=99, quote="Hallucinated text")
    ans_bad = citation_validation_service.verify_answer(RAGAnswer(answer="12 weeks.", citations=[bad_cit], is_grounded=True), [chunk])
    assert not ans_bad.is_grounded and len(ans_bad.citations) == 0
    assert "sufficient verifiable company policy" in ans_bad.answer.lower()


def test_eval_deterministic_pipeline_benchmark(monkeypatch):
    dataset = load_dataset()
    eval_stats = {"total": len(dataset), "answered": 0, "abstention": 0, "matching_expected": 0}

    with patch("app.chat.embedding_service.embed_texts", new=AsyncMock(return_value=[[0.05] * 768])):
        for item in dataset:
            db = create_in_memory_db()
            if item.get("passage_text") and item.get("policy_title"):
                # For regional isolation violation (eval-04), policy is EU while employee is US
                pol_region = "EU" if item["id"] == "eval-04-regional-isolation-violation" else item["applicable_region"]
                seed_policy(db, item["policy_title"], pol_region, item["passage_text"], ver=item.get("version") or "1.0", page=item.get("page_number") or 1)

            client = make_eval_client(db, monkeypatch, region=item["applicable_region"])
            mock_payload = {
                "choices": [{"message": {"content": json.dumps({
                    "answer": f"Answer for {item['question']}",
                    "citations": [{"policy_title": item["policy_title"], "version": item["version"], "page_number": item["page_number"], "quote": item["quote"]}] if item.get("quote") else [],
                })}}]
            }
            with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(200, json=mock_payload))):
                res = client.post("/api/v1/chat", json={"message": item["question"]})

            assert res.status_code == 200
            actual_outcome = res.json()["status"]
            eval_stats[actual_outcome] += 1
            if actual_outcome == item["expected_outcome"]:
                eval_stats["matching_expected"] += 1

    accuracy = eval_stats["matching_expected"] / eval_stats["total"]
    assert accuracy == 1.0, f"Expected 100% agreement on benchmark dataset, got {accuracy * 100}%: {eval_stats}"


@pytest.mark.skipif(not os.getenv("RUN_MODEL_EVAL"), reason="Model-based LLM evaluations require live Ollama/OpenAI API")
def test_eval_live_model_evaluation():
    """Separated hook for non-mocked live model evaluation runs."""
    pass
