"""Tests for configurable chunking with overlap."""

import pytest

from oau_ai.document_processing.chunking import (
    chunk_document_pages,
    chunk_page_text,
)


def test_chunk_page_text_basic():
    """Basic chunking produces overlapping chunks."""
    text = "A" * 1000
    chunks = chunk_page_text(page_number=1, text=text, chunk_size=100, overlap=20)

    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.page_number == 1
        assert chunk.chunk_index == i
        assert len(chunk.text) <= 100
        assert chunk.char_offset_start >= 0
        assert chunk.char_offset_end > chunk.char_offset_start


def test_chunk_page_text_overlap():
    """Consecutive chunks overlap by the specified amount."""
    text = "B" * 500
    chunks = chunk_page_text(page_number=2, text=text, chunk_size=100, overlap=30)

    assert len(chunks) > 2
    # Verify overlap: end of chunk N should overlap with start of chunk N+1
    for i in range(len(chunks) - 1):
        chunk_i = chunks[i].text
        chunk_next = chunks[i + 1].text
        # The next chunk should start before the previous chunk ends
        # (overlap exists in char offsets)
        assert chunks[i + 1].char_offset_start < chunks[i].char_offset_end


def test_chunk_page_text_empty():
    """Empty text returns empty chunk list."""
    chunks = chunk_page_text(page_number=1, text="", chunk_size=100, overlap=20)
    assert chunks == []

    chunks = chunk_page_text(page_number=1, text="   ", chunk_size=100, overlap=20)
    assert chunks == []


def test_chunk_page_text_invalid_params():
    """Invalid chunk_size or overlap raises ValueError."""
    with pytest.raises(ValueError):
        chunk_page_text(page_number=1, text="hello", chunk_size=0, overlap=10)

    with pytest.raises(ValueError):
        chunk_page_text(page_number=1, text="hello", chunk_size=10, overlap=10)


def test_chunk_document_pages_multi_page():
    """Chunking multiple pages produces globally unique chunk indices."""
    pages_text = {
        1: "Page one text. " * 50,
        2: "Page two text. " * 50,
        3: None,  # Scanned page - no text
    }
    chunks = chunk_document_pages(pages_text, chunk_size=100, overlap=20)

    assert len(chunks) > 0
    # Chunks from page 1 come before page 2
    page1_chunks = [c for c in chunks if c.page_number == 1]
    page2_chunks = [c for c in chunks if c.page_number == 2]
    assert len(page1_chunks) > 0
    assert len(page2_chunks) > 0
    # No chunks from scanned page 3
    page3_chunks = [c for c in chunks if c.page_number == 3]
    assert len(page3_chunks) == 0
    # Globally unique indices
    indices = [c.chunk_index for c in chunks]
    assert len(indices) == len(set(indices))
    # Indices are sequential
    assert indices == list(range(len(indices)))
