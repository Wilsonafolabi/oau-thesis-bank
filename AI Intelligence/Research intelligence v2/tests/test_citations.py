"""Tests for citation validation and unsupported-answer rejection."""

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.rag.service import RAGService


class MockChunk:
    def __init__(self, chunk_id, document_id, backend_thesis_id, text, page_number=None):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.backend_thesis_id = backend_thesis_id
        self.text = text
        self.page_number = page_number
        self.section = None
        self.chunk_index = 0
        self.access_level = "public"
        self.provenance = {
            "document_id": document_id,
            "source_file": backend_thesis_id,
            "access_classification": "public",
        }


def test_citation_validation_strips_invalid_citations():
    """Citations that don't match retrieved chunks are stripped."""
    chunks = [
        MockChunk("chunk-1", "doc-1", "thesis-1", "The quick brown fox."),
        MockChunk("chunk-2", "doc-1", "thesis-1", "Jumped over the lazy dog."),
    ]

    service = RAGService.__new__(RAGService)

    # Answer cites Source 1 (valid) and Source 5 (invalid - only 2 sources)
    answer = "The fox is quick [Source 1] and also blue [Source 5]."
    citations = service._validate_citations(answer, chunks)

    # Only Source 1 should be validated
    assert len(citations) == 1
    assert citations[0].chunk_id == "chunk-1"


def test_citation_validation_no_citations():
    """Answer with no citations returns empty list."""
    chunks = [MockChunk("chunk-1", "doc-1", "thesis-1", "Some text.")]
    service = RAGService.__new__(RAGService)

    citations = service._validate_citations("No citations here.", chunks)
    assert citations == []


def test_citation_validation_multiple_valid():
    """Multiple valid citations are all returned."""
    chunks = [
        MockChunk("chunk-1", "doc-1", "thesis-1", "First fact."),
        MockChunk("chunk-2", "doc-1", "thesis-1", "Second fact."),
    ]
    service = RAGService.__new__(RAGService)

    answer = "First [Source 1] and second [Source 2]."
    citations = service._validate_citations(answer, chunks)

    assert len(citations) == 2
    assert citations[0].chunk_id == "chunk-1"
    assert citations[1].chunk_id == "chunk-2"


def test_confidence_calculation_no_chunks():
    """Confidence is 0.0 when there are no chunks."""
    service = RAGService.__new__(RAGService)

    confidence = service._calculate_confidence([], [])
    assert confidence == 0.0


def test_confidence_calculation_with_citations():
    """Confidence scales with citation coverage."""
    chunks = [
        MockChunk("chunk-1", "doc-1", "thesis-1", "Text 1"),
        MockChunk("chunk-2", "doc-1", "thesis-1", "Text 2"),
        MockChunk("chunk-3", "doc-1", "thesis-1", "Text 3"),
    ]
    service = RAGService.__new__(RAGService)

    # All 3 chunks cited
    citations = [
        type("C", (), {"chunk_id": c.chunk_id})() for c in chunks
    ]
    confidence = service._calculate_confidence(citations, chunks)
    assert 0.0 <= confidence <= 1.0


def test_rag_service_initialization():
    """RAGService initializes with default components."""
    service = RAGService()
    assert service.llm_router is not None
    assert service.retrieval_service is not None
    assert service.embedding_service is not None
    assert service.vectorize_service is not None
    assert service.jev_client is not None
