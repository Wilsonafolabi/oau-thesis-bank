"""Configurable chunking with overlap.

Splits page text into overlapping chunks. Each chunk carries page-level
provenance (page_number, char_offset_start/end) linking it back to the
original thesis and page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ChunkData:
    """A single chunk with page-level provenance."""

    chunk_index: int
    text: str
    page_number: int
    char_offset_start: int
    char_offset_end: int
    token_count: Optional[int] = None


def chunk_page_text(
    page_number: int,
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
    start_index: int = 0,
) -> List[ChunkData]:
    """Split a single page's text into overlapping chunks.

    Args:
        page_number: The 1-based page number this text came from.
        text: The page text to chunk.
        chunk_size: Target chunk size in characters (default 512).
        overlap: Overlap between consecutive chunks in characters (default 50).
        start_index: Starting chunk index (for multi-page documents).

    Returns:
        List of ChunkData objects. Returns empty list for empty text.
    """
    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    chunks: List[ChunkData] = []
    step = chunk_size - overlap
    text_len = len(text)
    index = start_index

    start = 0
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk_text = text[start:end]

        # Try to break at a sentence or word boundary for cleaner chunks.
        if end < text_len:
            last_period = chunk_text.rfind(". ")
            last_newline = chunk_text.rfind("\n")
            break_point = max(last_period, last_newline)
            if break_point > start + chunk_size // 2:
                end = start + break_point + 1
                chunk_text = text[start:end]

        chunks.append(
            ChunkData(
                chunk_index=index,
                text=chunk_text.strip(),
                page_number=page_number,
                char_offset_start=start,
                char_offset_end=end,
            )
        )
        index += 1

        if end >= text_len:
            break

        start = end - overlap
        if start < 0:
            start = 0

    return chunks


def chunk_document_pages(
    pages_text: dict,
    chunk_size: int = 512,
    overlap: int = 50,
) -> List[ChunkData]:
    """Chunk all pages of a document.

    Args:
        pages_text: Dict mapping page_number (int) -> text (str or None).
                    Scanned pages (None text) are skipped.
        chunk_size: Target chunk size in characters.
        overlap: Overlap between consecutive chunks in characters.

    Returns:
        List of ChunkData across all pages, with globally unique chunk_index.
    """
    all_chunks: List[ChunkData] = []
    global_index = 0

    for page_number in sorted(pages_text.keys()):
        text = pages_text.get(page_number)
        if not text:
            continue

        page_chunks = chunk_page_text(
            page_number=page_number,
            text=text,
            chunk_size=chunk_size,
            overlap=overlap,
            start_index=global_index,
        )
        all_chunks.extend(page_chunks)
        global_index += len(page_chunks)

    return all_chunks
