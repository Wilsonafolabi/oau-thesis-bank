"""Tests for the Research Intelligence Agent — state module.

Tests AgentState initialization, property accessors, and dict compatibility.
All tests are offline; no live services or credentials required.
"""

from oau_ai.agent.state import AgentState


def test_agent_state_initialization():
    """AgentState initializes with all required fields."""
    actor = {"user_id": "user-1", "roles": ["student"], "department": "CS"}
    state = AgentState(
        question="What is X?",
        actor_context=actor,
        trace_id="trace-123",
        max_iterations=3,
    )

    assert state["question"] == "What is X?"
    assert state["actor_context"] == actor
    assert state["trace_id"] == "trace-123"
    assert state["max_iterations"] == 3
    assert state["plan"] == []
    assert state["plan_step"] == 0
    assert state["retrieved_evidence"] == []
    assert state["verified_evidence"] == []
    assert state["final_answer"] == ""
    assert state["citations"] == []
    assert state["confidence"] == 0.0
    assert state["insufficient_evidence"] is False
    assert state["tool_calls"] == []
    assert state["iteration_count"] == 0
    assert state["error"] is None
    assert state["status"] == "planning"


def test_agent_state_property_accessors():
    """AgentState property accessors return correct values."""
    actor = {"user_id": "user-1", "roles": ["admin"], "department": "CS"}
    state = AgentState(
        question="Q?",
        actor_context=actor,
        trace_id="trace-abc",
        max_iterations=5,
    )

    assert state.question == "Q?"
    assert state.actor_context == actor
    assert state.trace_id == "trace-abc"
    assert state.plan == []
    assert state.plan_step == 0
    assert state.retrieved_evidence == []
    assert state.verified_evidence == []
    assert state.final_answer == ""
    assert state.citations == []
    assert state.confidence == 0.0
    assert state.insufficient_evidence is False
    assert state.jev_decision is None
    assert state.tool_calls == []
    assert state.iteration_count == 0
    assert state.max_iterations == 5
    assert state.error is None
    assert state.status == "planning"


def test_agent_state_update_dict_compatible():
    """AgentState.update works like dict.update with kwargs."""
    actor = {"user_id": "user-1", "roles": ["student"], "department": "CS"}
    state = AgentState(
        question="Q?",
        actor_context=actor,
        trace_id="trace-abc",
        max_iterations=5,
    )

    state.update({"status": "retrieving", "iteration_count": 1})
    assert state["status"] == "retrieving"
    assert state["iteration_count"] == 1

    state.update(final_answer="The answer is X.", confidence=0.85)
    assert state["final_answer"] == "The answer is X."
    assert state["confidence"] == 0.85


def test_agent_state_default_trace_id():
    """AgentState defaults trace_id to empty string when not provided."""
    actor = {"user_id": "user-1", "roles": ["student"], "department": "CS"}
    state = AgentState(question="Q?", actor_context=actor)
    assert state["trace_id"] == ""
