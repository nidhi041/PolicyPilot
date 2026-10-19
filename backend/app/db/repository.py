"""Repository for persisting and querying policy chunks with pgvector embeddings."""
from __future__ import annotations
from datetime import datetime, timezone
import inspect
from typing import Any, Optional
import uuid
import sqlalchemy as sa
from sqlalchemy import select
from app.config import get_settings
from app.db.models import Policy, PolicyChunk, PolicyLifecycleStatus, PolicyVersion, Region
from app.embeddings import TextChunk


async def _maybe_await(val: Any) -> Any:
    if inspect.isawaitable(val):
        return await val
    return val


class PolicyChunkRepository:
    def __init__(self, expected_dim: int | None = None) -> None:
        self.expected_dim = expected_dim or get_settings().embedding_dimensions

    def validate_dimensions_match_column(self) -> bool:
        column_dim = getattr(PolicyChunk.embedding.type, "dim", 768)
        return self.expected_dim == column_dim

    def validate_embedding(self, embedding: list[float]) -> None:
        if not embedding or len(embedding) != self.expected_dim:
            raise ValueError(f"Embedding dimension mismatch: expected {self.expected_dim}, got {len(embedding) if embedding else 0}")

    async def save_chunks(self, session: Any, policy_id: uuid.UUID, policy_version_id: uuid.UUID, chunks: list[TextChunk | dict[str, Any]], embeddings: list[list[float]]) -> list[PolicyChunk]:
        if len(chunks) != len(embeddings):
            raise ValueError(f"Chunks count ({len(chunks)}) does not match embeddings count ({len(embeddings)})")
        instances: list[PolicyChunk] = []
        for seq_idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            self.validate_embedding(emb)
            c_idx = int(chunk["chunk_index"]) if isinstance(chunk, dict) and "chunk_index" in chunk else seq_idx
            p_num = getattr(chunk, "page_number", None) or int(chunk.get("page_number", 1) if isinstance(chunk, dict) else 1)
            c_text = chunk.text if hasattr(chunk, "text") else str(chunk.get("text", ""))
            record = PolicyChunk(id=uuid.uuid4(), policy_id=policy_id, policy_version_id=policy_version_id, page_number=p_num, chunk_index=c_idx, text=c_text, char_count=len(c_text), embedding=emb)
            session.add(record); instances.append(record)
        await _maybe_await(session.commit())
        for inst in instances: await _maybe_await(session.refresh(inst))
        return instances

    async def get_chunks_by_version(self, session: Any, policy_version_id: uuid.UUID) -> list[PolicyChunk]:
        stmt = select(PolicyChunk).where(PolicyChunk.policy_version_id == policy_version_id).order_by(PolicyChunk.chunk_index.asc())
        return list((await _maybe_await(session.execute(stmt))).scalars().all())

    async def search_chunks(self, session: Any, query_embedding: list[float], *, user_region: str, is_hr_admin: bool = False, policy_id: Optional[uuid.UUID] = None, current_time: Optional[datetime] = None, top_k: int = 5) -> list[dict[str, Any]]:
        self.validate_embedding(query_embedding)
        now = current_time or datetime.now(timezone.utc)
        stmt = (
            select(PolicyChunk, Policy.title, Policy.region, PolicyVersion.version_label)
            .join(PolicyVersion, PolicyChunk.policy_version_id == PolicyVersion.id)
            .join(Policy, PolicyChunk.policy_id == Policy.id)
            .where(PolicyVersion.status == PolicyLifecycleStatus.PUBLISHED.value)
            .where(sa.or_(PolicyVersion.effective_from.is_(None), PolicyVersion.effective_from <= now))
            .where(sa.or_(PolicyVersion.effective_to.is_(None), PolicyVersion.effective_to >= now))
        )
        if not is_hr_admin:
            stmt = stmt.where(Policy.region.in_([user_region, Region.GLOBAL.value]))
        if policy_id:
            stmt = stmt.where(Policy.id == policy_id)

        bind = getattr(session, "bind", None) or (session.get_bind() if hasattr(session, "get_bind") else None)
        dialect = getattr(getattr(bind, "dialect", None), "name", "")
        if dialect != "sqlite":
            stmt = stmt.order_by(PolicyChunk.embedding.cosine_distance(query_embedding).asc()).limit(top_k)
            rows = (await _maybe_await(session.execute(stmt))).all()
        else:
            rows = (await _maybe_await(session.execute(stmt))).all()
            def _dist(emb: Any) -> float:
                vec = emb if isinstance(emb, list) else [float(x) for x in str(emb).strip("[]").split(",") if x.strip()]
                dot = sum(a * b for a, b in zip(query_embedding, vec))
                norm_q, norm_v = sum(a * a for a in query_embedding) ** 0.5, sum(b * b for b in vec) ** 0.5
                return 1.0 - (dot / (norm_q * norm_v)) if (norm_q and norm_v) else 1.0
            rows = sorted(rows, key=lambda r: _dist(r[0].embedding))[:top_k]

        return [
            {
                "chunk_id": str(c.id), "policy_id": str(c.policy_id), "policy_version_id": str(c.policy_version_id),
                "policy_title": title, "policy_region": region, "version_label": ver,
                "text": c.text, "page_number": c.page_number, "chunk_index": c.chunk_index, "char_count": c.char_count,
                "page_metadata": {"page_number": c.page_number, "chunk_index": c.chunk_index, "char_count": c.char_count},
            }
            for c, title, region, ver in rows
        ]


policy_chunk_repo = PolicyChunkRepository()
