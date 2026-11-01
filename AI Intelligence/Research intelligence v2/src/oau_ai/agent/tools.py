"""Research tools for the Research Intelligence Agent.

Wraps existing V2 capabilities as explicitly registered, access-controlled
tools. The agent may only call tools in the allowlist. Each tool validates
its inputs and enforces document-level access before returning any text.

Available tools:
- hybrid_retrieve: Dense (Vectorize) + lexical (PostgreSQL FTS) retrieval
  with RRF fusion and access enforcement.
- rag_answer: Grounded RAG question answering via RAGService.
- jev_verify: JEV decision and verification for a claim or question.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..auth.middleware import ActorContext
from ..config import get_settings, get_vectorize_config
from ..errors import (
    ConfigurationError,
    Phase3Error,
    ProviderUnavailableError,
    RetrievalError,
)
from ..rag.service import RAGService
from ..retrieval.service import RetrievalService, RetrievedChunk

logger = logging.getLogger("oau_ai.agent.tools")

# Explicit tool allowlist. The agent may only call tools in this set.
TOOL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "hybrid_retrieve",
        "rag_answer",
        "jev_verify",
    }
)

# Maximum number of tool calls per agent run.
MAX_TOOL_CALLS = 10


class ToolNotAllowedError(Phase3Error):
    """Raised when the agent attempts to call a tool not in the allowlist."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(
            code="tool_not_allowed",
            message=f"Tool '{tool_name}' is not in the agent tool allowlist.",
            component="agent_tools",
            retryable=False,
        )


class ToolExecutionError(Phase3Error):
    """Raised when a tool execution fails."""

    def __init__(self, tool_name: str, message: str, retryable: bool = False) -> None:
        super().__init__(
            code="tool_execution_error",
            message=f"Tool '{tool_name}' failed: {message}",
            component="agent_tools",
            retryable=retryable,
        )


def _actor_context_from_state(
    actor_context: dict[str, Any],
) -> ActorContext:
    """Build an ActorContext from a dict (e.g., from agent state)."""
    return ActorContext(
        user_id=actor_context.get("user_id", ""),
        roles=actor_context.get("roles", ["student"]),
        department=actor_context.get("department", ""),
        trace_id=actor_context.get("trace_id"),
    )


