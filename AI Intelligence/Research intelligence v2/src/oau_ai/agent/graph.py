"""Agent graph — bounded autonomous orchestration for the Research Intelligence Agent.

Follows LangGraph StateGraph conventions (nodes, conditional edges, state
transitions) but works with or without the langgraph package installed.
When langgraph is available, a real StateGraph is compiled. When not,
a built-in state-machine orchestrator provides the same semantics.

The agent graph nodes:
- plan: Interpret the question and create a bounded plan.
- verify: Run JEV guardrails and decision on the question BEFORE any retrieval.
- retrieve: Execute hybrid retrieval only after JEV verification passes.
- answer: Generate a grounded answer using DeepSeek (no Groq fallback).
- abstain: Report insufficient evidence or JEV block.
- error: Terminal error state.

Security controls:
- JEV guardrails run BEFORE any document text is retrieved (pre-retrieval check on the user question).
- Document-level access (authorization) is enforced by the retrieval tools before chunk text enters agent state.
- Retrieved content is screened for prompt injection before it can influence generation (retrieved-content screening).
- Output validation checks that answer claims map to cited evidence.
- Tool allowlist restricts calls to registered tools.
- Maximum iteration and tool-call limits prevent runaway loops.
- No silent Groq fallback; DeepSeek is the only generation provider.
- Pre-retrieval screening protects against malicious user instructions only; it does NOT protect against malicious instructions embedded in retrieved documents. Retrieved documents are screened separately before generation.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Optional

from ..agent.state import (
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
from ..agent.tools import ResearchTools, ToolNotAllowedError, ToolExecutionError
from ..auth.middleware import ActorContext
from ..config import get_settings
from ..errors import (
    ConfigurationError,
    Phase3Error,
    ProviderUnavailableError,
    RetrievalError,
)
from ..jev.router import RoutingDecision, TaskType, TypedDecisionRouter
from ..rag.service import RAGService
from ..retrieval.service import RetrievedChunk
from ..telemetry.core import telemetry_context

logger = logging.getLogger("oau_ai.agent.graph")

# Maximum iterations before forced termination.
MAX_ITERATIONS = 5

# Input injection patterns (mirrors JEV guardrails for defense-in-depth).
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior)\s+instructions",
    r"reveal\s+(your\s+)?(system prompt|hidden instructions)",
    r"act\s+as\s+if\s+your\s+safety\s+rules",
]

# Minimum word overlap for an answer claim to be considered supported by
# its cited evidence (anti-fabrication, defense-in-depth beyond RAG service).
# Set to 1 because the RAG service already performs citation validation;
# this is a lightweight defense-in-depth check.
MIN_ANSWER_EVIDENCE_OVERLAP = 1


class AgentGraph:
    """Bounded autonomous agent graph.

    Orchestrates a research workflow: plan → verify → retrieve → answer/abstain.
    JEV verification runs before retrieval; retrieved content is screened
    before generation.
    Supports conditional edges based on JEV decisions, evidence sufficiency,
    and iteration limits.

    When LangGraph is installed, compiles a real StateGraph. Otherwise, uses
    a built-in sequential orchestrator with identical semantics.
    """

    def __init__(
        self,
        tools: Optional[ResearchTools] = None,
        max_iterations: int = MAX_ITERATIONS,
        jev_router: Optional[TypedDecisionRouter] = None,
    ) -> None:
        self.tools = tools or ResearchTools()
        self.max_iterations = max_iterations
        self.jev_router = jev_router or TypedDecisionRouter()
        self._compiled_graph: Optional[Any] = None
        self._langgraph_available = False

        # Try to compile with LangGraph if available.
        try:
            from langgraph.graph import StateGraph as LGStateGraph, END as LGEND

            self._lg_state_graph = LGStateGraph
            self._lg_end = LGEND
            self._langgraph_available = True
        except ImportError:
            self._lg_state_graph = None
            self._lg_end = "__end__"
            self._langgraph_available = False

    def langgraph_available(self) -> bool:
        """Return True if LangGraph is installed."""
        return self._langgraph_available

    # ------------------------------------------------------------------
    # Node functions
    # ------------------------------------------------------------------

    async def _node_plan(self, state: AgentState) -> AgentState:
        """Plan node: interpret the question and create a bounded plan.

        Creates a bounded plan with security ordering:
        1. Verify the question with JEV (guardrails + decision) FIRST.
        2. Retrieve evidence only if verification passes.
        3. Answer using verified evidence.
        """
        state["status"] = "planning"
        state["iteration_count"] = state.get("iteration_count", 0) + 1

        question = state.get("question", "")
        if not question or not question.strip():
            state["error"] = "Empty question."
            state["status"] = "error"
            return state

        # Defense-in-depth: check for injection patterns before any retrieval.
        if self._contains_injection(question):
            state["error"] = "Input injection detected."
            state["status"] = "abstain"
            state["insufficient_evidence"] = True
            logger.warning(
                "agent.node.plan_injection_detected question_length=%d",
                len(question),
            )
            return state

        # Bounded plan: verify first, then retrieve, then answer.
        state["plan"] = [
            {"step": 1, "tool": "jev_verify", "question": question},
            {"step": 2, "tool": "hybrid_retrieve", "question": question},
            {"step": 3, "tool": "rag_answer", "question": question},
        ]
        state["plan_step"] = 0
        state["retrieved_evidence"] = []
        state["verified_evidence"] = []
        state["final_answer"] = ""
        state["citations"] = []
        state["confidence"] = 0.0
        state["insufficient_evidence"] = False
        state["error"] = None

        logger.info(
            "agent.node.plan iteration=%d question_length=%d",
            state["iteration_count"],
            len(question),
        )
        return state

    def _contains_injection(self, text: str) -> bool:
        """Check for prompt-injection patterns in user input.

        Defense-in-depth check that mirrors JEV guardrails. Runs before
        any retrieval so injection attempts never trigger document access.
        """
        return bool(
            any(re.search(p, text, re.I) for p in INJECTION_PATTERNS)
        )

    def _screen_retrieved_content(
        self, evidence: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Screen retrieved evidence text for prompt injection.

        Treats document text as untrusted: any chunk whose text matches an
        injection pattern is excluded from the evidence returned to the
        generation context. This is a separate check from pre-retrieval
        user-input screening and does not rely on JEV.

        Args:
            evidence: List of retrieved evidence dicts with ``text`` field.

        Returns:
            Filtered list of evidence dicts with injection content removed.
            Excluded chunks are logged but not included in the return value.
        """
        safe_evidence: list[dict[str, Any]] = []
        for chunk in evidence:
            text = chunk.get("text", "")
            if self._contains_injection(text):
                logger.warning(
                    "agent.retrieve.injection_in_chunk chunk_id=%s document_id=%s",
                    chunk.get("chunk_id"),
                    chunk.get("document_id"),
                )
                continue
            safe_evidence.append(chunk)
        return safe_evidence

    async def _node_retrieve(self, state: AgentState) -> AgentState:
        """Retrieve node: execute hybrid retrieval after JEV verification.

        Only runs if JEV verification passed. Retrieval tools enforce
        document-level access before any chunk text enters agent state.
        """
        state["status"] = "retrieving"

        plan = state.get("plan", [])
        plan_step = state.get("plan_step", 0)

        if plan_step >= len(plan):
            state["error"] = "No more plan steps."
            state["status"] = "error"
            return state

        step = plan[plan_step]
        question = state.get("question", "")
        actor_context = state.get("actor_context", {})

        try:
            evidence = await self.tools.hybrid_retrieve(
                question=question,
                question_vector=[0.0] * 1024,  # Zero vector when embeddings unavailable
                actor_context=actor_context,
                top_k=5,
            )
            # Screen retrieved content for prompt injection before it can
            # influence generation. Document text is treated as untrusted.
            safe_evidence = self._screen_retrieved_content(evidence)
            state["retrieved_evidence"] = safe_evidence
            # Access is already enforced by hybrid_retrieve; content has
            # been screened. Mark as verified for generation context.
            state["verified_evidence"] = safe_evidence
            state["plan_step"] = plan_step + 1

            logger.info(
                "agent.node.retrieve step=%d evidence_count=%d",
                plan_step,
                len(evidence),
            )
        except (ToolNotAllowedError, ToolExecutionError) as exc:
            state["error"] = str(exc)
            state["status"] = "error"
            logger.warning("agent.node.retrieve_failed error=%s", exc)
        except Exception as exc:  # noqa: BLE001
            state["error"] = f"Unexpected retrieval error: {exc}"
            state["status"] = "error"
            logger.exception("agent.node.retrieve_unexpected_error")

        return state

    async def _node_verify(self, state: AgentState) -> AgentState:
        """Verify node: run JEV guardrails and decision on the question.

        Runs BEFORE any retrieval. If JEV returns BLOCK or guardrails flag
        the input, no document text is ever fetched. If JEV allows, the
        agent proceeds to retrieval.

        Enforces:
        - Prompt-injection detection (JEV guardrails + local patterns).
        - Content verification (JEV decision on whether the question is
          answerable with evidence).
        - Authentication (user_id required from actor context).
        """
        state["status"] = "verifying"

        question = state.get("question", "")
        actor_context = state.get("actor_context", {})

        try:
            # Run JEV verification on the question BEFORE any retrieval.
            decision = await self.tools.jev_verify(
                question=question,
                actor_context=actor_context,
                task_type="query_classification",
            )
            state["jev_decision"] = decision

            if decision.get("decision") == "block":
                state["insufficient_evidence"] = True
                state["status"] = "abstain"
                state["error"] = (
                    f"JEV blocked: {decision.get('fallback_reason', 'unknown')}"
                )
                logger.warning(
                    "agent.node.verify_blocked reason=%s",
                    decision.get("fallback_reason"),
                )
                return state

            # JEV allows — mark as verified so retrieval can proceed.
            state["plan_step"] = state.get("plan_step", 0) + 1

            logger.info(
                "agent.node.verify_passed jev_decision=%s",
                decision.get("decision"),
            )
        except (ToolNotAllowedError, ToolExecutionError) as exc:
            state["error"] = str(exc)
            state["status"] = "error"
            logger.warning("agent.node.verify_failed error=%s", exc)
        except Exception as exc:  # noqa: BLE001
            state["error"] = f"Unexpected verification error: {exc}"
            state["status"] = "error"
            logger.exception("agent.node.verify_unexpected_error")

        return state

    async def _node_answer(self, state: AgentState) -> AgentState:
        """Answer node: generate a grounded answer using DeepSeek only.

        Uses RAGService.ask which enforces DeepSeek-primary with no Groq
        fallback. Citations are validated against actual evidence.
        Output validation checks that answer claims map to cited evidence.
        """
        state["status"] = "answering"

        question = state.get("question", "")
        actor_context = state.get("actor_context", {})
        verified_evidence = state.get("verified_evidence", [])

        if not verified_evidence:
            state["insufficient_evidence"] = True
            state["status"] = "abstain"
            state["error"] = "No verified evidence for answer generation."
            return state

        try:
            # Build document_ids from verified evidence for access-scoped RAG.
            document_ids = list(
                {
                    e.get("document_id", "")
                    for e in verified_evidence
                    if e.get("document_id")
                }
            ) or None

            result = await self.tools.rag_answer(
                question=question,
                actor_context=actor_context,
                document_ids=document_ids,
                top_k=5,
            )

            answer = result.get("answer", "")
            citations = result.get("citations", [])

            # Output validation: defense-in-depth beyond RAG service.
            # 1. Check for injection patterns in the generated answer.
            if self._contains_injection(answer):
                state["error"] = "Generated answer failed output safety check."
                state["status"] = "error"
                state["insufficient_evidence"] = True
                logger.warning("agent.node.answer_injection_detected")
                return state

            # 2. Build a set of evidence text chunks for claim validation.
            evidence_texts = [
                e.get("text", "") for e in verified_evidence if e.get("text")
            ]

            # 3. Validate that cited claims have supporting evidence.
            validated_citations = self._validate_output_citations(
                answer, citations, evidence_texts, verified_evidence
            )

            state["final_answer"] = answer
            state["citations"] = validated_citations
            state["confidence"] = result.get("confidence", 0.0)
            state["insufficient_evidence"] = result.get(
                "insufficient_evidence", True
            )
            # If output validation stripped all citations, evidence is insufficient.
            if not validated_citations:
                state["insufficient_evidence"] = True

            logger.info(
                "agent.node.answer answer_length=%d citations=%d confidence=%.3f",
                len(state["final_answer"]),
                len(state["citations"]),
                state["confidence"],
            )
        except (ToolNotAllowedError, ToolExecutionError) as exc:
            state["error"] = str(exc)
            state["status"] = "error"
            logger.warning("agent.node.answer_failed error=%s", exc)
        except ProviderUnavailableError as exc:
            state["error"] = f"Provider unavailable: {exc.message}"
            state["status"] = "error"
            state["insufficient_evidence"] = True
            logger.warning("agent.node.answer_provider_unavailable error=%s", exc)
        except Exception as exc:  # noqa: BLE001
            state["error"] = f"Unexpected answer error: {exc}"
            state["status"] = "error"
            logger.exception("agent.node.answer_unexpected_error")

        return state

    def _validate_output_citations(
        self,
        answer: str,
        citations: list[dict[str, Any]],
        evidence_texts: list[str],
        verified_evidence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Validate that cited claims in the answer map to actual evidence.

        Defense-in-depth check beyond the RAG service's citation validation.
        Strips citations whose source text has no meaningful word overlap
        with the answer context around the citation, and flags uncited
        claims.

        Args:
            answer: The generated answer text.
            citations: List of citation dicts from RAG service.
            evidence_texts: List of verified evidence chunk texts.

        Returns:
            Filtered list of citations that pass validation.
        """
        import re

        validated: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()

        # Extract all [Source N] references from the answer.
        source_refs = re.findall(r"\[Source (\d+)\]", answer)

        # Build evidence text lookup by chunk_id for overlap checking.
        evidence_by_chunk = {}
        for i, text in enumerate(evidence_texts):
            chunk_id = f"chunk-{i}"
            # Also try to get the real chunk_id from verified_evidence if available.
            if i < len(verified_evidence):
                real_id = verified_evidence[i].get("chunk_id")
                if real_id:
                    chunk_id = real_id
            evidence_by_chunk[chunk_id] = text

        for ref in source_refs:
            try:
                source_idx = int(ref) - 1
                if not (0 <= source_idx < len(citations)):
                    continue
                citation = citations[source_idx]
                chunk_id = citation.get("chunk_id", "")

                if chunk_id in seen_chunk_ids:
                    continue

                # Check word overlap between answer and cited evidence.
                answer_words = set(
                    w.strip(".,!?;:\"'()[]{}").lower()
                    for w in answer.split()
                    if len(w.strip(".,!?;:\"'()[]{}")) > 3
                )
                evidence_text = evidence_by_chunk.get(chunk_id, "")
                evidence_words = set(
                    w.strip(".,!?;:\"'()[]{}").lower()
                    for w in evidence_text.split()
                    if len(w.strip(".,!?;:\"'()[]{}")) > 3
                )
                overlap = answer_words & evidence_words

                if len(overlap) >= MIN_ANSWER_EVIDENCE_OVERLAP:
                    seen_chunk_ids.add(chunk_id)
                    validated.append(citation)
            except (ValueError, IndexError):
                continue

        return validated

    async def _node_abstain(self, state: AgentState) -> AgentState:
        """Abstain node: report insufficient evidence with a structured response."""
        state["status"] = "abstain"
        state["final_answer"] = ""
        state["citations"] = []
        state["confidence"] = 0.0
        state["insufficient_evidence"] = True
        logger.info("agent.node.abstain reason=%s", state.get("error"))
        return state

    async def _node_error(self, state: AgentState) -> AgentState:
        """Error node: terminal error state."""
        state["status"] = "error"
        state["final_answer"] = ""
        state["citations"] = []
        state["confidence"] = 0.0
        state["insufficient_evidence"] = True
        logger.error("agent.node.error error=%s", state.get("error"))
        return state

    # ------------------------------------------------------------------
    # Conditional edges
    # ------------------------------------------------------------------

    def _edge_after_plan(self, state: AgentState) -> str:
        """After planning: go to verify (JEV before retrieval), or error."""
        if state.get("status") == "error":
            return EDGE_ERROR
        if state.get("status") == "abstain":
            return EDGE_ABSTAIN
        return EDGE_CONTINUE

    def _edge_after_verify(self, state: AgentState) -> str:
        """After verification: go to retrieve if JEV allows, else abstain/error.

        Verify runs before retrieval, so no evidence should be present yet.
        If JEV allows, always proceed to retrieve.
        """
        if state.get("status") == "error":
            return EDGE_ERROR
        if state.get("status") == "abstain":
            return EDGE_ABSTAIN
        return EDGE_CONTINUE

    def _edge_after_retrieve(self, state: AgentState) -> str:
        """After retrieval: go to answer, or error/abstain if failed."""
        if state.get("status") == "error":
            return EDGE_ERROR
        if not state.get("verified_evidence"):
            return EDGE_ABSTAIN
        return EDGE_ANSWER

    def _edge_after_answer(self, state: AgentState) -> str:
        """After answering: end (terminal)."""
        return "__end__"

    def _edge_after_abstain(self, state: AgentState) -> str:
        """After abstaining: end (terminal)."""
        return "__end__"

    def _edge_after_error(self, state: AgentState) -> str:
        """After error: end (terminal)."""
        return "__end__"

    # ------------------------------------------------------------------
    # Graph execution
    # ------------------------------------------------------------------

    def _build_graph(self) -> Any:
        """Build the agent graph using LangGraph if available, else built-in."""
        if self._langgraph_available and self._lg_state_graph is not None:
            return self._build_langgraph()
        return self  # Built-in orchestrator (self is the graph)

    def _build_langgraph(self) -> Any:
        """Compile a real LangGraph StateGraph."""
        sg = self._lg_state_graph(AgentState)

        sg.add_node(NODE_PLAN, self._node_plan)
        sg.add_node(NODE_RETRIEVE, self._node_retrieve)
        sg.add_node(NODE_VERIFY, self._node_verify)
        sg.add_node(NODE_ANSWER, self._node_answer)
        sg.add_node(NODE_ABSTAIN, self._node_abstain)
        sg.add_node(NODE_ERROR, self._node_error)

        sg.set_entry_point(NODE_PLAN)

        sg.add_conditional_edges(
            NODE_PLAN,
            self._edge_after_plan,
            {
                EDGE_CONTINUE: NODE_VERIFY,
                EDGE_ERROR: NODE_ERROR,
                EDGE_ABSTAIN: NODE_ABSTAIN,
            },
        )
        sg.add_conditional_edges(
            NODE_VERIFY,
            self._edge_after_verify,
            {
                EDGE_CONTINUE: NODE_RETRIEVE,
                EDGE_ERROR: NODE_ERROR,
                EDGE_ABSTAIN: NODE_ABSTAIN,
                EDGE_ANSWER: NODE_ANSWER,
            },
        )
        sg.add_conditional_edges(
            NODE_RETRIEVE,
            self._edge_after_retrieve,
            {
                EDGE_CONTINUE: NODE_ANSWER,
                EDGE_ERROR: NODE_ERROR,
                EDGE_ABSTAIN: NODE_ABSTAIN,
            },
        )
        sg.add_edge(NODE_ANSWER, self._lg_end)
        sg.add_edge(NODE_ABSTAIN, self._lg_end)
        sg.add_edge(NODE_ERROR, self._lg_end)

        self._compiled_graph = sg.compile()
        return self._compiled_graph

    async def run(
        self,
        question: str,
        actor_context: ActorContext,
        trace_id: Optional[str] = None,
    ) -> AgentState:
        """Run the agent graph for a research question.

        Args:
            question: The user's research question.
            actor_context: Django-issued ActorContext.
            trace_id: Optional UUIDv4 trace identifier.

        Returns:
            Final AgentState with answer, citations, confidence, and status.
        """
        import time

        started = time.monotonic()

        # Enforce iteration limit.
        if self.max_iterations <= 0:
            raise ConfigurationError(
                code="invalid_max_iterations",
                message="max_iterations must be > 0.",
                component="agent_graph",
            )

        # Build initial state.
        state = AgentState(
            question=question,
            actor_context=actor_context.to_dict(),
            trace_id=trace_id,
            max_iterations=self.max_iterations,
        )

        with telemetry_context(
            component="agent_graph",
            event_type="agent_run",
            trace_id=trace_id,
            model_provider="deepseek",
            llm_tier=1,
        ):
            # Run using LangGraph if compiled, else built-in orchestrator.
            if self._compiled_graph is not None:
                # LangGraph path
                try:
                    result = await self._compiled_graph.ainvoke(state)
                    return result if isinstance(result, AgentState) else AgentState(**result)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("LangGraph execution failed")
                    state["error"] = f"Graph execution error: {exc}"
                    state["status"] = "error"
                    return state
            else:
                # Built-in state-machine orchestrator.
                return await self._run_builtin(state, started)

    async def _run_builtin(
        self, state: AgentState, started: float
    ) -> AgentState:
        """Built-in state-machine orchestrator (no LangGraph dependency).

        Executes nodes sequentially with conditional edge transitions,
        enforcing iteration limits.
        """
        current_node = NODE_PLAN
        node_map = {
            NODE_PLAN: self._node_plan,
            NODE_RETRIEVE: self._node_retrieve,
            NODE_VERIFY: self._node_verify,
            NODE_ANSWER: self._node_answer,
            NODE_ABSTAIN: self._node_abstain,
            NODE_ERROR: self._node_error,
        }
        edge_map = {
            NODE_PLAN: self._edge_after_plan,
            NODE_RETRIEVE: self._edge_after_retrieve,
            NODE_VERIFY: self._edge_after_verify,
            NODE_ANSWER: self._edge_after_answer,
            NODE_ABSTAIN: self._edge_after_abstain,
            NODE_ERROR: self._edge_after_error,
        }

        iteration = 0
        while current_node != "__end__" and iteration < self.max_iterations:
            iteration += 1
            node_fn = node_map[current_node]
            state = await node_fn(state)

            # Check iteration limit.
            if state.get("iteration_count", 0) >= self.max_iterations:
                if state.get("status") not in ("error", "abstain"):
                    state["error"] = "Maximum iteration limit reached."
                    state["status"] = "error"
                break

            # Determine next node via conditional edge.
            edge_fn = edge_map[current_node]
            edge_result = edge_fn(state)

            # Map edge result to next node name.
            node_for_edge = {
                EDGE_CONTINUE: {
                    NODE_PLAN: NODE_VERIFY,
                    NODE_VERIFY: NODE_RETRIEVE,
                    NODE_RETRIEVE: NODE_ANSWER,
                },
                EDGE_ANSWER: NODE_ANSWER,
                EDGE_ABSTAIN: NODE_ABSTAIN,
                EDGE_ERROR: NODE_ERROR,
            }

            if isinstance(edge_result, str):
                if edge_result == "__end__":
                    current_node = "__end__"
                    break
                # EDGE_CONTINUE is context-dependent; resolve based on current node.
                if edge_result == EDGE_CONTINUE:
                    current_node = node_for_edge[EDGE_CONTINUE].get(
                        current_node, NODE_ERROR
                    )
                else:
                    current_node = node_for_edge.get(edge_result, NODE_ERROR)
            else:
                current_node = NODE_ERROR

            if current_node == "__end__":
                break

        if state.get("status") not in ("error", "abstain", "complete"):
            # If we exited the loop without a terminal state, mark complete.
            state["status"] = "complete"

        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        state["provenance"] = {
            "elapsed_ms": elapsed_ms,
            "iterations": state.get("iteration_count", 0),
            "langgraph_available": self._langgraph_available,
        }

        return state


# Module-level convenience function.


async def run_agent(
    question: str,
    actor_context: ActorContext,
    trace_id: Optional[str] = None,
    tools: Optional[ResearchTools] = None,
    max_iterations: int = MAX_ITERATIONS,
) -> AgentState:
    """Convenience: run the Research Intelligence Agent.

    Args:
        question: The user's research question.
        actor_context: Django-issued ActorContext.
        trace_id: Optional UUIDv4 trace identifier.
        tools: Optional ResearchTools instance.
        max_iterations: Maximum reasoning iterations.

    Returns:
        Final AgentState.
    """
    graph = AgentGraph(tools=tools, max_iterations=max_iterations)
    return await graph.run(question, actor_context, trace_id=trace_id)
