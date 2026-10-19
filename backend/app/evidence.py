"""Evidence validation service evaluating retrieval quality, regional clarity, and conflict signals.

LIMITATIONS:
1. Lexical and heuristic conflict detection relies on pattern matching for explicit opposing directives
   (e.g., permitted vs prohibited, mandatory vs optional) and divergent numerical quantities for shared subject terms.
2. Subtle semantic contradictions, conditional policy exceptions ("unless approved by executive VP"),
   or complex cross-document precedence hierarchies require downstream LLM validation and citation auditing.
3. Similarity scores reflect vector proximity, not factual ground truth or logical consistency.
"""
from __future__ import annotations
import enum
import re
from typing import Any, Optional
from pydantic import BaseModel, Field


class EvidenceVerdict(str, enum.Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    AMBIGUOUS_REGIONAL_APPLICABILITY = "ambiguous_regional_applicability"
    CONFLICTING_PASSAGES = "conflicting_passages"


class ValidationConfig(BaseModel):
    min_similarity_threshold: float = Field(0.60, ge=0.0, le=1.0)
    min_total_chars: int = Field(40, ge=1)
    min_chunks: int = Field(1, ge=1)


class EvidenceValidationResult(BaseModel):
    verdict: EvidenceVerdict
    is_sufficient: bool
    reason: str
    signals: dict[str, Any]
    qualified_chunks: list[dict[str, Any]]


OPPOSING_DIRECTIVES = [
    (re.compile(r"\b(prohibited|not allowed|forbidden|strictly banned|ineligible)\b", re.I),
     re.compile(r"\b(permitted|allowed|eligible|authorized|encouraged)\b", re.I)),
    (re.compile(r"\b(mandatory|required|must|compulsory)\b", re.I),
     re.compile(r"\b(optional|voluntary|discretionary|not required|not mandatory)\b", re.I)),
]

NUMERIC_PATTERNS = [
    re.compile(r"(\d+)\s*(days?|weeks?|months?|hours?)\b", re.I),
    re.compile(r"\$(\d+(?:,\d{3})*(?:\.\d+)?)\b"),
]


class EvidenceValidationService:
    def __init__(self, config: Optional[ValidationConfig] = None) -> None:
        self.config = config or ValidationConfig()

    def detect_conflicts(self, chunks: list[dict[str, Any]]) -> list[str]:
        texts = [c.get("text", "") for c in chunks]
        conflicts: list[str] = []
        for neg_re, pos_re in OPPOSING_DIRECTIVES:
            if any(neg_re.search(t) for t in texts) and any(pos_re.search(t) for t in texts):
                conflicts.append("Contradictory directives detected (e.g. permitted vs prohibited / mandatory vs optional)")
                break

        for kw in ["leave", "notice", "probation", "carryover", "allowance", "stipend", "expense", "rollover"]:
            kw_re = re.compile(rf"\b{kw}\b", re.I)
            kw_texts = [t for t in texts if kw_re.search(t)]
            if len(kw_texts) >= 2:
                nums = set()
                for t in kw_texts:
                    for num_pat in NUMERIC_PATTERNS:
                        for m in num_pat.findall(t):
                            nums.add(m if isinstance(m, str) else " ".join(m).lower())
                if len(nums) > 1:
                    conflicts.append(f"Divergent numeric specifications for '{kw}': {sorted(list(nums))}")
        return conflicts

    def detect_regional_ambiguity(self, chunks: list[dict[str, Any]], target_region: Optional[str] = None) -> Optional[str]:
        regions = {str(c.get("policy_region", "")).upper() for c in chunks if c.get("policy_region")}
        non_global = regions - {"GLOBAL", ""}
        if len(non_global) > 1:
            return f"Multiple conflicting regional jurisdictions found: {sorted(list(non_global))}"
        if target_region and non_global and target_region.upper() not in non_global:
            return f"Retrieved region {sorted(list(non_global))} does not match target region {target_region.upper()}"
        return None

    def validate(self, chunks: list[dict[str, Any]], *, target_region: Optional[str] = None, config: Optional[ValidationConfig] = None) -> EvidenceValidationResult:
        cfg = config or self.config
        if not chunks:
            return EvidenceValidationResult(verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE, is_sufficient=False, reason="No evidence chunks were retrieved.", signals={"chunk_count": 0, "total_chars": 0}, qualified_chunks=[])

        qualified = [c for c in chunks if c.get("similarity") is None or c["similarity"] >= cfg.min_similarity_threshold]
        total_chars = sum(len(c.get("text", "").strip()) for c in qualified)
        if len(qualified) < cfg.min_chunks or total_chars < cfg.min_total_chars:
            return EvidenceValidationResult(verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE, is_sufficient=False, reason=f"Insufficient evidence: qualified chunks ({len(qualified)}) or characters ({total_chars}) below threshold.", signals={"qualified_chunks": len(qualified), "total_chars": total_chars}, qualified_chunks=qualified)

        regional_issue = self.detect_regional_ambiguity(qualified, target_region=target_region)
        if regional_issue:
            return EvidenceValidationResult(verdict=EvidenceVerdict.AMBIGUOUS_REGIONAL_APPLICABILITY, is_sufficient=False, reason=regional_issue, signals={"regions": [c.get("policy_region") for c in qualified]}, qualified_chunks=qualified)

        conflicts = self.detect_conflicts(qualified)
        if conflicts:
            return EvidenceValidationResult(verdict=EvidenceVerdict.CONFLICTING_PASSAGES, is_sufficient=False, reason="; ".join(conflicts), signals={"conflicts": conflicts}, qualified_chunks=qualified)

        return EvidenceValidationResult(verdict=EvidenceVerdict.SUFFICIENT, is_sufficient=True, reason="Retrieved evidence meets relevance thresholds and is clear and non-conflicting.", signals={"qualified_chunks": len(qualified), "total_chars": total_chars}, qualified_chunks=qualified)


evidence_validation_service = EvidenceValidationService()
