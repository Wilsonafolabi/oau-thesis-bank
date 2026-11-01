"""Tests for PDF text extraction with scanned-page detection."""

import os
import tempfile
from pathlib import Path

import pypdf
import pytest

from oau_ai.document_processing.extraction import (
    PDFExtractionError,
    extract_pdf_pages,
)


def _create_pdf(path: str, pages_text: list):
    """Create a simple PDF with given page count."""
    writer = pypdf.PdfWriter()
    for _ in pages_text:
        writer.add_blank_page(width=72, height=72)
    with open(path, "wb") as f:
        writer.write(f)


def test_extract_pdf_pages_empty_pdf():
    """Extracting pages from an empty PDF returns scanned pages."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        _create_pdf(path, [])
        pages = extract_pdf_pages(path)
        # Empty pages have no text -> flagged as scanned
        for page in pages:
            assert page.is_scanned is True
            assert page.text is None
    finally:
        Path(path).unlink(missing_ok=True)


def test_extract_pdf_pages_nonexistent_file():
    """Extracting from a nonexistent file raises PDFExtractionError."""
    with pytest.raises(PDFExtractionError):
        extract_pdf_pages("/nonexistent/path/to/file.pdf")


def test_extract_pdf_pages_returns_list():
    """Extraction returns a list of ExtractedPage objects."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        _create_pdf(path, ["page text"])
        pages = extract_pdf_pages(path)
        assert isinstance(pages, list)
        assert len(pages) >= 1
        for page in pages:
            assert hasattr(page, "page_number")
            assert hasattr(page, "text")
            assert hasattr(page, "is_scanned")
            assert page.page_number >= 1
    finally:
        Path(path).unlink(missing_ok=True)
