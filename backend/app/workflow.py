"""Policy document processing workflow connecting extraction, chunking, embedding, and vector persistence."""
from __future__ import annotations
import logging
from typing import Any, Optional
import uuid
from sqlalchemy import delete, select
from app.db.models import PolicyChunk, PolicyVersion, ProcessingStatus
from app.db.repository import _maybe_await, policy_chunk_repo
from app.embeddings import chunk_pages, embedding_service
from app.errors import AppError
from app.extractor import ExtractionStatus, pdf_extractor
from app.storage import storage_service

logger = logging.getLogger(__name__)


class PolicyProcessingWorkflow:
    def __init__(self, extractor=pdf_extractor, embedder=embedding_service, repo=policy_chunk_repo, storage=storage_service) -> None:
        self.extractor, self.embedder, self.repo, self.storage = extractor, embedder, repo, storage

    async def process_version(self, session: Any, policy_version_id: uuid.UUID, pdf_bytes: Optional[bytes] = None) -> dict[str, Any]:
        res = await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.id == policy_version_id)))
        version = res.scalar_one_or_none()
        if not version:
            raise AppError("Policy version not found", 404, "NOT_FOUND")

        version.processing_status, version.processing_error = ProcessingStatus.PROCESSING.value, None
        await _maybe_await(session.commit())

        try:
            content = pdf_bytes or await self.storage.download_pdf(version.storage_path)
            extraction = self.extractor.extract_text(content)
            if extraction.status != ExtractionStatus.SUCCESS or extraction.extracted_pages == 0:
                raise AppError(f"Extraction failed: {extraction.error_message or 'No extractable text found'}", 422, "EXTRACTION_FAILED")

            chunks = chunk_pages(extraction.pages, policy_id=version.policy_id, version_id=version.id)
            if not chunks:
                raise AppError("Chunking failed: 0 chunks generated", 422, "CHUNKING_FAILED")

            embeddings = await self.embedder.embed_chunks(chunks)
            await _maybe_await(session.execute(delete(PolicyChunk).where(PolicyChunk.policy_version_id == version.id)))
            saved = await self.repo.save_chunks(session, version.policy_id, version.id, chunks, embeddings)

            version.processing_status, version.processing_error = ProcessingStatus.COMPLETED.value, None
            await _maybe_await(session.commit())
            await _maybe_await(session.refresh(version))
            return {"policy_version_id": str(version.id), "policy_id": str(version.policy_id), "processing_status": version.processing_status, "total_pages": extraction.total_pages, "chunks_count": len(saved), "lifecycle_status": version.status}
        except Exception as exc:
            await _maybe_await(session.rollback())
            try:
                fail_res = await _maybe_await(session.execute(select(PolicyVersion).where(PolicyVersion.id == policy_version_id)))
                if v := fail_res.scalar_one_or_none():
                    v.processing_status, v.processing_error = ProcessingStatus.FAILED.value, str(exc)
                    await _maybe_await(session.commit())
            except Exception: pass
            if isinstance(exc, AppError): raise
            raise AppError(f"Processing failed: {exc}", 500, "PROCESSING_FAILED") from exc


policy_processing_workflow = PolicyProcessingWorkflow()
