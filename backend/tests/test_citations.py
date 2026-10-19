"""Tests for CitationValidationService: verifying citations against authorized chunks, detecting hallucinations and preventing storage path leaks."""
from __future__ import annotations
import pytest
from app.citations import SAFE_ABSTENTION_MESSAGE, CitationValidationService
from app.llm import Citation, RAGAnswer


@pytest.fixture
def validator():
    return CitationValidationService()


@pytest.fixture
def authorized_chunks():
    return [
        {
            "policy_id": "pol-123",
            "policy_title": "Remote Work Policy",
            "version_label": "2.0",
            "page_number": 3,
            "text": "Employees may work remotely up to 2 days per week with manager approval.",
            "storage_path": "/internal/bucket/confidential/remote.pdf",
        },
        {
            "policy_id": "pol-456",
            "policy_title": "Health Benefits",
            "version_label": "1.0",
            "page_number": 1,
            "text": "Comprehensive health coverage begins on the first day of the calendar month.",
            "storage_path": "/internal/bucket/confidential/health.pdf",
        },
    ]


def test_verified_citation_passes_cleanly(validator, authorized_chunks):
    cit = Citation(policy_title="Remote Work Policy", version="2.0", page_number=3, quote="work remotely up to 2 days per week")
    ans = RAGAnswer(answer="You can work remotely 2 days per week.", citations=[cit], is_grounded=True)
    res = validator.verify_answer(ans, authorized_chunks)

    assert res.is_grounded is True
    assert len(res.citations) == 1
    assert res.citations[0].policy_title == "Remote Work Policy"
    assert res.citations[0].version == "2.0"
    assert res.citations[0].page_number == 3


def test_reject_fabricated_citation(validator, authorized_chunks):
    cit = Citation(policy_title="Unlimited Travel Stipend", version="1.0", page_number=1)
    ans = RAGAnswer(answer="You receive unlimited travel funds.", citations=[cit], is_grounded=True)
    res = validator.verify_answer(ans, authorized_chunks)

    assert res.is_grounded is False
    assert len(res.citations) == 0
    assert res.answer == SAFE_ABSTENTION_MESSAGE


def test_reject_incorrect_page_number(validator, authorized_chunks):
    # Remote Work Policy is on page 3 in retrieved chunks, not page 12
    cit = Citation(policy_title="Remote Work Policy", version="2.0", page_number=12)
    ans = RAGAnswer(answer="Remote guidelines.", citations=[cit], is_grounded=True)
    res = validator.verify_answer(ans, authorized_chunks)

    assert res.is_grounded is False
    assert len(res.citations) == 0
    assert res.answer == SAFE_ABSTENTION_MESSAGE


def test_reject_stale_or_wrong_version(validator, authorized_chunks):
    # Remote Work Policy is version 2.0, not stale version 1.0
    cit = Citation(policy_title="Remote Work Policy", version="1.0", page_number=3)
    ans = RAGAnswer(answer="Old rules.", citations=[cit], is_grounded=True)
    res = validator.verify_answer(ans, authorized_chunks)

    assert res.is_grounded is False
    assert len(res.citations) == 0
    assert res.answer == SAFE_ABSTENTION_MESSAGE


def test_reject_unsupported_claim_quote(validator, authorized_chunks):
    cit = Citation(policy_title="Remote Work Policy", version="2.0", page_number=3, quote="employees can work 100% abroad indefinitely")
    ans = RAGAnswer(answer="You can work abroad indefinitely.", citations=[cit], is_grounded=True)
    res = validator.verify_answer(ans, authorized_chunks)

    assert res.is_grounded is False
    assert len(res.citations) == 0
    assert res.answer == SAFE_ABSTENTION_MESSAGE


def test_no_private_storage_paths_exposed(validator, authorized_chunks):
    cit = Citation(policy_title="Health Benefits", version="1.0", page_number=1)
    ans = RAGAnswer(answer="Health coverage starts on the 1st of the month.", citations=[cit], is_grounded=True)
    res = validator.verify_answer(ans, authorized_chunks)

    res_json = res.model_dump_json()
    assert "/internal/bucket" not in res_json
    assert "confidential" not in res_json
    assert "storage_path" not in res_json


def test_partial_valid_citations_filters_out_invalid(validator, authorized_chunks):
    valid_cit = Citation(policy_title="Health Benefits", version="1.0", page_number=1)
    fake_cit = Citation(policy_title="Nonexistent Perk", version="1.0", page_number=99)
    ans = RAGAnswer(answer="Mixed response.", citations=[valid_cit, fake_cit], is_grounded=True)
    res = validator.verify_answer(ans, authorized_chunks)

    assert res.is_grounded is True
    assert len(res.citations) == 1
    assert res.citations[0].policy_title == "Health Benefits"
