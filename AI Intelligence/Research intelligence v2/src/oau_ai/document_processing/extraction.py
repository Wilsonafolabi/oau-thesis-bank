"""PDF text extraction with scanned-page detection.

Uses pypdf for text extraction. Pages with no extractable text are flagged
as scanned so downstream OCR can be applied later without blocking the
pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pypdf


@dataclass
class ExtractedPage:
    """Result of extracting a single PDF page."""

    page_number: int
    text: Optional[str]
    is_scanned: bool
    char_offset_start: Optional[int] = None
    char_offset_end: Optional[int] = None


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be opened or read."""


def extract_pdf_pages(file_path: str) -> List[ExtractedPage]:
    """Extract text from every page of a PDF file.

    Returns a list of ExtractedPage objects in page order. Pages that contain
    no extractable text are flagged as scanned (text=None) so the pipeline can
    route them to OCR later without failing the entire document.
    """
    try:
        reader = pypdf.PdfReader(file_path)
    except Exception as exc:
        raise PDFExtractionError(f"Cannot open PDF: {exc}") from exc

    pages: List[ExtractedPage] = []
    char_offset = 0

    for idx, page in enumerate(reader.pages, start=1):
        page_number = idx
        try:
            text = page.extract_text()
        except Exception:
            text = None

        if text is None or not text.strip():
            is_scanned = True
            text = None
        else:
            is_scanned = False

        pages.append(
            ExtractedPage(
                page_number=page_number,
                text=text,
                is_scanned=is_scanned,
                char_offset_start=char_offset if text else None,
                char_offset_end=(char_offset + len(text)) if text else None,
            )
        )

        if text:
            char_offset += len(text) + 1  # +1 for page separator

    return pages
