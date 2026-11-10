"""RAG service — grounded answer generation with DeepSeek.

Combines:
- Hybrid retrieval: Cloudflare Vectorize semantic search + PostgreSQL
  full-text search, fused with Reciprocal Rank Fusion (RRF)
- Optional cross-encoder reranking (BAAI/bge-reranker-base when available)
- Authorized retrieval boundary (Django-issued actor context)
- DeepSeek-based grounded answer generation (primary provider)
- JEV integration at decision and security points
- Citation validation against actual retrieved evidence
- Structured abstention when evidence is insufficient

Groq is never used as a fallback when DeepSeek fails.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..auth.middleware import ActorContext
from ..db.models import AIDocument, AIChunk
from ..db.session import get_session_factory as AsyncSessionLocal
from ..embeddings.service import EmbeddingService
from ..embeddings.vectorize import VectorizeService, metadata_in_filter
from ..errors import (
    GuardrailError,
    Phase3Error,
    ProviderUnavailableError,
    RetrievalError,
)
from ..llm.base import ChatMessage, ChatRequest
from ..llm.router import (
    ProviderRouter,
    TaskDesignation,
    complete_with_deepseek,
    get_router,
)
from ..memory.service import MemoryService
from ..retrieval.service import (
    AuthorizedChunk,
    RetrievedChunk,
    RetrievalService,
    rrf_fuse,
)
from ..telemetry.core import TelemetryEvent, telemetry_context
from ..jev.client import JEVClient
from ..jev.router import TypedDecisionRouter
from ..jev.schemas import TaskType

logger = logging.getLogger("oau_ai.rag")

# Citation markers are matched case-insensitively: a model that emits
# "[source 2]" must not silently escape validation.
_CITATION_RE = re.compile(r"\[source\s+(\d+)\]", re.IGNORECASE)


@dataclass
class Citation:
    """A validated citation mapping to actual retrieved evidence."""

    chunk_id: str
    document_id: str
    backend_thesis_id: str
    text_snippet: str
    page_number: Optional[int]
    section: Optional[str]
    relevance_score: float


@dataclass
class RAGResponse:
    """Structured RAG response."""

    answer: str
    citations: List[Citation]
    confidence: float
    decision_engine: str
    llm_tier: int
    trace_id: str
    request_id: str
    insufficient_evidence: bool = False
    message: Optional[str] = None
    abstention_reason: Optional[str] = None


class Reranker:
    """Cross-encoder reranker for retrieval results.

    Uses sentence-transformers CrossEncoder with the configured
    ``RERANKER_MODEL_NAME`` (default BAAI/bge-reranker-base). Gracefully
    degrades when sentence-transformers or model weights are unavailable:
    reranking is skipped and chunks are returned in their original order.
    Never silently claims reranking occurred when it did not.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> None:
        import os

        self.model_name = model_name or os.environ.get(
            "RERANKER_MODEL_NAME", "BAAI/bge-reranker-base"
        )
        self.model_version = model_version or os.environ.get(
            "RERANKER_MODEL_VERSION", "stock-v1"
        )
        self._model: Optional[object] = None
        self._available: Optional[bool] = None
        self._load_error: Optional[str] = None

    @property
    def available(self) -> bool:
        """Whether the reranker model is loaded and ready."""
        if self._available is None:
            self._load_model()
        return self._available is True

    def _load_model(self) -> None:
        """Lazily load the cross-encoder model."""
        if self._available is not None:
            return
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            self._available = True
            logger.info(
                "reranker.loaded model=%s version=%s",
                self.model_name,
                self.model_version,
            )
        except ImportError as exc:
            self._available = False
            self._load_error = (
                f"sentence-transformers not installed: {exc}. "
                "Reranking will be skipped."
            )
            logger.warning("reranker.not_available %s", self._load_error)
        except Exception as exc:  # noqa: BLE001
            self._available = False
            self._load_error = (
                f"failed to load reranker model {self.model_name}: {exc}. "
                "Reranking will be skipped."
            )
            logger.warning("reranker.load_failed %s", self._load_error)

    def rerank(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Rerank chunks by cross-encoder relevance to the query.

        Args:
            query: The user question.
            chunks: Retrieved chunks to rerank.
            top_k: Maximum number of chunks to return (None = all).

        Returns:
            Reranked list of chunks. If reranker is unavailable, returns
            chunks in their original order with a log warning.
        """
        if not chunks:
            return []

        if not self.available:
            logger.warning(
                "reranker.skip reason=%s chunk_count=%d",
                self._load_error or "reranker unavailable",
                len(chunks),
            )
            return chunks[:top_k] if top_k else chunks

        try:
            pairs = [(query, chunk.text) for chunk in chunks]
            scores = self._model.predict(pairs)  # type: ignore[union-attr]

            scored = list(zip(chunks, scores))
            scored.sort(key=lambda x: float(x[1]), reverse=True)

            reranked = [chunk for chunk, _ in scored]
            result = reranked[:top_k] if top_k else reranked

            logger.info(
                "reranker.completed chunk_count=%d returned=%d",
                len(chunks),
                len(result),
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "reranker.failed error=%s chunk_count=%d", exc, len(chunks)
            )
            return chunks[:top_k] if top_k else chunks


class RAGService:
    """Grounded RAG service with authorization, citation validation, and JEV."""

    def __init__(
        self,
        db_session=None,
        llm_router: Optional[ProviderRouter] = None,
        retrieval_service: Optional[RetrievalService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        vectorize_service: Optional[VectorizeService] = None,
        jev_client: Optional[JEVClient] = None,
        reranker: Optional[Reranker] = None,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        self.db_session = db_session
        self.llm_router = llm_router or get_router()
        self.retrieval_service = retrieval_service or RetrievalService(db_session)
        self.embedding_service = embedding_service or EmbeddingService()
        self.vectorize_service = vectorize_service or VectorizeService()
        self.jev_client = jev_client or JEVClient()
        self.reranker = reranker or Reranker()
        self.memory_service = memory_service or MemoryService(db_session=db_session)

    async def ask(
        self,
        question: str,
        actor_context: ActorContext,
        document_ids: Optional[List[str]] = None,
        top_k: int = 5,
        request_id: Optional[str] = None,
    ) -> RAGResponse:
        """Answer a question using grounded retrieval + DeepSeek generation.

        Steps:
        1. JEV classification (security/decision gate)
        2. Verify document access
        3. Hybrid retrieval (dense Vectorize + lexical PostgreSQL FTS, RRF fused)
        4. Optional cross-encoder reranking
        5. Fetch authorized chunk text + provenance from PostgreSQL
        6. DeepSeek answer generation using only retrieved evidence
        7. Citation validation against actual evidence
        8. Structured abstention if evidence is insufficient
        """
        trace_id = actor_context.trace_id or str(uuid.uuid4())
        request_id = request_id or str(uuid.uuid4())

        with telemetry_context(
            component="rag_service",
            event_type="rag_generation",
            trace_id=trace_id,
            model_provider="deepseek",
            llm_tier=1,
        ) as _:
            # Step 1: JEV classification
            jev_decision = await self._classify_with_jev(
                question, actor_context, trace_id
            )
            if jev_decision.decision.value == "block":
                return RAGResponse(
                    answer="",
                    citations=[],
                    confidence=0.0,
                    decision_engine="jev",
                    llm_tier=1,
                    trace_id=trace_id,
                    request_id=request_id,
                    insufficient_evidence=True,
                    message=f"Request blocked by JEV: {jev_decision.fallback_reason.value}",
                    abstention_reason="blocked_by_safety",
                )

            # Step 2: Verify document access
            if document_ids:
                accessible_ids = await self.retrieval_service.verify_access_before_retrieval(
                    actor_context, document_ids
                )
            else:
                accessible_ids = None

            # Step 3: Hybrid retrieval
            query_embedding = await self._embed_question(question)
            vectorize_results, dense_degraded = await self._query_vectorize(
                query_embedding, top_k, accessible_ids, actor_context
            )

            retrieved_chunks = await self.retrieval_service.hybrid_retrieve(
                actor_context=actor_context,
                query=question,
                query_vector=query_embedding,
                vectorize_results=vectorize_results,
                document_ids=accessible_ids,
                top_k=top_k,
            )

            # Step 4: Optional reranking
            if retrieved_chunks:
                retrieved_chunks = self.reranker.rerank(
                    question, retrieved_chunks, top_k=top_k
                )

            # Step 5: Convert to AuthorizedChunk for generation
            authorized_chunks = self._to_authorized_chunks(retrieved_chunks)

            # Step 5b: Retrieve relevant memories (ranked, deduplicated, budgeted)
            memory_context = ""
            relevant_memories = []
            try:
                (
                    memory_context,
                    relevant_memories,
                ) = await self.memory_service.build_memory_context(
                    user_id=actor_context.user_id,
                    query=question,
                    top_k=5,
                )
            except Exception:
                # Memory retrieval failures should not block RAG
                logger.warning("Memory retrieval failed, continuing without memory")
                memory_context, relevant_memories = "", []

            if not authorized_chunks and not relevant_memories:
                if dense_degraded:
                    message = (
                        "Semantic retrieval is unavailable and no lexical "
                        "evidence was found for this question."
                    )
                    reason = "retrieval_degraded"
                else:
                    message = "No accessible evidence found for this question."
                    reason = "no_evidence"
                return RAGResponse(
                    answer="",
                    citations=[],
                    confidence=0.0,
                    decision_engine="deepseek",
                    llm_tier=1,
                    trace_id=trace_id,
                    request_id=request_id,
                    insufficient_evidence=True,
                    message=message,
                    abstention_reason=reason,
                )

            # Step 6: DeepSeek answer generation (primary provider)
            answer_result = await self._generate_answer(
                question, authorized_chunks, trace_id, memory_context, relevant_memories
            )

            # Step 7: Citation validation against actual evidence
            validated_citations = self._validate_citations(
                answer_result["answer"],
                authorized_chunks,
                scores={
                    rc.chunk_id: (rc.fused_score or 0.0)
                    for rc in retrieved_chunks
                },
            )

            # Step 8: Confidence (deterministic, based on citation coverage)
            confidence = self._calculate_confidence(
                validated_citations, authorized_chunks
            )

            insufficient_evidence = confidence < 0.50

            return RAGResponse(
                answer=answer_result["answer"],
                citations=validated_citations,
                confidence=confidence,
                decision_engine="deepseek",
                llm_tier=1,
                trace_id=trace_id,
                request_id=request_id,
                insufficient_evidence=insufficient_evidence,
                message=(
                    "Insufficient evidence to answer with confidence."
                    if insufficient_evidence
                    else None
                ),
                abstention_reason="weak_evidence" if insufficient_evidence else None,
            )

    def _to_authorized_chunks(
        self, retrieved_chunks: List[RetrievedChunk]
    ) -> List[AuthorizedChunk]:
        """Convert RetrievedChunk list to AuthorizedChunk list."""
        return [
            AuthorizedChunk(
                chunk_id=rc.chunk_id,
                document_id=rc.document_id,
                backend_thesis_id=rc.backend_thesis_id,
                text=rc.text,
                page_number=rc.page_number,
                section=rc.section,
                chunk_index=rc.chunk_index,
                access_level=rc.access_level,
                provenance=dict(rc.provenance),
            )
            for rc in retrieved_chunks
        ]

    async def _classify_with_jev(
        self, question: str, actor_context: ActorContext, trace_id: str
    ) -> object:
        """Classify the question using JEV decision layer."""
        router = TypedDecisionRouter(
            jev_client=self.jev_client,
        )
        state = {
            "user_input": question,
            "query": question,
            "evidence": [],
            "actor_context": actor_context.to_dict(),
        }
        decision = await router.route(
            task_type=TaskType.QUERY_CLASSIFICATION,
            state=state,
            user_id=actor_context.user_id,
        )
        return decision

    async def _embed_question(self, question: str) -> List[float]:
        """Generate an embedding for the question.

        Raises:
            ConfigurationError: If the embedding service is not available
                (e.g., sentence-transformers not installed). The error
                propagates to the API layer which returns a structured
                service-unavailable response. No zero vector is ever
                sent to Cloudflare Vectorize.
        """
        result = self.embedding_service.embed_text(question)
        return result.vector

    async def _query_vectorize(
        self,
        query_vector: List[float],
        top_k: int,
        accessible_ids: Optional[List[str]],
        actor_context: ActorContext,
    ) -> tuple[List[dict], bool]:
        """Query Vectorize for nearest neighbors, then filter by access.

        Returns:
            (matches, degraded). ``degraded`` is True when semantic retrieval
            could not run at all, so the caller can distinguish "the index
            returned nothing" from "the index was never consulted" instead of
            silently presenting a lexical-only answer as a hybrid one.

        Over-fetches relative to ``top_k`` because dense candidates still have
        to survive authoritative database re-resolution; without the headroom,
        unauthorized or orphaned points would crowd out valid evidence.
        """
        if not self.vectorize_service.is_configured():
            logger.warning("Vectorize not configured; skipping semantic retrieval.")
            return [], True

        try:
            filter_metadata = {}
            if accessible_ids:
                # Filter by accessible document IDs.
                filter_metadata = metadata_in_filter("document_id", accessible_ids)

            result = self.vectorize_service.query(
                vector=query_vector,
                top_k=min(max(top_k * 4, top_k), 50),
                filter=filter_metadata,
            )

            matches = result.get("result", {}).get("matches", [])
            return matches, False
        except ProviderUnavailableError as exc:
            logger.warning("Vectorize query failed: %s", exc.message)
            return [], True

    async def _generate_answer(
        self,
        question: str,
        chunks: List[AuthorizedChunk],
        trace_id: str,
        memory_context: str = "",
        relevant_memories: Optional[List] = None,
    ) -> dict:
        """Generate a grounded answer using DeepSeek (primary provider).

        Only uses retrieved chunk text as context. Never uses Groq as fallback.
        If DeepSeek fails, returns ProviderUnavailableError — no silent switch.

        Memory context is distinguished from thesis evidence: memories are
        researcher-supplied context, not authoritative thesis evidence.
        """
        context_parts = []
        for i, chunk in enumerate(chunks):
            page_info = f" (page {chunk.page_number})" if chunk.page_number else ""
            context_parts.append(
                f"[Source {i+1}] {chunk.text}{page_info}\n"
                f"  chunk_id={chunk.chunk_id}, document_id={chunk.document_id}"
            )

        thesis_context = "\n\n".join(context_parts)

        system_prompt = (
            "You are an expert academic research assistant. "
            "Answer the user's question using the provided thesis evidence "
            "and researcher memory context. "
            "Thesis evidence (marked [Source N]) is authoritative for factual "
            "claims about theses. "
            "Researcher memory (marked [Memory: key]) is user-supplied context "
            "about research interests, objectives, and preferences — it is NOT "
            "authoritative thesis evidence and should not be cited as such. "
            "If the answer is not in the evidence, say so explicitly. "
            "Always cite specific thesis sources using [Source N] format. "
            "Do not add information not present in the evidence or memory."
        )

        user_prompt_parts = [f"Question: {question}\n"]

        if thesis_context:
            user_prompt_parts.append(
                f"Thesis Evidence:\n{thesis_context}\n"
            )

        if memory_context:
            user_prompt_parts.append(
                f"Researcher Memory Context:\n{memory_context}\n"
            )

        user_prompt_parts.append(
            "Answer the question using the thesis evidence and researcher "
            "memory above. Cite thesis claims with [Source N]. "
            "Distinguish remembered context from thesis evidence in your answer."
        )

        user_prompt = "\n\n".join(user_prompt_parts)

        # DeepSeek is the primary provider — no fallback.
        response = await asyncio.to_thread(
            complete_with_deepseek,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
            temperature=0.2,
        )

        return {
            "answer": response.content,
            "model": response.model,
            "provider": response.provider,
        }

    def _validate_citations(
        self,
        answer: str,
        chunks: List[AuthorizedChunk],
        scores: Optional[Dict[str, float]] = None,
    ) -> List[Citation]:
        """Validate that every citation in the answer maps to actual evidence.

        A marker is accepted only when all of these hold:
        1. ``[Source N]`` indexes a chunk that was actually retrieved for
           this request.
        2. The chunk ID belongs to the authorized evidence set.
        3. The sentence carrying the marker shares content words with that
           chunk — so a plausible-looking index cannot be bolted onto
           unrelated prose.

        Duplicate markers for the same chunk collapse to one citation.
        Out-of-range, malformed and unverifiable markers are dropped rather
        than reported. Passing this check means the cited source exists and
        was retrieved; it does not certify that the surrounding claim is true.
        """
        if not chunks:
            return []

        chunk_map = {c.chunk_id: c for c in chunks}
        scores = scores or {}
        validated: List[Citation] = []
        seen_chunk_ids: set[str] = set()

        for marker in _CITATION_RE.finditer(answer):
            try:
                source_idx = int(marker.group(1)) - 1
            except (TypeError, ValueError):
                continue
            if not 0 <= source_idx < len(chunks):
                continue

            chunk = chunks[source_idx]
            if chunk.chunk_id not in chunk_map:
                continue
            if chunk.chunk_id in seen_chunk_ids:
                continue

            sentence = self._sentence_around(answer, marker.start())
            if not self._text_overlaps(sentence, chunk.text):
                continue

            seen_chunk_ids.add(chunk.chunk_id)
            validated.append(
                Citation(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    backend_thesis_id=chunk.backend_thesis_id,
                    text_snippet=chunk.text[:200],
                    page_number=chunk.page_number,
                    section=chunk.section,
                    relevance_score=float(scores.get(chunk.chunk_id, 0.0)),
                )
            )

        return validated

    @staticmethod
    def _sentence_around(text: str, position: int) -> str:
        """Return the sentence-like span of ``text`` containing ``position``."""
        starts = [
            p
            for p in (
                text.rfind(". ", 0, position),
                text.rfind("\n", 0, position),
                text.rfind("? ", 0, position),
                text.rfind("! ", 0, position),
            )
            if p != -1
        ]
        ends = [
            p
            for p in (
                text.find(". ", position),
                text.find("\n", position),
                text.find("? ", position),
                text.find("! ", position),
            )
            if p != -1
        ]
        start = max(starts) + 1 if starts else 0
        end = min(ends) + 1 if ends else len(text)
        return text[start:end]

    @staticmethod
    def _text_overlaps(answer: str, chunk_text: str, min_overlap_words: int = 1) -> bool:
        """Check whether the answer text shares meaningful words with the chunk.

        Used as an anti-fabrication check for citations: if the model cites
        a source but none of its key terms appear in that source's text, the
        citation is likely fabricated.

        Args:
            answer: The generated answer text.
            chunk_text: The source chunk text.
            min_overlap_words: Minimum number of shared content words required.

        Returns:
            True if there is meaningful word overlap.
        """
        # Normalize: lowercase, strip punctuation, split into words.
        answer_words = set(
            w.strip(".,!?;:\"'()[]{}").lower()
            for w in answer.split()
            if len(w.strip(".,!?;:\"'()[]{}")) > 3
        )
        chunk_words = set(
            w.strip(".,!?;:\"'()[]{}").lower()
            for w in chunk_text.split()
            if len(w.strip(".,!?;:\"'()[]{}")) > 3
        )

        overlap = answer_words & chunk_words
        return len(overlap) >= min_overlap_words

    def _calculate_confidence(
        self, citations: List[Citation], chunks: List[AuthorizedChunk]
    ) -> float:
        """Calculate deterministic confidence based on citation coverage.

        Not model self-reported confidence. Based on:
        - Fraction of retrieved chunks that were cited
        - Number of validated citations
        """
        if not chunks:
            return 0.0

        citation_coverage = len(citations) / len(chunks)
        # Cap at 1.0, scale so that having at least 2 citations on 3 chunks
        # gives reasonable confidence.
        confidence = min(citation_coverage * 0.9 + 0.1, 1.0)
        return round(confidence, 3)
