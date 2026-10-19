"""Authenticated chat endpoint orchestrating identity, region resolution, retrieval, validation, and citations."""
from __future__ import annotations
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import AuthenticatedUser, require_authenticated_user
from app.citations import citation_validation_service
from app.db.repository import policy_chunk_repo
from app.embeddings import embedding_service
from app.errors import AppError
from app.evidence import evidence_validation_service
from app.llm import Citation, llm_service
from app.policies import get_db_session


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Employee question or message")
    conversation_id: Optional[uuid.UUID] = Field(None, description="Optional existing conversation identifier")
    policy_id: Optional[uuid.UUID] = Field(None, description="Optional applicable policy ID scope")
    limit: int = Field(5, ge=1, le=20, description="Maximum evidence chunks to retrieve")


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    status: str = Field(..., description="Answer status: 'answered' or 'abstention'")
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    is_grounded: bool
    confidence: str


chat_router = APIRouter(prefix="/chat", tags=["Chat"])


@chat_router.post("", status_code=200, response_model=ChatResponse)
async def chat_message(
    request: ChatRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    clean_msg = (request.message or "").strip()
    if not clean_msg:
        raise AppError("Message cannot be empty", 400, "INVALID_INPUT")

    conv_id = request.conversation_id or uuid.uuid4()
    user_region = current_user.profile.region
    is_hr = current_user.profile.is_hr_administrator

    embeddings = await embedding_service.embed_texts([clean_msg])
    if not embeddings:
        raise AppError("Failed to vectorize input message", 500, "EMBEDDING_FAILED")

    chunks = await policy_chunk_repo.search_chunks(
        session, embeddings[0], user_region=user_region, is_hr_admin=is_hr, policy_id=request.policy_id, top_k=request.limit,
    )

    val = evidence_validation_service.validate(chunks, target_region=user_region)
    if not val.is_sufficient:
        return ChatResponse(
            conversation_id=conv_id, status="abstention",
            answer=f"Unable to answer from company policy: {val.reason}",
            citations=[], is_grounded=False, confidence="abstain",
        )

    raw_answer = await llm_service.generate_answer(clean_msg, val.qualified_chunks)
    verified_answer = citation_validation_service.verify_answer(raw_answer, val.qualified_chunks)

    return ChatResponse(
        conversation_id=conv_id,
        status="answered" if verified_answer.is_grounded else "abstention",
        answer=verified_answer.answer,
        citations=verified_answer.citations,
        is_grounded=verified_answer.is_grounded,
        confidence=verified_answer.confidence,
    )
