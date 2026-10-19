"""Deterministic unit tests for EvidenceValidationService."""
from __future__ import annotations
import pytest
from app.evidence import EvidenceValidationService, EvidenceVerdict, ValidationConfig


@pytest.fixture
def validator():
    return EvidenceValidationService()


def test_insufficient_evidence_empty_chunks(validator):
    res = validator.validate([])
    assert res.verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE
    assert not res.is_sufficient and res.signals["chunk_count"] == 0


def test_insufficient_evidence_below_similarity_threshold(validator):
    chunks = [{"text": "Sufficiently long policy text about annual vacations and holidays.", "similarity": 0.45}]
    res = validator.validate(chunks, config=ValidationConfig(min_similarity_threshold=0.60))
    assert res.verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE
    assert not res.is_sufficient


def test_insufficient_evidence_short_text(validator):
    chunks = [{"text": "Too short", "similarity": 0.95}]
    res = validator.validate(chunks)
    assert res.verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE
    assert not res.is_sufficient


def test_ambiguous_regional_applicability_multiple_regions(validator):
    chunks = [
        {"text": "Employees in US receive up to 12 weeks of parental leave.", "policy_region": "US"},
        {"text": "Employees in UK receive statutory maternity and paternity allowances.", "policy_region": "UK"},
    ]
    res = validator.validate(chunks)
    assert res.verdict == EvidenceVerdict.AMBIGUOUS_REGIONAL_APPLICABILITY
    assert not res.is_sufficient and "Multiple conflicting regional" in res.reason


def test_ambiguous_regional_applicability_mismatch_target(validator):
    chunks = [{"text": "US workplace safety standards require hard hats on site.", "policy_region": "US"}]
    res = validator.validate(chunks, target_region="EU")
    assert res.verdict == EvidenceVerdict.AMBIGUOUS_REGIONAL_APPLICABILITY
    assert not res.is_sufficient


def test_conflicting_passages_opposing_directives(validator):
    chunks = [
        {"text": "Remote work is permitted for all team members on Fridays with manager approval.", "policy_region": "GLOBAL"},
        {"text": "Working from home is prohibited and all work must be performed on premise.", "policy_region": "GLOBAL"},
    ]
    res = validator.validate(chunks)
    assert res.verdict == EvidenceVerdict.CONFLICTING_PASSAGES
    assert not res.is_sufficient and "Contradictory directives" in res.reason


def test_conflicting_passages_divergent_numeric_limits(validator):
    chunks = [
        {"text": "Standard annual leave entitlement is 20 days per calendar year.", "policy_region": "GLOBAL"},
        {"text": "Full-time staff members are allotted 25 days of annual leave annually.", "policy_region": "GLOBAL"},
    ]
    res = validator.validate(chunks)
    assert res.verdict == EvidenceVerdict.CONFLICTING_PASSAGES
    assert not res.is_sufficient and "Divergent numeric" in res.reason


def test_similarity_score_is_signal_not_proof_of_correctness(validator):
    # Despite near-perfect similarity 0.99, conflicting rules fail validation
    chunks = [
        {"text": "Overtime is mandatory whenever requested by department leadership.", "similarity": 0.99, "policy_region": "GLOBAL"},
        {"text": "Overtime is strictly optional and voluntary for all hourly staff.", "similarity": 0.98, "policy_region": "GLOBAL"},
    ]
    res = validator.validate(chunks)
    assert res.verdict == EvidenceVerdict.CONFLICTING_PASSAGES
    assert not res.is_sufficient


def test_sufficient_evidence_passes(validator):
    chunks = [
        {"text": "Employees receive 20 days of paid vacation leave each year, accruing monthly.", "similarity": 0.91, "policy_region": "GLOBAL"},
        {"text": "Vacation requests should be submitted at least 2 weeks in advance via HR portal.", "similarity": 0.88, "policy_region": "GLOBAL"},
    ]
    res = validator.validate(chunks, target_region="US")
    assert res.verdict == EvidenceVerdict.SUFFICIENT
    assert res.is_sufficient and len(res.qualified_chunks) == 2


def test_configurable_thresholds_override(validator):
    chunks = [{"text": "Moderate similarity policy text with enough characters for test validation.", "similarity": 0.75, "policy_region": "GLOBAL"}]
    # Passes with default threshold 0.60
    assert validator.validate(chunks).verdict == EvidenceVerdict.SUFFICIENT
    # Fails when strict threshold is configured
    strict_cfg = ValidationConfig(min_similarity_threshold=0.85)
    assert validator.validate(chunks, config=strict_cfg).verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE
