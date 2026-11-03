"""Tests for the cross-encoder reranker.

Uses mocks where sentence-transformers is not installed or model loading fails.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from oau_ai.rag.service import Reranker
from oau_ai.retrieval.service import RetrievedChunk


def _make_chunk(chunk_id: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        backend_thesis_id="thesis-1",
        text=text,
        page_number=1,
        section=None,
        chunk_index=0,
        access_level="public",
        provenance={},
    )


def test_reranker_not_available_when_no_package():
    """Reranker reports unavailable when sentence-transformers is not installed."""
    reranker = Reranker()
    reranker._available = False
    reranker._load_error = (
        "sentence-transformers not installed: No module named 'sentence_transformers'"
    )
    assert reranker.available is False


def test_reranker_returns_original_order_when_unavailable():
    """Reranker returns chunks in original order when unavailable (never falsely claims reranking)."""
    reranker = Reranker()
    reranker._available = False
    reranker._load_error = "model not available"

    chunks = [_make_chunk("c-1", "alpha text"), _make_chunk("c-2", "beta text")]

    result = reranker.rerank("query", chunks, top_k=5)

    assert result == chunks  # Same order, no false reranking claim


def test_reranker_empty_input():
    """Reranker returns empty list for empty input."""
    reranker = Reranker()
    reranker._available = True
    reranker._model = MagicMock()

    result = reranker.rerank("query", [])
    assert result == []


def test_reranker_reranks_by_score():
    """Reranker sorts chunks by cross-encoder score descending."""
    reranker = Reranker()
    reranker._available = True

    # Mock CrossEncoder.predict to return scores in reverse order
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.1, 0.9, 0.5]  # c-2 should be first
    reranker._model = mock_model

    chunks = [
        _make_chunk("c-1", "alpha"),
        _make_chunk("c-2", "beta"),
        _make_chunk("c-3", "gamma"),
    ]

    result = reranker.rerank("query", chunks)

    assert result[0].chunk_id == "c-2"  # highest score (0.9)
    assert result[1].chunk_id == "c-3"  # second (0.5)
    assert result[2].chunk_id == "c-1"  # lowest (0.1)


def test_reranker_top_k_limits_results():
    """Reranker respects top_k parameter."""
    reranker = Reranker()
    reranker._available = True
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.1, 0.9, 0.5]
    reranker._model = mock_model

    chunks = [
        _make_chunk("c-1", "alpha"),
        _make_chunk("c-2", "beta"),
        _make_chunk("c-3", "gamma"),
    ]

    result = reranker.rerank("query", chunks, top_k=2)

    assert len(result) == 2
    assert result[0].chunk_id == "c-2"


def test_reranker_failure_degrades_gracefully():
    """Reranker returns original order if prediction fails."""
    reranker = Reranker()
    reranker._available = True
    mock_model = MagicMock()
    mock_model.predict.side_effect = RuntimeError("model crash")
    reranker._model = mock_model

    chunks = [_make_chunk("c-1", "alpha"), _make_chunk("c-2", "beta")]

    result = reranker.rerank("query", chunks)

    assert result == chunks  # Falls back to original order
