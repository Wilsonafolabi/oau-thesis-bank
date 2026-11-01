"""Tests for strengthened citation validation (text overlap anti-fabrication).

Unit tests use mocked chunks; no live services.
"""

from oau_ai.auth.middleware import ActorContext
from oau_ai.rag.service import Citation, RAGService


def _make_chunk(chunk_id, document_id, backend_thesis_id, text, page_number=1):
    chunk = type(
        "MockChunk",
        (),
        {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "backend_thesis_id": backend_thesis_id,
            "text": text,
            "page_number": page_number,
            "section": None,
            "chunk_index": 0,
            "access_level": "public",
            "provenance": {"document_id": document_id},
        },
    )()
    return chunk


def test_validate_citation_strips_invalid_source_index():
    """Citation referencing non-existent source index is stripped."""
    chunks = [_make_chunk("c-1", "doc-1", "thesis-1", "The quick brown fox jumps.")]
    service = RAGService.__new__(RAGService)

    # Cites Source 5 which doesn't exist
    answer = "The fox is quick [Source 1] and also blue [Source 5]."
    citations = service._validate_citations(answer, chunks)

    assert len(citations) == 1
    assert citations[0].chunk_id == "c-1"


def test_validate_citation_strips_fabricated_citation():
    """Citation with no text overlap with source chunk is stripped (anti-fabrication)."""
    chunks = [
        _make_chunk("c-1", "doc-1", "thesis-1", "The quick brown fox jumps over the lazy dog."),
        _make_chunk("c-2", "doc-1", "thesis-1", "Climate change affects polar bear habitats."),
    ]
    service = RAGService.__new__(RAGService)

    # Cites Source 1 (fox text) but talks about climate (no overlap with fox chunk)
    answer = "The climate is warming rapidly [Source 1]."
    citations = service._validate_citations(answer, chunks)

    # Source 1 text is about foxes, answer is about climate -> no overlap -> stripped
    assert len(citations) == 0


def test_validate_citation_keeps_real_citation():
    """Citation with meaningful text overlap with source is kept."""
    chunks = [
        _make_chunk(
            "c-1",
            "doc-1",
            "thesis-1",
            "The methodology used a randomized controlled trial with 500 participants.",
        )
    ]
    service = RAGService.__new__(RAGService)

    # Cites Source 1 and the text shares words (methodology, participants)
    answer = "The study used a methodology with 500 participants [Source 1]."
    citations = service._validate_citations(answer, chunks)

    assert len(citations) == 1
    assert citations[0].chunk_id == "c-1"


def test_validate_citation_multiple_valid():
    """Multiple valid citations are all returned."""
    chunks = [
        _make_chunk("c-1", "doc-1", "thesis-1", "Climate change affects polar bears."),
        _make_chunk("c-2", "doc-1", "thesis-1", "Renewable energy reduces carbon emissions."),
    ]
    service = RAGService.__new__(RAGService)

    answer = "Climate change affects polar bears [Source 1] and renewable energy reduces emissions [Source 2]."
    citations = service._validate_citations(answer, chunks)

    assert len(citations) == 2
    assert citations[0].chunk_id == "c-1"
    assert citations[1].chunk_id == "c-2"


def test_validate_citation_no_citations():
    """Answer with no citations returns empty list."""
    chunks = [_make_chunk("c-1", "doc-1", "thesis-1", "Some text.")]
    service = RAGService.__new__(RAGService)

    citations = service._validate_citations("No citations here.", chunks)
    assert citations == []


def test_validate_citation_duplicate_source_index():
    """Same source cited multiple times is returned only once."""
    chunks = [_make_chunk("c-1", "doc-1", "thesis-1", "The fox is quick.")]
    service = RAGService.__new__(RAGService)

    answer = "The fox is quick [Source 1] indeed very quick [Source 1]."
    citations = service._validate_citations(answer, chunks)

    assert len(citations) == 1
    assert citations[0].chunk_id == "c-1"


def test_text_overlaps_detects_shared_words():
    """_text_overlaps returns True when answer and chunk share content words."""
    service = RAGService.__new__(RAGService)

    assert service._text_overlaps("climate change polar bears", "Climate change affects polar bear habitats") is True


def test_text_overlaps_no_shared_words():
    """_text_overlaps returns False when no meaningful overlap."""
    service = RAGService.__new__(RAGService)

    assert service._text_overlaps("quantum computing algorithms", "The fox is quick brown") is False


def test_citation_has_provenance_fields():
    """Citation dataclass includes all provenance fields."""
    citation = Citation(
        chunk_id="c-1",
        document_id="doc-1",
        backend_thesis_id="thesis-1",
        text_snippet="The fox is quick.",
        page_number=1,
        section=None,
        relevance_score=0.95,
    )
    assert citation.chunk_id == "c-1"
    assert citation.document_id == "doc-1"
    assert citation.backend_thesis_id == "thesis-1"
    assert citation.page_number == 1
    assert citation.relevance_score == 0.95
