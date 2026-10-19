"""Citation validation service verifying citations against authorized retrieved policy chunks."""
from __future__ import annotations
import logging
import re
from typing import Any, Optional
from pydantic import BaseModel, Field
from app.llm import Citation, RAGAnswer

logger = logging.getLogger(__name__)

SAFE_ABSTENTION_MESSAGE = (
    "I do not have sufficient verifiable company policy evidence to answer this question. "
    "Please consult your HR department directly."
)


class CitationValidationResult(BaseModel):
    is_valid: bool
    verified_citations: list[Citation] = Field(default_factory=list)
    rejected_citations: list[dict[str, Any]] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


class CitationValidationService:
    def validate_citation(self, citation: Citation, authorized_chunks: list[dict[str, Any]]) -> tuple[bool, Optional[str], Optional[dict[str, Any]]]:
        c_title = (citation.policy_title or "").strip().lower()
        c_ver = (citation.version or "").strip()
        c_page = citation.page_number

        matching_title = [c for c in authorized_chunks if str(c.get("policy_title", "")).strip().lower() == c_title]
        if not matching_title:
            return False, f"Fabricated citation: policy '{citation.policy_title}' not in retrieved evidence", None

        matching_ver = [c for c in matching_title if str(c.get("version_label", c.get("version", ""))).strip() == c_ver]
        if not matching_ver:
            vers = sorted(list({str(c.get("version_label", c.get("version", ""))) for c in matching_title}))
            return False, f"Stale/incorrect version '{c_ver}' for '{citation.policy_title}'; authorized versions: {vers}", None

        matching_page = [c for c in matching_ver if int(c.get("page_number", 1)) == int(c_page)]
        if not matching_page:
            pages = sorted(list({int(c.get("page_number", 1)) for c in matching_ver}))
            return False, f"Incorrect page {c_page} for '{citation.policy_title}' v{c_ver}; authorized pages: {pages}", None

        matched_chunk = matching_page[0]

        if citation.quote:
            quote_clean = re.sub(r"\s+", " ", citation.quote.strip().lower())
            chunk_clean = re.sub(r"\s+", " ", str(matched_chunk.get("text", "")).lower())
            if quote_clean not in chunk_clean:
                return False, f"Unsupported claim quote '{citation.quote}' not found in passage", None

        sanitized_ref = {
            "policy_id": str(matched_chunk.get("policy_id", "")),
            "policy_title": matched_chunk.get("policy_title", citation.policy_title),
            "version": matched_chunk.get("version_label", matched_chunk.get("version", citation.version)),
            "page_number": matched_chunk.get("page_number", citation.page_number),
        }
        return True, None, sanitized_ref

    def verify_answer(self, answer: RAGAnswer, authorized_chunks: list[dict[str, Any]]) -> RAGAnswer:
        if not answer.is_grounded or not authorized_chunks or not answer.citations:
            return RAGAnswer(answer=SAFE_ABSTENTION_MESSAGE if not answer.citations else answer.answer, citations=[], is_grounded=False, confidence="abstain")

        verified: list[Citation] = []
        rejected: list[dict[str, Any]] = []
        reasons: list[str] = []

        for cit in answer.citations:
            valid, reason, ref = self.validate_citation(cit, authorized_chunks)
            if valid and ref:
                verified.append(Citation(policy_title=ref["policy_title"], version=ref["version"], page_number=ref["page_number"], quote=cit.quote))
            else:
                rejected.append({"citation": cit.model_dump(), "reason": reason})
                if reason: reasons.append(reason)

        if not verified:
            logger.warning("All citations failed verification: %s", reasons)
            return RAGAnswer(answer=SAFE_ABSTENTION_MESSAGE, citations=[], is_grounded=False, confidence="abstain")

        return RAGAnswer(answer=answer.answer, citations=verified, is_grounded=True, confidence="high" if len(rejected) == 0 else "medium")


citation_validation_service = CitationValidationService()
