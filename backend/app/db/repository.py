"""Repository for persisting and querying policy chunks with pgvector embeddings."""
from __future__ import annotations
import inspect
from typing import Any
import uuid
from sqlalchemy import select
from app.config import get_settings
from app.db.models import PolicyChunk
from app.embeddings import TextChunk


async def _maybe_await(val: Any) -> Any:
    if inspect.isawaitable(val):
        return await val
    return val


class PolicyChunkRepository:
    def __init__(self, expected_dim: int | None = None) -> None:
        self.expected_dim = expected_dim or get_settings().embedding_dimensions

    def validate_dimensions_match_column(self) -> bool:
        column_dim = getattr(PolicyChunk.embedding.type, "dim", 1536)
        return self.expected_dim == column_dim

    def validate_embedding(self, embedding: list[float]) -> None:
        if not embedding or len(embedding) != self.expected_dim:
            raise ValueError(f"Embedding dimension mismatch: expected {self.expected_dim}, got {len(embedding) if embedding else 0}")

    async def save_chunks(
        self,
        session: Any,
        policy_id: uuid.UUID,
        policy_version_id: uuid.UUID,
        chunks: list[TextChunk | dict[str, Any]],
        embeddings: list[list[float]],
    ) -> list[PolicyChunk]:
        if len(chunks) != len(embeddings):
            raise ValueError(f"Chunks count ({len(chunks)}) does not match embeddings count ({len(embeddings)})")

        instances: list[PolicyChunk] = []
        for chunk, emb in zip(chunks, embeddings):
            self.validate_embedding(emb)
            c_idx = chunk.chunk_index if isinstance(chunk, TextChunk) else int(chunk.get("chunk_index", 0))
            p_num = getattr(chunk, "page_number", None) or int(chunk.get("page_number", 1) if isinstance(chunk, dict) else 1)
            c_text = chunk.text if hasattr(chunk, "text") else str(chunk.get("text", ""))

            record = PolicyChunk(
                id=uuid.uuid4(),
                policy_id=policy_id,
                policy_version_id=policy_version_id,
                page_number=p_num,
                chunk_index=c_idx,
                text=c_text,
                char_count=len(c_text),
                embedding=emb,
            )
            session.add(record)
            instances.append(record)

        await _maybe_await(session.commit())
        for inst in instances:
            await _maybe_await(session.refresh(inst))
        return instances

    async def get_chunks_by_version(self, session: Any, policy_version_id: uuid.UUID) -> list[PolicyChunk]:
        stmt = select(PolicyChunk).where(PolicyChunk.policy_version_id == policy_version_id).order_by(PolicyChunk.chunk_index.asc())
        result = await _maybe_await(session.execute(stmt))
        return list(result.scalars().all())


policy_chunk_repo = PolicyChunkRepository()
