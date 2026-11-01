"""Tests for the Research Intelligence Agent — tools module.

Tests tool allowlist, call limits, and tool execution with mocked services.
All tests are offline; no live services or credentials required.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oau_ai.agent.tools import (
    MAX_TOOL_CALLS,
    ResearchTools,
    ToolExecutionError,
    ToolNotAllowedError,
    TOOL_ALLOWLIST,
)
from oau_ai.auth.middleware import ActorContext


def test_tool_allowlist_contains_expected_tools():
    """Tool allowlist contains only existing V2 capabilities."""
    assert "hybrid_retrieve" in TOOL_ALLOWLIST
    assert "rag_answer" in TOOL_ALLOWLIST
    assert "jev_verify" in TOOL_ALLOWLIST
    # Research-gap and researcher-network are NOT in the allowlist
    # because no functioning implementation exists.
    assert "research_gap" not in TOOL_ALLOWLIST
    assert "researcher_network" not in TOOL_ALLOWLIST


def test_tools_is_allowed():
    """ResearchTools.is_allowed returns correct results."""
    tools = ResearchTools()
    assert tools.is_allowed("hybrid_retrieve") is True
    assert tools.is_allowed("rag_answer") is True
    assert tools.is_allowed("jev_verify") is True
    assert tools.is_allowed("research_gap") is False
    assert tools.is_allowed("researcher_network") is False
    assert tools.is_allowed("unknown_tool") is False


def test_tools_call_limit():
    """ResearchTools enforces maximum tool call limit."""
    tools = ResearchTools()
    assert tools.can_call_more() is True

    for _ in range(MAX_TOOL_CALLS):
        tools.record_call()

    assert tools.can_call_more() is False


@pytest.mark.asyncio
async def test_hybrid_retrieve_not_allowed_raises():
    """Calling a non-allowed tool raises ToolNotAllowedError."""
    tools = ResearchTools()
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    # Temporarily remove hybrid_retrieve from allowlist by monkeypatching
    original = tools.is_allowed
    tools.is_allowed = lambda name: False

    with pytest.raises(ToolNotAllowedError):
        await tools.hybrid_retrieve(
            question="Q?",
            question_vector=[0.1, 0.2],
            actor_context=actor.to_dict(),
        )

    tools.is_allowed = original


@pytest.mark.asyncio
async def test_hybrid_retrieve_call_limit():
    """hybrid_retrieve raises when call limit is reached."""
    tools = ResearchTools()
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    # Exhaust call limit
    for _ in range(MAX_TOOL_CALLS):
        tools.record_call()

    with pytest.raises(ToolExecutionError) as exc_info:
        await tools.hybrid_retrieve(
            question="Q?",
            question_vector=[0.1, 0.2],
            actor_context=actor.to_dict(),
        )

    assert "Maximum tool call limit" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rag_answer_not_allowed_raises():
    """rag_answer raises ToolNotAllowedError when not in allowlist."""
    tools = ResearchTools()
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    original = tools.is_allowed
    tools.is_allowed = lambda name: False

    with pytest.raises(ToolNotAllowedError):
        await tools.rag_answer(
            question="Q?",
            actor_context=actor.to_dict(),
        )

    tools.is_allowed = original


@pytest.mark.asyncio
async def test_jev_verify_not_allowed_raises():
    """jev_verify raises ToolNotAllowedError when not in allowlist."""
    tools = ResearchTools()
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    original = tools.is_allowed
    tools.is_allowed = lambda name: False

    with pytest.raises(ToolNotAllowedError):
        await tools.jev_verify(
            question="Q?",
            actor_context=actor.to_dict(),
        )

    tools.is_allowed = original


@pytest.mark.asyncio
async def test_hybrid_retrieve_returns_structured_evidence():
    """hybrid_retrieve returns evidence with provenance fields."""
    tools = ResearchTools()
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    # Mock the retrieval service's hybrid_retrieve
    mock_rc = MagicMock()
    mock_rc.chunk_id = "chunk-1"
    mock_rc.document_id = "doc-1"
    mock_rc.backend_thesis_id = "thesis-1"
    mock_rc.text = "Sample thesis content about X."
    mock_rc.page_number = 1
    mock_rc.chunk_index = 0
    mock_rc.access_level = "public"
    mock_rc.dense_score = 0.9
    mock_rc.lexical_score = 0.8
    mock_rc.fused_score = 0.85
    mock_rc.retrieval_source = "hybrid"
    mock_rc.provenance = {"document_id": "doc-1"}

    with patch.object(
        tools.retrieval_service,
        "hybrid_retrieve",
        AsyncMock(return_value=[mock_rc]),
    ):
        results = await tools.hybrid_retrieve(
            question="What is X?",
            question_vector=[0.1, 0.2, 0.3],
            actor_context=actor.to_dict(),
            top_k=5,
        )

    assert len(results) == 1
    assert results[0]["chunk_id"] == "chunk-1"
    assert results[0]["document_id"] == "doc-1"
    assert results[0]["backend_thesis_id"] == "thesis-1"
    assert results[0]["text"] == "Sample thesis content about X."
    assert results[0]["page_number"] == 1
    assert results[0]["fused_score"] == 0.85
    assert results[0]["retrieval_source"] == "hybrid"
    assert "provenance" in results[0]


@pytest.mark.asyncio
async def test_rag_answer_returns_structured_result():
    """rag_answer returns answer, citations, confidence, and sufficiency."""
    tools = ResearchTools()
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    mock_result = MagicMock()
    mock_result.answer = "The answer is X."
    mock_result.citations = []
    mock_result.confidence = 0.9
    mock_result.decision_engine = "deepseek"
    mock_result.llm_tier = 1
    mock_result.trace_id = "trace-1"
    mock_result.request_id = "req-1"
    mock_result.insufficient_evidence = False
    mock_result.message = None

    with patch.object(tools.rag_service, "ask", AsyncMock(return_value=mock_result)):
        result = await tools.rag_answer(
            question="What is X?",
            actor_context=actor.to_dict(),
            top_k=5,
        )

    assert result["answer"] == "The answer is X."
    assert result["confidence"] == 0.9
    assert result["decision_engine"] == "deepseek"
    assert result["llm_tier"] == 1
    assert result["insufficient_evidence"] is False


@pytest.mark.asyncio
async def test_jev_verify_returns_structured_decision():
    """jev_verify returns decision, confidence, engine, and provenance."""
    tools = ResearchTools()
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    # Mock TypedDecisionRouter.route used inside jev_verify.
    mock_decision = MagicMock()
    mock_decision.decision.value = "allow"
    mock_decision.confidence = 0.95
    mock_decision.engine_used = "jev"
    mock_decision.fallback_reason.value = "none"
    mock_decision.guardrail_outcome.value = "passed"
    mock_decision.provenance = {"elapsed_ms": 10.5}
    mock_decision.timestamp = "2026-10-29T00:00:00+00:00"

    with patch(
        "oau_ai.jev.router.TypedDecisionRouter"
    ) as mock_router_class:
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=mock_decision)
        mock_router_class.return_value = mock_router

        result = await tools.jev_verify(
            question="What is X?",
            actor_context=actor.to_dict(),
        )

    assert result["decision"] == "allow"
    assert result["confidence"] == 0.95
    assert result["engine_used"] == "jev"
    assert result["guardrail_outcome"] == "passed"
    assert "provenance" in result
