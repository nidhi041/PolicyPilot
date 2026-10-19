"""Semantic search API router and retrieval service."""
from __future__ import annotations
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import AuthenticatedUser, require_authenticated_user
from app.citations import citation_validation_service
from app.db.repository import policy_chunk_repo
from app.embeddings import embedding_service
from app.evidence import evidence_validation_service
from app.errors import AppError
from app.llm import RAGAnswer, llm_service
from app.policies import get_db_session


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language search query")
    policy_id: Optional[uuid.UUID] = Field(None, description="Optional applicable policy ID filter")
    limit: int = Field(5, ge=1, le=50, description="Maximum number of chunks to return")


class SearchResultChunk(BaseModel):
    chunk_id: str
    policy_id: str
    policy_version_id: str
    policy_title: str
    policy_region: str
    version_label: str
    text: str
    page_number: int
    chunk_index: int
    char_count: int
    page_metadata: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultChunk]
    total_results: int


search_router = APIRouter(prefix="/search", tags=["Search"])


@search_router.post("", status_code=200, response_model=SearchResponse)
async def search_policies(
    request: SearchRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> SearchResponse:
    q = (request.query or "").strip()
    if not q:
        raise AppError("Search query cannot be empty", 400, "INVALID_QUERY")
    embeddings = await embedding_service.embed_texts([q])
    if not embeddings:
        raise AppError("Failed to generate query embedding", 500, "EMBEDDING_FAILED")

    chunks = await policy_chunk_repo.search_chunks(
        session,
        embeddings[0],
        user_region=current_user.profile.region,
        is_hr_admin=current_user.profile.is_hr_administrator,
        policy_id=request.policy_id,
        top_k=max(1, min(request.limit, 50)),
    )
    return SearchResponse(query=q, results=chunks, total_results=len(chunks))


@search_router.get("", status_code=200, response_model=SearchResponse)
async def search_policies_get(
    query: str = Query(..., min_length=1),
    policy_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(5, ge=1, le=50),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> SearchResponse:
    return await search_policies(SearchRequest(query=query, policy_id=policy_id, limit=limit), current_user=current_user, session=session)


@search_router.post("/answer", status_code=200, response_model=RAGAnswer)
async def answer_policy_question(
    request: SearchRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> RAGAnswer:
    q = (request.query or "").strip()
    if not q: raise AppError("Question cannot be empty", 400, "INVALID_QUERY")
    embeddings = await embedding_service.embed_texts([q])
    if not embeddings: raise AppError("Failed to generate query embedding", 500, "EMBEDDING_FAILED")
    chunks = await policy_chunk_repo.search_chunks(
        session, embeddings[0], user_region=current_user.profile.region,
        is_hr_admin=current_user.profile.is_hr_administrator, policy_id=request.policy_id,
        top_k=max(1, min(request.limit, 10)),
    )
    val = evidence_validation_service.validate(chunks, target_region=current_user.profile.region)
    if not val.is_sufficient:
        return RAGAnswer(answer=f"Unable to provide policy answer: {val.reason}", citations=[], is_grounded=False, confidence="abstain")
    raw = await llm_service.generate_answer(q, val.qualified_chunks)
    return citation_validation_service.verify_answer(raw, val.qualified_chunks)
