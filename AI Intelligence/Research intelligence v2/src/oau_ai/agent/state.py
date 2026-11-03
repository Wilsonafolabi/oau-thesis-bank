"""Agent state definition for the Research Intelligence Agent.

Defines the TypedDict state that flows through the agent graph. Follows
LangGraph StateGraph conventions: a typed dictionary that each node reads
and updates, with conditional edges determining the next node.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

# Node names used as graph nodes and conditional-edge targets.
NODE_PLAN = "plan"
NODE_RETRIEVE = "retrieve"
NODE_VERIFY = "verify"
NODE_ANSWER = "answer"
NODE_ABSTAIN = "abstain"
NODE_ERROR = "error"

# Terminal decision values returned by conditional edges.
EDGE_CONTINUE = "continue"
EDGE_ANSWER = "answer"
EDGE_ABSTAIN = "abstain"
EDGE_ERROR = "error"


class AgentState(dict):
    """TypedDict-like state for the Research Intelligence Agent.

    Fields:
        question: The user's research question.
        actor_context: Django-issued actor context (user_id, roles, department, trace_id).
        trace_id: UUIDv4 trace identifier for the request.
        plan: The bounded plan created by the plan node.
        plan_step: Current step index in the plan.
        retrieved_evidence: List of evidence items retrieved so far.
        verified_evidence: List of evidence items that passed JEV verification.
        final_answer: The generated answer (set by the answer node).
        citations: Validated citations mapping to actual evidence.
        confidence: Deterministic confidence score (0.0-1.0).
        insufficient_evidence: Whether evidence is insufficient to answer.
        jev_decision: The JEV decision result for the current request.
        tool_calls: List of tool calls made so far (for iteration tracking).
        iteration_count: Number of reasoning iterations performed.
        max_iterations: Maximum allowed iterations (default 5).
        error: Error message if the agent entered an error state.
        status: Current status (planning, retrieving, verifying, answering, abstaining, error, complete).
    """

    def __init__(
        self,
        *,
        question: str,
        actor_context: dict[str, Any],
        trace_id: Optional[str] = None,
        max_iterations: int = 5,
    ) -> None:
        super().__init__()
        self["question"] = question
        self["actor_context"] = actor_context
        self["trace_id"] = trace_id or ""
        self["plan"] = []
        self["plan_step"] = 0
        self["retrieved_evidence"] = []
        self["verified_evidence"] = []
        self["final_answer"] = ""
        self["citations"] = []
        self["confidence"] = 0.0
        self["insufficient_evidence"] = False
        self["jev_decision"] = None
        self["tool_calls"] = []
        self["iteration_count"] = 0
        self["max_iterations"] = max_iterations
        self["error"] = None
        self["status"] = "planning"

    # Convenience property accessors for dict-style state.
    @property
    def question(self) -> str:
        return self.get("question", "")

    @property
    def actor_context(self) -> dict[str, Any]:
        return self.get("actor_context", {})

    @property
    def trace_id(self) -> Optional[str]:
        return self.get("trace_id")

    @property
    def plan(self) -> list[dict[str, Any]]:
        return self.get("plan", [])

    @property
    def plan_step(self) -> int:
        return self.get("plan_step", 0)

    @property
    def retrieved_evidence(self) -> list[dict[str, Any]]:
        return self.get("retrieved_evidence", [])

    @property
    def verified_evidence(self) -> list[dict[str, Any]]:
        return self.get("verified_evidence", [])

    @property
    def final_answer(self) -> str:
        return self.get("final_answer", "")

    @property
    def citations(self) -> list[dict[str, Any]]:
        return self.get("citations", [])

    @property
    def confidence(self) -> float:
        return self.get("confidence", 0.0)

    @property
    def insufficient_evidence(self) -> bool:
        return self.get("insufficient_evidence", False)

    @property
    def jev_decision(self) -> Optional[dict[str, Any]]:
        return self.get("jev_decision")

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return self.get("tool_calls", [])

    @property
    def iteration_count(self) -> int:
        return self.get("iteration_count", 0)

    @property
    def max_iterations(self) -> int:
        return self.get("max_iterations", 5)

    @property
    def error(self) -> Optional[str]:
        return self.get("error")

    @property
    def status(self) -> str:
        return self.get("status", "planning")

    def update(self, __m: Any = None, **kwargs: Any) -> None:
        """Dict-compatible update that also supports keyword args."""
        if __m is not None:
            super().update(__m)
        if kwargs:
            super().update(kwargs)
