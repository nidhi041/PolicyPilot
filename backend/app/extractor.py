"""PyMuPDF-based text extraction service for policy PDFs."""
from __future__ import annotations
import enum
import logging
from typing import Optional
from pydantic import BaseModel
import pymupdf

logger = logging.getLogger(__name__)


class ExtractionStatus(str, enum.Enum):
    SUCCESS = "success"
    EMPTY_TEXT = "empty_text"
    FAILED = "failed"


class PageContent(BaseModel):
    page_number: int
    text: str
    char_count: int
    is_empty: bool


class PDFExtractionResult(BaseModel):
    status: ExtractionStatus
    total_pages: int
    extracted_pages: int
    empty_pages: list[int]
    total_char_count: int
    pages: list[PageContent]
    error_message: Optional[str] = None


class PDFExtractorService:
    @staticmethod
    def extract_text(pdf_bytes: bytes) -> PDFExtractionResult:
        if not pdf_bytes:
            logger.warning("PDF extraction failed: zero-byte input")
            return PDFExtractionResult(
                status=ExtractionStatus.FAILED, total_pages=0, extracted_pages=0,
                empty_pages=[], total_char_count=0, pages=[],
                error_message="Cannot extract text from empty document",
            )
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            logger.warning("PDF extraction failed: malformed document (%s)", type(exc).__name__)
            return PDFExtractionResult(
                status=ExtractionStatus.FAILED, total_pages=0, extracted_pages=0,
                empty_pages=[], total_char_count=0, pages=[],
                error_message=f"Malformed or unreadable PDF: {type(exc).__name__}",
            )

        try:
            if doc.is_encrypted and not doc.authenticate(""):
                logger.warning("PDF extraction failed: document is encrypted")
                return PDFExtractionResult(
                    status=ExtractionStatus.FAILED, total_pages=len(doc), extracted_pages=0,
                    empty_pages=[], total_char_count=0, pages=[],
                    error_message="Document is password-protected or encrypted",
                )

            total_pages = len(doc)
            if total_pages == 0:
                logger.warning("PDF extraction: document has 0 pages")
                return PDFExtractionResult(
                    status=ExtractionStatus.EMPTY_TEXT, total_pages=0, extracted_pages=0,
                    empty_pages=[], total_char_count=0, pages=[],
                    error_message="Document contains no pages",
                )

            pages: list[PageContent] = []
            empty_pages: list[int] = []
            total_chars = 0

            for idx, page in enumerate(doc):
                page_num = idx + 1
                try:
                    raw_text = page.get_text() or ""
                except Exception:
                    raw_text = ""
                clean_text = raw_text.strip()
                char_count = len(clean_text)
                is_empty = char_count == 0
                if is_empty:
                    empty_pages.append(page_num)
                else:
                    total_chars += char_count
                pages.append(PageContent(page_number=page_num, text=clean_text, char_count=char_count, is_empty=is_empty))

            extracted = total_pages - len(empty_pages)
            status = ExtractionStatus.EMPTY_TEXT if extracted == 0 else ExtractionStatus.SUCCESS
            logger.info("PDF extraction finished: status=%s, pages=%d, extracted=%d, empty=%d, chars=%d", status.value, total_pages, extracted, len(empty_pages), total_chars)
            return PDFExtractionResult(
                status=status, total_pages=total_pages, extracted_pages=extracted,
                empty_pages=empty_pages, total_char_count=total_chars, pages=pages,
                error_message="No extractable text found in document" if status == ExtractionStatus.EMPTY_TEXT else None,
            )
        finally:
            doc.close()


pdf_extractor = PDFExtractorService()
