"""Authenticated chat and conversation history endpoints."""
from __future__ import annotations
from datetime import datetime, timezone
import inspect
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import AuthenticatedUser, require_authenticated_user
from app.citations import citation_validation_service
from app.db.models import Conversation, Message
from app.db.repository import policy_chunk_repo
from app.embeddings import embedding_service
from app.errors import AppError
from app.evidence import evidence_validation_service
from app.llm import Citation, llm_service
from app.policies import get_db_session


async def _maybe_await(val: Any) -> Any:
    return await val if inspect.isawaitable(val) else val


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


class MessageItem(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    status: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)
    is_grounded: bool = True
    created_at: datetime


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageItem] = Field(default_factory=list)


chat_router = APIRouter(prefix="/chat", tags=["Chat"])
conversations_router = APIRouter(prefix="/conversations", tags=["Conversations"])


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
    user_id = current_user.user.id
    user_region = current_user.profile.region
    is_hr = current_user.profile.is_hr_administrator

    conv_res = await _maybe_await(session.execute(select(Conversation).where(Conversation.id == conv_id)))
    conv = conv_res.scalar_one_or_none()
    if conv:
        if conv.user_id != user_id:
            raise AppError("Conversation not found or unauthorized", 403, "FORBIDDEN")
    else:
        conv = Conversation(id=conv_id, user_id=user_id, title=clean_msg[:60])
        session.add(conv)

    session.add(Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content=clean_msg))

    embeddings = await embedding_service.embed_texts([clean_msg])
    if not embeddings:
        raise AppError("Failed to vectorize input message", 500, "EMBEDDING_FAILED")

    chunks = await policy_chunk_repo.search_chunks(
        session, embeddings[0], user_region=user_region, is_hr_admin=is_hr, policy_id=request.policy_id, top_k=request.limit,
    )

    val = evidence_validation_service.validate(chunks, target_region=user_region)
    if not val.is_sufficient:
        status, ans, cits, grounded, conf = "abstention", f"Unable to answer from company policy: {val.reason}", [], False, "abstain"
    else:
        raw = await llm_service.generate_answer(clean_msg, val.qualified_chunks)
        ver = citation_validation_service.verify_answer(raw, val.qualified_chunks)
        status, ans, cits, grounded, conf = ("answered" if ver.is_grounded else "abstention"), ver.answer, ver.citations, ver.is_grounded, ver.confidence

    session.add(Message(
        id=uuid.uuid4(), conversation_id=conv_id, role="assistant", content=ans,
        status=status, citations=[c.model_dump() for c in cits], is_grounded=grounded,
    ))
    conv.updated_at = datetime.now(timezone.utc)
    await _maybe_await(session.commit())

    return ChatResponse(conversation_id=conv_id, status=status, answer=ans, citations=cits, is_grounded=grounded, confidence=conf)


@conversations_router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ConversationSummary]:
    stmt = select(Conversation).where(Conversation.user_id == current_user.user.id).order_by(Conversation.updated_at.desc())
    res = await _maybe_await(session.execute(stmt))
    return [ConversationSummary(id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at) for c in res.scalars().all()]


@conversations_router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationDetail:
    conv = (await _maybe_await(session.execute(select(Conversation).where(Conversation.id == conversation_id)))).scalar_one_or_none()
    if not conv or conv.user_id != current_user.user.id:
        raise AppError("Conversation not found" if not conv else "Unauthorized", 404 if not conv else 403, "NOT_FOUND" if not conv else "FORBIDDEN")
    msg_res = await _maybe_await(session.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())))
    msgs = [MessageItem(id=m.id, role=m.role, content=m.content, status=m.status, citations=[Citation(**c) for c in (m.citations or [])], is_grounded=m.is_grounded, created_at=m.created_at) for m in msg_res.scalars().all()]
    return ConversationDetail(id=conv.id, title=conv.title, created_at=conv.created_at, updated_at=conv.updated_at, messages=msgs)
