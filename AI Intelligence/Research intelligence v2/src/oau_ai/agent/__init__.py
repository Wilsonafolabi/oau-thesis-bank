"""Research Intelligence Agent — bounded autonomous agent for Phase 3 V2.

Implements a tool-using research workflow following LangGraph orchestration
patterns. When LangGraph is not installed, the agent degrades gracefully to
a built-in state-machine orchestrator that preserves the same semantics
(nodes, conditional edges, state transitions, iteration limits).

The agent is NOT a multi-agent framework. It is a single bounded agent with
an explicit tool allowlist, maximum iteration limits, JEV security gating,
and DeepSeek-primary generation with no silent Groq fallback.

LangGraph is an optional dependency. It is NOT installed in this environment.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .graph import AgentGraph, MAX_ITERATIONS, run_agent
from .state import (
    AgentState,
    EDGE_ABSTAIN,
    EDGE_ANSWER,
    EDGE_CONTINUE,
    EDGE_ERROR,
    NODE_ANSWER,
    NODE_ABSTAIN,
    NODE_ERROR,
    NODE_PLAN,
    NODE_RETRIEVE,
    NODE_VERIFY,
)
from .tools import (
    MAX_TOOL_CALLS,
    ResearchTools,
    ToolExecutionError,
    ToolNotAllowedError,
    TOOL_ALLOWLIST,
)

logger = logging.getLogger("oau_ai.agent")

# Optional LangGraph import. Degrades gracefully when not available.
try:
    from langgraph.graph import StateGraph, END  # type: ignore[import-not-found]

    _LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on environment
    StateGraph = None  # type: ignore[assignment,misc]
    END = "__end__"  # type: ignore[assignment,misc]
    _LANGGRAPH_AVAILABLE = False


def langgraph_available() -> bool:
    """Return True if LangGraph is installed and importable."""
    return _LANGGRAPH_AVAILABLE


__all__ = [
    "AgentGraph",
    "AgentState",
    "ResearchTools",
    "run_agent",
    "langgraph_available",
    "ToolNotAllowedError",
    "ToolExecutionError",
    "TOOL_ALLOWLIST",
    "MAX_TOOL_CALLS",
    "MAX_ITERATIONS",
    "NODE_PLAN",
    "NODE_RETRIEVE",
    "NODE_VERIFY",
    "NODE_ANSWER",
    "NODE_ABSTAIN",
    "NODE_ERROR",
    "EDGE_CONTINUE",
    "EDGE_ANSWER",
    "EDGE_ABSTAIN",
    "EDGE_ERROR",
]
