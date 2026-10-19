"""Unit and failure-path tests for PyMuPDF-based text extraction service."""
from __future__ import annotations
import logging
import pymupdf
import pytest
from app.extractor import ExtractionStatus, PDFExtractorService, pdf_extractor


def build_pdf(pages_text: list[str], encrypt_pw: str | None = None) -> bytes:
    doc = pymupdf.open()
    for txt in pages_text:
        p = doc.new_page()
        if txt:
            p.insert_text((50, 50), txt)
    kwargs = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "user_pw": encrypt_pw, "owner_pw": "owner"} if encrypt_pw else {}
    return doc.tobytes(**kwargs)


def test_extract_normal_pdf():
    pdf = build_pdf(["Page 1 Content", "Page 2 Content Here"])
    res = pdf_extractor.extract_text(pdf)

    assert res.status == ExtractionStatus.SUCCESS
    assert res.total_pages == 2 and res.extracted_pages == 2
    assert res.empty_pages == []
    assert len(res.pages) == 2
    assert res.pages[0].page_number == 1 and res.pages[0].text == "Page 1 Content" and not res.pages[0].is_empty
    assert res.pages[1].page_number == 2 and res.pages[1].text == "Page 2 Content Here" and not res.pages[1].is_empty
    assert res.total_char_count == len("Page 1 Content") + len("Page 2 Content Here")
    assert res.error_message is None


def test_extract_pdf_with_empty_and_whitespace_pages():
    pdf = build_pdf(["Valid text", "   \n\t  ", "More valid text"])
    res = pdf_extractor.extract_text(pdf)

    assert res.status == ExtractionStatus.SUCCESS
    assert res.total_pages == 3 and res.extracted_pages == 2
    assert res.empty_pages == [2]
    assert res.pages[1].is_empty and res.pages[1].text == ""
    assert res.pages[0].page_number == 1 and res.pages[2].page_number == 3


def test_extract_completely_blank_pdf():
    pdf = build_pdf(["", "  "])
    res = pdf_extractor.extract_text(pdf)

    assert res.status == ExtractionStatus.EMPTY_TEXT
    assert res.total_pages == 2 and res.extracted_pages == 0
    assert res.empty_pages == [1, 2]
    assert "No extractable text found" in (res.error_message or "")


def test_extract_zero_byte_and_malformed_input():
    # Zero bytes
    res_empty = pdf_extractor.extract_text(b"")
    assert res_empty.status == ExtractionStatus.FAILED
    assert res_empty.total_pages == 0 and "empty document" in (res_empty.error_message or "").lower()

    # Corrupted / malformed
    res_bad = pdf_extractor.extract_text(b"%PDF-1.4 but corrupted trailing garbage not a real pdf")
    assert res_bad.status == ExtractionStatus.FAILED
    assert res_bad.total_pages == 0 and "malformed" in (res_bad.error_message or "").lower()


def test_extract_encrypted_pdf_failure():
    pdf = build_pdf(["Confidential policy"], encrypt_pw="secret123")
    res = pdf_extractor.extract_text(pdf)

    assert res.status == ExtractionStatus.FAILED
    assert "encrypted" in (res.error_message or "").lower() or "password" in (res.error_message or "").lower()
    assert res.extracted_pages == 0


def test_logging_avoids_sensitive_document_contents(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="app.extractor")
    sensitive_token = "CONFIDENTIAL_SALARY_SSN_987654"
    pdf = build_pdf([f"Employee salary data: {sensitive_token}"])

    res = pdf_extractor.extract_text(pdf)
    assert res.status == ExtractionStatus.SUCCESS

    # Operational stats are logged
    assert "PDF extraction finished" in caplog.text
    # Sensitive text itself is NEVER leaked into application logs
    assert sensitive_token not in caplog.text