class ResearchTools:
    """Bounded set of research tools for the agent.

    Wraps existing V2 services. All tools enforce document-level access
    before returning any text. Tools are stateless and safe to call
    concurrently.
    """

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        rag_service: Optional[RAGService] = None,
    ) -> None:
        self.retrieval_service = retrieval_service or RetrievalService()
        self.rag_service = rag_service or RAGService()
        self._call_count = 0

    def is_allowed(self, tool_name: str) -> bool:
        """Return True if the tool is in the allowlist."""
        return tool_name in TOOL_ALLOWLIST

    def can_call_more(self) -> bool:
        """Return True if the agent has not exceeded the tool call limit."""
        return self._call_count < MAX_TOOL_CALLS

    def record_call(self) -> None:
        """Record a tool call for limit tracking."""
        self._call_count += 1

    async def hybrid_retrieve(
        self,
        question: str,
        question_vector: list[float],
        actor_context: dict[str, Any],
        document_ids: Optional[list[str]] = None,
        top_k: int = 5,
        vectorize_results: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Hybrid retrieval: dense + lexical search with RRF fusion.

        Enforces document-level access before returning any chunk text.

        Args:
            question: The research question.
            question_vector: Embedding vector for dense search.
            actor_context: Django-issued actor context.
            document_ids: Optional list of internal document IDs to restrict.
            top_k: Maximum results.
            vectorize_results: Optional pre-fetched Vectorize matches.

        Returns:
            List of retrieved evidence dicts with provenance.
        """
        if not self.is_allowed("hybrid_retrieve"):
            raise ToolNotAllowedError("hybrid_retrieve")
        if not self.can_call_more():
            raise ToolExecutionError(
                "hybrid_retrieve",
                "Maximum tool call limit reached.",
                retryable=False,
            )

        self.record_call()
        logger.info(
            "agent.tool.hybrid_retrieve question_length=%d top_k=%d",
            len(question),
            top_k,
        )

        try:
            actor = _actor_context_from_state(actor_context)

            # If no Vectorize results provided, query Vectorize first.
            if vectorize_results is None:
                from ..embeddings.vectorize import VectorizeService

                vs = VectorizeService()
                if vs.is_configured():
                    from ..embeddings.service import EmbeddingService

                    es = EmbeddingService()
                    embed_result = es.embed_text(question)
                    vectorize_results = vs.query(
                        vector=embed_result.vector,
                        top_k=top_k,
                        filter=None,
                    ).get("result", {}).get("matches", [])
                else:
                    logger.warning("Vectorize not configured; skipping dense retrieval.")
                    vectorize_results = []

            retrieved = await self.retrieval_service.hybrid_retrieve(
                actor_context=actor,
                query=question,
                query_vector=question_vector,
                vectorize_results=vectorize_results or [],
                document_ids=document_ids,
                top_k=top_k,
            )

            return [
                {
                    "chunk_id": rc.chunk_id,
                    "document_id": rc.document_id,
                    "backend_thesis_id": rc.backend_thesis_id,
                    "text": rc.text,
                    "page_number": rc.page_number,
                    "chunk_index": rc.chunk_index,
                    "access_level": rc.access_level,
                    "dense_score": rc.dense_score,
                    "lexical_score": rc.lexical_score,
                    "fused_score": rc.fused_score,
                    "retrieval_source": rc.retrieval_source,
                    "provenance": dict(rc.provenance),
                }
                for rc in retrieved
            ]
        except ToolNotAllowedError:
            raise
        except Phase3Error as exc:
            raise ToolExecutionError(
                "hybrid_retrieve",
                exc.message,
                retryable=exc.retryable,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("hybrid_retrieve failed")
            raise ToolExecutionError(
                "hybrid_retrieve",
                str(exc),
                retryable=True,
            ) from exc

    async def rag_answer(
        self,
        question: str,
        actor_context: dict[str, Any],
        document_ids: Optional[list[str]] = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Grounded RAG question answering.

        Uses RAGService to generate a DeepSeek-grounded answer with citation
        validation and structured abstention.

        Args:
            question: The research question.
            actor_context: Django-issued actor context.
            document_ids: Optional list of internal document IDs.
            top_k: Maximum retrieved chunks.

        Returns:
            Dict with answer, citations, confidence, and sufficiency flag.
        """
        if not self.is_allowed("rag_answer"):
            raise ToolNotAllowedError("rag_answer")
        if not self.can_call_more():
            raise ToolExecutionError(
                "rag_answer",
                "Maximum tool call limit reached.",
                retryable=False,
            )

        self.record_call()
        logger.info("agent.tool.rag_answer question_length=%d", len(question))

        try:
            actor = _actor_context_from_state(actor_context)
            result = await self.rag_service.ask(
                question=question,
                actor_context=actor,
                document_ids=document_ids,
                top_k=top_k,
            )

            return {
                "answer": result.answer,
                "citations": [
                    {
                        "chunk_id": c.chunk_id,
                        "document_id": c.document_id,
                        "backend_thesis_id": c.backend_thesis_id,
                        "text_snippet": c.text_snippet,
                        "page_number": c.page_number,
                        "section": c.section,
                        "relevance_score": c.relevance_score,
                    }
                    for c in result.citations
                ],
                "confidence": result.confidence,
                "decision_engine": result.decision_engine,
                "llm_tier": result.llm_tier,
                "trace_id": result.trace_id,
                "request_id": result.request_id,
                "insufficient_evidence": result.insufficient_evidence,
                "message": result.message,
            }
        except ToolNotAllowedError:
            raise
        except ProviderUnavailableError as exc:
            raise ToolExecutionError(
                "rag_answer",
                exc.message,
                retryable=exc.retryable,
            ) from exc
        except Phase3Error as exc:
            raise ToolExecutionError(
                "rag_answer",
                exc.message,
                retryable=exc.retryable,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("rag_answer failed")
            raise ToolExecutionError(
                "rag_answer",
                str(exc),
                retryable=True,
            ) from exc

    async def jev_verify(
        self,
        question: str,
        actor_context: dict[str, Any],
        task_type: str = "query_classification",
    ) -> dict[str, Any]:
        """JEV decision and verification for a research question.

        Runs the JEV decision layer (guardrails → JEV → local → LLM fallback)
        to determine whether the question is allowed and what confidence to
        assign. Fail-closed: ALLOW from LLM fallback is not trusted.

        Args:
            question: The question to verify.
            actor_context: Django-issued actor context.
            task_type: JEV task type.

        Returns:
            Dict with decision, confidence, engine, and provenance.
        """
        if not self.is_allowed("jev_verify"):
            raise ToolNotAllowedError("jev_verify")
        if not self.can_call_more():
            raise ToolExecutionError(
                "jev_verify",
                "Maximum tool call limit reached.",
                retryable=False,
            )

        self.record_call()
        logger.info("agent.tool.jev_verify question_length=%d", len(question))

        try:
            actor = _actor_context_from_state(actor_context)
            from ..jev.router import TaskType, TypedDecisionRouter

            router = TypedDecisionRouter()
            state = {
                "user_input": question,
                "query": question,
                "evidence": [],
                "actor_context": actor.to_dict(),
            }
            decision = await router.route(
                task_type=task_type,
                state=state,
                user_id=actor.user_id,
            )

            return {
                "decision": decision.decision.value,
                "confidence": decision.confidence,
                "engine_used": decision.engine_used,
                "fallback_reason": decision.fallback_reason.value,
                "guardrail_outcome": decision.guardrail_outcome.value,
                "provenance": decision.provenance,
                "timestamp": decision.timestamp,
            }
        except ToolNotAllowedError:
            raise
        except Phase3Error as exc:
            raise ToolExecutionError(
                "jev_verify",
                exc.message,
                retryable=exc.retryable,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("jev_verify failed")
            raise ToolExecutionError(
                "jev_verify",
                str(exc),
                retryable=True,
            ) from exc
