"""Unit and failure-path tests for chunking and embedding service."""
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import uuid
import httpx
import pytest
from app.config import Settings
from app.errors import AppError
from app.extractor import PageContent
from app.embeddings import EmbeddingService, chunk_pages, chunk_text


def test_chunk_boundaries():
    # 1. Short text
    short = "Short policy snippet."
    res = chunk_text(short, chunk_size=50, chunk_overlap=10)
    assert len(res) == 1 and res[0] == (0, short)

    # 2. Long text with overlap
    text = "A" * 150 + "B" * 150
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
    assert len(chunks) == 4
    assert chunks[0][1] == text[0:100]
    # Step is 100 - 20 = 80
    assert chunks[1][1] == text[80:180]
    assert chunks[1][1][:20] == chunks[0][1][80:100]  # Overlap confirmed

    # 3. Invalid parameters
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        chunk_text("test", chunk_size=0, chunk_overlap=0)
    with pytest.raises(ValueError, match="chunk_overlap must be non-negative and less than chunk_size"):
        chunk_text("test", chunk_size=100, chunk_overlap=100)
    with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
        chunk_text("test", chunk_size=100, chunk_overlap=-5)


def test_metadata_preservation():
    pid, vid = uuid.uuid4(), uuid.uuid4()
    pages = [
        PageContent(page_number=1, text="Page 1 Content " * 20, char_count=300, is_empty=False),
        PageContent(page_number=2, text="Page 2 Content " * 20, char_count=300, is_empty=False),
    ]
    chunks = chunk_pages(pages, policy_id=pid, version_id=vid, chunk_size=120, chunk_overlap=20)

    assert len(chunks) > 2
    for c in chunks:
        assert c.policy_id == str(pid)
        assert c.version_id == str(vid)
        assert c.page_number in (1, 2)
        assert c.chunk_id == f"{pid}_{vid}_p{c.page_number}_c{c.chunk_index}"
        assert c.metadata["page_number"] == c.page_number
        assert c.metadata["chunk_index"] == c.chunk_index
        assert c.metadata["char_count"] == len(c.text)


def test_empty_text():
    # Chunking empty text or whitespace produces 0 chunks
    assert chunk_text("") == []
    assert chunk_text("   \n\t  ") == []
    empty_pages = [PageContent(page_number=1, text="", char_count=0, is_empty=True)]
    assert chunk_pages(empty_pages, policy_id=uuid.uuid4(), version_id=uuid.uuid4()) == []


@pytest.mark.asyncio
async def test_embedding_unconfigured_and_empty():
    svc = EmbeddingService(Settings(openai_api_key=None))
    assert await svc.embed_texts([]) == []

    with pytest.raises(AppError, match="Embedding service unconfigured") as exc:
        await svc.embed_texts(["sample text"])
    assert exc.value.status_code == 503 and exc.value.code == "EMBEDDINGS_UNCONFIGURED"


@pytest.mark.asyncio
async def test_provider_errors():
    svc = EmbeddingService(Settings(openai_api_key="sk-test", embedding_timeout_seconds=5.0))

    # Rate limit 429
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(429, text="Rate limit"))):
        with pytest.raises(AppError, match="rate limit exceeded") as exc:
            await svc.embed_texts(["hello"])
        assert exc.value.status_code == 429

    # Provider 500 error
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(500, text="Internal Server Error"))):
        with pytest.raises(AppError, match="Embedding provider error") as exc:
            await svc.embed_texts(["hello"])
        assert exc.value.status_code == 502

    # Timeout
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(AppError, match="timed out") as exc:
            await svc.embed_texts(["hello"])
        assert exc.value.status_code == 504 and exc.value.code == "EMBEDDING_PROVIDER_TIMEOUT"

    # Connection error
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(AppError, match="Embedding provider unavailable") as exc:
            await svc.embed_texts(["hello"])
        assert exc.value.status_code == 503 and exc.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_embedding_dimensions_and_success():
    svc = EmbeddingService(Settings(openai_api_key="sk-test", embedding_dimensions=1536))
    fake_vec = [0.01 * (i % 10) for i in range(1536)]
    mock_resp = httpx.Response(200, json={"data": [{"index": 0, "embedding": fake_vec}]})

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        res = await svc.embed_texts(["policy text"])
        assert len(res) == 1
        assert len(res[0]) == 1536
        assert res[0] == fake_vec

    # Dimension mismatch error
    short_vec = [0.1] * 512
    mismatch_resp = httpx.Response(200, json={"data": [{"index": 0, "embedding": short_vec}]})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mismatch_resp)):
        with pytest.raises(AppError, match="Embedding dimension mismatch") as exc:
            await svc.embed_texts(["policy text"])
        assert exc.value.status_code == 502 and exc.value.code == "EMBEDDING_DIMENSION_MISMATCH"
