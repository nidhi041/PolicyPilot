"""Deterministic text chunking and hosted embedding service."""
from __future__ import annotations
import logging
from typing import Any, Optional
import uuid
import httpx
from pydantic import BaseModel
from app.config import Settings, get_settings
from app.errors import AppError
from app.extractor import PageContent

logger = logging.getLogger(__name__)


class TextChunk(BaseModel):
    chunk_id: str
    policy_id: str
    version_id: str
    page_number: int
    chunk_index: int
    text: str
    char_count: int
    metadata: dict[str, Any]


def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[tuple[int, str]]:
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(f"chunk_overlap must be non-negative and less than chunk_size ({chunk_size}), got {chunk_overlap}")
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [(0, cleaned)]

    chunks: list[tuple[int, str]] = []
    step = chunk_size - chunk_overlap
    idx = 0
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append((idx, piece))
            idx += 1
        if end >= len(cleaned):
            break
        start += step
    return chunks


def chunk_pages(
    pages: list[PageContent | dict[str, Any]],
    policy_id: uuid.UUID | str,
    version_id: uuid.UUID | str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> list[TextChunk]:
    settings = get_settings()
    c_size = chunk_size or settings.chunk_size_chars
    c_overlap = chunk_overlap or settings.chunk_overlap_chars
    pid, vid = str(policy_id), str(version_id)

    result_chunks: list[TextChunk] = []
    for page in pages:
        p_num = page.page_number if isinstance(page, PageContent) else int(page.get("page_number", 1))
        p_text = page.text if isinstance(page, PageContent) else str(page.get("text", ""))
        for chunk_idx, chunk_str in chunk_text(p_text, chunk_size=c_size, chunk_overlap=c_overlap):
            cid = f"{pid}_{vid}_p{p_num}_c{chunk_idx}"
            meta = {"policy_id": pid, "version_id": vid, "page_number": p_num, "chunk_index": chunk_idx, "char_count": len(chunk_str)}
            result_chunks.append(TextChunk(chunk_id=cid, policy_id=pid, version_id=vid, page_number=p_num, chunk_index=chunk_idx, text=chunk_str, char_count=len(chunk_str), metadata=meta))
    return result_chunks


class EmbeddingService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.settings.openai_api_key:
            raise AppError("Embedding service unconfigured: missing API key", 503, "EMBEDDINGS_UNCONFIGURED")

        url = f"{self.settings.openai_base_url.rstrip('/')}/embeddings"
        key = self.settings.openai_api_key.get_secret_value()
        hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {"input": texts, "model": self.settings.embedding_model}

        try:
            async with httpx.AsyncClient(timeout=self.settings.embedding_timeout_seconds) as client:
                resp = await client.post(url, headers=hdrs, json=payload)
        except httpx.TimeoutException:
            logger.warning("Embedding provider request timed out")
            raise AppError("Embedding provider request timed out", 504, "EMBEDDING_PROVIDER_TIMEOUT")
        except httpx.RequestError as exc:
            logger.warning("Embedding provider request error: %s", type(exc).__name__)
            raise AppError("Embedding provider unavailable", 503, "EMBEDDING_PROVIDER_UNAVAILABLE")

        if resp.status_code == 429:
            raise AppError(f"Embedding provider rate limit exceeded: {resp.text}", 429, "EMBEDDING_PROVIDER_ERROR")
        if resp.status_code != 200:
            raise AppError(f"Embedding provider error ({resp.status_code}): {resp.text}", 502, "EMBEDDING_PROVIDER_ERROR")

        data = resp.json().get("data", [])
        # Sort by index to guarantee deterministic ordering
        sorted_data = sorted(data, key=lambda d: d.get("index", 0))
        embeddings: list[list[float]] = [d["embedding"] for d in sorted_data]

        for vec in embeddings:
            if len(vec) != self.settings.embedding_dimensions:
                raise AppError(f"Embedding dimension mismatch: expected {self.settings.embedding_dimensions}, got {len(vec)}", 502, "EMBEDDING_DIMENSION_MISMATCH")
        return embeddings

    async def embed_chunks(self, chunks: list[TextChunk]) -> list[list[float]]:
        return await self.embed_texts([c.text for c in chunks])


embedding_service = EmbeddingService()
