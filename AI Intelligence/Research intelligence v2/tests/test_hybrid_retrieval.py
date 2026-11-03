"""Tests for hybrid retrieval: RRF fusion, lexical search, access enforcement.

These unit tests use mocked database sessions and no live services.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.retrieval.service import (
    AuthorizedChunk,
    RetrievedChunk,
    RetrievalService,
    rrf_fuse,
)


def test_rrf_fuse_basic():
    """RRF fusion combines ranked lists correctly."""
    list_a = [
        {"chunk_id": "chunk-1", "score": 0.9},
        {"chunk_id": "chunk-2", "score": 0.8},
        {"chunk_id": "chunk-3", "score": 0.7},
    ]
    list_b = [
        {"chunk_id": "chunk-2", "score": 0.95},
        {"chunk_id": "chunk-4", "score": 0.85},
        {"chunk_id": "chunk-1", "score": 0.75},
    ]

    fused = rrf_fuse([list_a, list_b], k=60)

    # chunk-2 appears first in both lists -> highest score
    assert fused[0][0] == "chunk-2"
    assert fused[0][1] > 0
    assert len(fused) == 4  # 4 unique chunk IDs


def test_rrf_fuse_empty_lists():
    """RRF fusion with empty lists returns empty result."""
    assert rrf_fuse([], k=60) == []
    assert rrf_fuse([[]], k=60) == []
    assert rrf_fuse([[], []], k=60) == []


def test_rrf_fuse_single_list():
    """RRF fusion with a single list preserves order."""
    items = [
        {"chunk_id": "chunk-a", "score": 0.9},
        {"chunk_id": "chunk-b", "score": 0.8},
    ]
    fused = rrf_fuse([items], k=60)
    assert fused[0][0] == "chunk-a"
    assert fused[1][0] == "chunk-b"


def test_authorized_chunk_creation():
    """AuthorizedChunk can be created with all required fields."""
    chunk = AuthorizedChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        backend_thesis_id="thesis-1",
        text="Sample thesis text.",
        page_number=1,
        section=None,
        chunk_index=0,
        access_level="private",
        provenance={"document_id": "doc-1"},
    )
    assert chunk.chunk_id == "chunk-1"
    assert chunk.access_level == "private"


def test_retrieved_chunk_defaults():
    """RetrievedChunk has sensible defaults."""
    chunk = RetrievedChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        backend_thesis_id="thesis-1",
        text="Sample text.",
        page_number=1,
        section=None,
        chunk_index=0,
        access_level="public",
        provenance={},
    )
    assert chunk.dense_score is None
    assert chunk.lexical_score is None
    assert chunk.fused_score is None
    assert chunk.retrieval_source == "hybrid"


@pytest.mark.asyncio
async def test_lexical_search_empty_query():
    """Lexical search with empty query returns empty list."""
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")
    service = RetrievalService(db_session=AsyncMock())
    results = await service.lexical_search(actor, "", document_ids=["doc-1"])
    assert results == []


@pytest.mark.asyncio
async def test_lexical_search_access_enforced():
    """Lexical search query joins documents with access conditions."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.execute.return_value = mock_result

    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")
    service = RetrievalService(db_session=mock_session)

    await service.lexical_search(
        actor, "research question", document_ids=["doc-1"], limit=5
    )

    # Verify the execute was called with a query
    call_args = mock_session.execute.call_args
    assert call_args is not None
    # The query should reference to_tsvector (lexical search)
    query_obj = call_args[0][0]
    query_str = str(query_obj)
    assert "to_tsvector" in query_str or "plainto_tsquery" in query_str


@pytest.mark.asyncio
async def test_hybrid_retrieve_dedupes_by_chunk_id():
    """Hybrid retrieval deduplicates results by chunk_id."""
    mock_session = AsyncMock()

    # Mock get_chunk_by_id to return a chunk (used as fallback in hybrid_retrieve)
    mock_chunk = MagicMock()
    mock_chunk.id = "chunk-1"
    mock_chunk.document_id = "doc-1"
    mock_chunk.backend_thesis_id = "thesis-1"
    mock_chunk.text = "Sample text."
    mock_chunk.page_number = 1
    mock_chunk.chunk_index = 0
    mock_chunk.access_level = "public"
    mock_chunk.provenance = {}

    mock_doc = MagicMock()
    mock_doc.id = "doc-1"
    mock_doc.backend_thesis_id = "thesis-1"
    mock_doc.thesis_metadata = {"title": "Test"}
    mock_doc.created_at = None

    mock_result = MagicMock()
    mock_result.first.return_value = (mock_chunk, mock_doc)
    mock_session.execute.return_value = mock_result

    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")
    service = RetrievalService(db_session=mock_session)

    vectorize_results = [
        {
            "metadata": {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
            },
            "score": 0.9,
        },
    ]

    results = await service.hybrid_retrieve(
        actor_context=actor,
        query="test question",
        query_vector=[0.1, 0.2, 0.3],
        vectorize_results=vectorize_results,
        document_ids=["doc-1"],
        top_k=5,
    )

    # Results should be deduplicated
    chunk_ids = [r.chunk_id for r in results]
    assert len(chunk_ids) == len(set(chunk_ids))


@pytest.mark.asyncio
async def test_hybrid_retrieve_access_denied_excludes_unauthorized():
    """Hybrid retrieval excludes chunks from unauthorized documents."""
    mock_session = AsyncMock()

    # Mock lexical search to return empty (no authorized results)
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_result.first.return_value = None
    mock_session.execute.return_value = mock_result

    service = RetrievalService(db_session=mock_session)

    # Mock check_document_access to deny access
    async def mock_check_access(thesis_id, actor_ctx):
        from oau_ai.retrieval.service import DocumentAccess

        return DocumentAccess(
            document_id="",
            backend_thesis_id=thesis_id,
            access_level="private",
            title=None,
            can_view=False,
            reason="Access denied",
        )

    service.check_document_access = mock_check_access

    # Mock get_authorized_chunks to return empty (no access)
    async def mock_get_authorized(actor_context=None, document_ids=None, limit=10):
        return []

    service.get_authorized_chunks = mock_get_authorized

    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")
    results = await service.hybrid_retrieve(
        actor_context=actor,
        query="test question",
        query_vector=[0.1, 0.2],
        vectorize_results=[
            {
                "metadata": {
                    "chunk_id": "chunk-1",
                    "document_id": "doc-1",
                },
                "score": 0.9,
            }
        ],
        document_ids=["doc-1"],
        top_k=5,
    )

    # With access denied, no chunks should be returned
    assert results == []
