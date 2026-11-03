"""P2 regression tests — orphan filtering, access enforcement, citations, abstention.

Unit tests with mocked database sessions and mocked providers. No network,
no model downloads, no paid calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.errors import ProviderUnavailableError
from oau_ai.rag.service import RAGService
from oau_ai.retrieval.service import (
    RetrievedChunk,
    RetrievalService,
    rrf_fuse,
)


def _actor(user_id="user-1", roles=None):
    return ActorContext(
        user_id=user_id, roles=roles or ["student"], department="CS", trace_id="t-p2"
    )


def _document(
    doc_id="doc-1",
    thesis_id="thesis-1",
    access="private",
    owner="user-1",
):
    document = MagicMock()
    document.id = doc_id
    document.backend_thesis_id = thesis_id
    document.access_level = access
    document.backend_user_id = owner
    document.thesis_metadata = {"title": thesis_id}
    document.created_at = None
    return document


def _chunk(chunk_id, doc_id="doc-1", text="crop rotation improves soil nitrogen"):
    chunk = MagicMock()
    chunk.id = chunk_id
    chunk.document_id = doc_id
    chunk.text = text
    chunk.chunk_index = 0
    chunk.page_id = None
    return chunk


def _session_returning(rows):
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute.return_value = result
    return session


def _retrieved(chunk_id, doc_id="doc-1", thesis_id="thesis-1", text="crop rotation"):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        backend_thesis_id=thesis_id,
        text=text,
        page_number=1,
        section=None,
        chunk_index=0,
        access_level="public",
        provenance={"document_id": doc_id},
    )


# --------------------------------------------------------------------------
# §1 Orphan / unresolvable vector handling
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_returns_only_rows_present_in_database():
    """A point whose chunk row is gone must not resolve."""
    service = RetrievalService(
        db_session=_session_returning([(_chunk("c1"), _document(), None)])
    )

    resolved, unresolved = await service.resolve_authorized_chunks(
        ["c1", "c-orphan"], _actor()
    )

    assert set(resolved) == {"c1"}
    assert unresolved == ["c-orphan"]


@pytest.mark.asyncio
async def test_resolve_treats_access_denied_as_unresolved():
    """SQL excludes unauthorized documents, so their chunks never resolve."""
    service = RetrievalService(db_session=_session_returning([]))

    resolved, unresolved = await service.resolve_authorized_chunks(
        ["c-private"], _actor(user_id="someone-else")
    )

    assert resolved == {}
    assert unresolved == ["c-private"]


@pytest.mark.asyncio
async def test_resolve_empty_input():
    service = RetrievalService(db_session=AsyncMock())

    assert await service.resolve_authorized_chunks([], _actor()) == ({}, [])


@pytest.mark.asyncio
async def test_resolve_applies_access_conditions_in_query():
    """The resolving query must carry document access conditions."""
    session = _session_returning([])
    service = RetrievalService(db_session=session)

    await service.resolve_authorized_chunks(["c1"], _actor())

    query_str = str(session.execute.call_args[0][0])
    assert "access_level" in query_str or "backend_user_id" in query_str


# --------------------------------------------------------------------------
# §3 Hybrid retrieval: orphans dropped before ranking output
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_drops_orphaned_dense_point():
    """An orphaned Vectorize point never becomes evidence."""
    service = RetrievalService(db_session=_session_returning([]))
    service.resolve_authorized_chunks = AsyncMock(return_value=({}, ["chunk-gone"]))

    results = await service.hybrid_retrieve(
        actor_context=_actor(),
        query="crop rotation",
        query_vector=[0.1],
        vectorize_results=[
            {"metadata": {"chunk_id": "chunk-gone", "document_id": "doc-1"}, "score": 0.95}
        ],
        top_k=5,
    )

    assert results == []


@pytest.mark.asyncio
async def test_hybrid_keeps_valid_and_drops_invalid():
    """Mixed results: only the resolvable, authorized chunk survives."""
    service = RetrievalService(db_session=_session_returning([]))
    from oau_ai.retrieval.service import AuthorizedChunk

    service.resolve_authorized_chunks = AsyncMock(
        return_value=(
            {
                "c1": AuthorizedChunk(
                    chunk_id="c1",
                    document_id="doc-1",
                    backend_thesis_id="thesis-1",
                    text="crop rotation improves soil nitrogen",
                    page_number=1,
                    section=None,
                    chunk_index=0,
                    access_level="public",
                    provenance={"document_id": "doc-1"},
                )
            },
            ["c-private"],
        )
    )

    results = await service.hybrid_retrieve(
        actor_context=_actor(),
        query="crop rotation",
        query_vector=[0.1],
        vectorize_results=[
            {"metadata": {"chunk_id": "c1", "document_id": "doc-1"}, "score": 0.9},
            {"metadata": {"chunk_id": "c-private", "document_id": "doc-9"}, "score": 0.99},
        ],
        top_k=5,
    )

    assert [r.chunk_id for r in results] == ["c1"]
    assert all(r.access_level == "public" for r in results)


@pytest.mark.asyncio
async def test_hybrid_ignores_dense_match_without_chunk_id():
    service = RetrievalService(db_session=_session_returning([]))
    service.resolve_authorized_chunks = AsyncMock(return_value=({}, []))

    results = await service.hybrid_retrieve(
        actor_context=_actor(),
        query="q",
        query_vector=[0.1],
        vectorize_results=[{"metadata": {"document_id": "doc-1"}, "score": 0.9}],
        top_k=5,
    )

    assert results == []


@pytest.mark.asyncio
async def test_hybrid_logs_orphan_pruning(caplog):
    service = RetrievalService(db_session=_session_returning([]))
    service.resolve_authorized_chunks = AsyncMock(return_value=({}, ["x"]))

    with caplog.at_level("INFO", logger="oau_ai.retrieval"):
        await service.hybrid_retrieve(
            actor_context=_actor(),
            query="q",
            query_vector=[0.1],
            vectorize_results=[{"metadata": {"chunk_id": "x"}, "score": 0.9}],
            top_k=5,
        )

    assert "unresolved_results_pruned" in caplog.text
    # Log line carries counts only, never chunk text.
    assert "crop rotation" not in caplog.text


def test_rrf_does_not_double_count_duplicate_chunk_in_one_list():
    """A repeated chunk inside a single ranked list contributes once."""
    duplicated = [
        {"chunk_id": "a", "score": 0.9},
        {"chunk_id": "a", "score": 0.8},
        {"chunk_id": "b", "score": 0.7},
    ]

    fused = dict(rrf_fuse([duplicated], k=60))

    assert fused["a"] == pytest.approx(1.0 / 61)
    assert fused["b"] == pytest.approx(1.0 / 63)


@pytest.mark.asyncio
async def test_hybrid_labels_retrieval_source_and_scores():
    from oau_ai.retrieval.service import AuthorizedChunk

    service = RetrievalService(db_session=_session_returning([]))
    service.resolve_authorized_chunks = AsyncMock(
        return_value=(
            {
                "c1": AuthorizedChunk(
                    chunk_id="c1",
                    document_id="doc-1",
                    backend_thesis_id="thesis-1",
                    text="text",
                    page_number=1,
                    section=None,
                    chunk_index=0,
                    access_level="public",
                    provenance={},
                )
            },
            [],
        )
    )

    results = await service.hybrid_retrieve(
        actor_context=_actor(),
        query="q",
        query_vector=[0.1],
        vectorize_results=[{"metadata": {"chunk_id": "c1"}, "score": 0.77}],
        top_k=5,
    )

    assert results[0].retrieval_source == "dense"
    assert results[0].dense_score == 0.77
    assert results[0].fused_score is not None


# --------------------------------------------------------------------------
# §4/§5 RAG: abstention reasons, degraded retrieval, LLM boundary
# --------------------------------------------------------------------------


def _rag_service(
    retrieval=None,
    vectorize=None,
    reranker=None,
    memory=None,
):
    service = RAGService.__new__(RAGService)
    service.db_session = None
    service.llm_router = MagicMock()
    service.retrieval_service = retrieval or MagicMock()
    service.embedding_service = MagicMock()
    service.vectorize_service = vectorize or MagicMock()
    service.jev_client = MagicMock()
    service.reranker = reranker or MagicMock()
    service.memory_service = memory or MagicMock()
    service.reranker.rerank = MagicMock(side_effect=lambda q, c, top_k=None: c)
    service._classify_with_jev = AsyncMock(
        return_value=MagicMock(decision=MagicMock(value="allow"))
    )
    service._embed_question = AsyncMock(return_value=[0.1, 0.2])
    service._query_vectorize = AsyncMock(return_value=([], False))
    service.memory_service.retrieve_relevant_memories = AsyncMock(
        side_effect=Exception("memory unavailable")
    )
    return service


@pytest.mark.asyncio
async def test_ask_abstains_with_no_evidence_reason():
    retrieval = MagicMock()
    retrieval.hybrid_retrieve = AsyncMock(return_value=[])
    service = _rag_service(retrieval=retrieval)

    result = await service.ask("What about crops?", _actor())

    assert result.insufficient_evidence is True
    assert result.abstention_reason == "no_evidence"
    assert result.answer == ""
    assert result.citations == []
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_ask_reports_degraded_retrieval_separately():
    retrieval = MagicMock()
    retrieval.hybrid_retrieve = AsyncMock(return_value=[])
    service = _rag_service(retrieval=retrieval)
    service._query_vectorize = AsyncMock(return_value=([], True))

    result = await service.ask("What about crops?", _actor())

    assert result.insufficient_evidence is True
    assert result.abstention_reason == "retrieval_degraded"
    assert "Semantic retrieval is unavailable" in result.message


@pytest.mark.asyncio
async def test_vectorize_failure_is_reported_as_degraded():
    vectorize = MagicMock()
    vectorize.is_configured = MagicMock(return_value=True)
    vectorize.query = MagicMock(
        side_effect=ProviderUnavailableError(
            message="index down", component="vectorize"
        )
    )
    service = RAGService.__new__(RAGService)
    service.vectorize_service = vectorize

    matches, degraded = await service._query_vectorize(
        [0.1], 5, None, _actor()
    )

    assert matches == []
    assert degraded is True


@pytest.mark.asyncio
async def test_vectorize_unconfigured_is_degraded():
    vectorize = MagicMock()
    vectorize.is_configured = MagicMock(return_value=False)
    service = RAGService.__new__(RAGService)
    service.vectorize_service = vectorize

    matches, degraded = await service._query_vectorize([0.1], 5, None, _actor())

    assert matches == []
    assert degraded is True


@pytest.mark.asyncio
async def test_unauthorized_and_orphan_content_never_reaches_the_llm():
    """Only authorized, resolved chunks are passed to answer generation."""
    retrieval = MagicMock()
    retrieval.hybrid_retrieve = AsyncMock(
        return_value=[_retrieved("c1", text="public thesis evidence about soil")]
    )
    service = _rag_service(retrieval=retrieval)
    service._generate_answer = AsyncMock(
        return_value={
            "answer": "Soil matters [Source 1].",
            "model": "m",
            "provider": "p",
        }
    )

    await service.ask("Soil?", _actor(user_id="user-b"))

    chunks = service._generate_answer.call_args[0][1]
    assert [c.chunk_id for c in chunks] == ["c1"]
    serialized = repr(chunks)
    assert "private-secret" not in serialized
    assert "c-private" not in serialized


@pytest.mark.asyncio
async def test_weak_evidence_marks_abstention_reason():
    retrieval = MagicMock()
    retrieval.hybrid_retrieve = AsyncMock(
        return_value=[_retrieved("c1"), _retrieved("c2"), _retrieved("c3")]
    )
    service = _rag_service(retrieval=retrieval)
    # Answer cites nothing -> confidence floor -> abstain.
    service._generate_answer = AsyncMock(
        return_value={"answer": "No citations at all.", "model": "m", "provider": "p"}
    )

    result = await service.ask("Soil?", _actor())

    assert result.insufficient_evidence is True
    assert result.abstention_reason == "weak_evidence"


# --------------------------------------------------------------------------
# §4 Citation validation
# --------------------------------------------------------------------------


def _citation_chunks():
    from oau_ai.retrieval.service import AuthorizedChunk

    return [
        AuthorizedChunk(
            chunk_id="c1",
            document_id="doc-1",
            backend_thesis_id="thesis-1",
            text="crop rotation improves soil nitrogen",
            page_number=1,
            section=None,
            chunk_index=0,
            access_level="public",
            provenance={},
        ),
        AuthorizedChunk(
            chunk_id="c2",
            document_id="doc-1",
            backend_thesis_id="thesis-1",
            text="irrigation scheduling reduces water waste",
            page_number=2,
            section=None,
            chunk_index=1,
            access_level="public",
            provenance={},
        ),
    ]


def _rag_for_citations():
    service = RAGService.__new__(RAGService)
    return service


def test_citation_rejects_out_of_range_source():
    service = _rag_for_citations()

    citations = service._validate_citations(
        "Crop rotation improves nitrogen [Source 7].", _citation_chunks()
    )

    assert citations == []


def test_citation_rejects_unrelated_sentence():
    """A valid index bolted onto unrelated prose is not a grounded citation."""
    service = _rag_for_citations()

    citations = service._validate_citations(
        "The weather in Lagos was unusually cold [Source 1].", _citation_chunks()
    )

    assert citations == []


def test_citation_accepts_grounded_sentence():
    service = _rag_for_citations()

    citations = service._validate_citations(
        "Crop rotation improves soil nitrogen [Source 1].", _citation_chunks()
    )

    assert [c.chunk_id for c in citations] == ["c1"]


def test_citation_is_case_insensitive():
    service = _rag_for_citations()

    citations = service._validate_citations(
        "Crop rotation improves soil nitrogen [source 1].", _citation_chunks()
    )

    assert [c.chunk_id for c in citations] == ["c1"]


def test_citation_deduplicates_repeated_markers():
    service = _rag_for_citations()

    citations = service._validate_citations(
        "Crop rotation improves soil nitrogen [Source 1] and again [Source 1].",
        _citation_chunks(),
    )

    assert len(citations) == 1


def test_citation_ignores_malformed_marker():
    service = _rag_for_citations()

    citations = service._validate_citations(
        "Crop rotation improves soil nitrogen [Source abc].", _citation_chunks()
    )

    assert citations == []


def test_citation_relevance_score_uses_fused_scores():
    service = _rag_for_citations()

    citations = service._validate_citations(
        "Crop rotation improves soil nitrogen [Source 1].",
        _citation_chunks(),
        scores={"c1": 0.0421},
    )

    assert citations[0].relevance_score == pytest.approx(0.0421)


def test_citation_rejects_unknown_chunk_id_in_map():
    """A chunk whose id is not in the authorized map is never cited."""
    service = _rag_for_citations()
    chunks = _citation_chunks()
    chunks[0].chunk_id = "c1"

    citations = service._validate_citations(
        "Crop rotation improves soil nitrogen [Source 1].", chunks
    )

    assert [c.chunk_id for c in citations] == ["c1"]
