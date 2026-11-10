"""Research Gap Detection service.

Analyzes retrieved thesis content to identify potential research gaps
across individual theses and related studies. Classifies gaps into:
- Topic gaps
- Methodological gaps
- Population/context gaps
- Evidence gaps
- Contradictory findings

Distinguishes explicit author-stated limitations from system-inferred gaps.
All gaps must be backed by actual retrieved evidence — no fabricated
citations, findings, or gaps. Returns insufficient evidence when the
available documents cannot support a conclusion.

Reuses the existing retrieval, embeddings, DeepSeek generation, and JEV
guardrails infrastructure — no new vector database or duplicate pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..auth.middleware import ActorContext
from ..db.models import AIDocument, AIChunk
from ..db.session import get_session_factory as AsyncSessionLocal
from ..embeddings.service import EmbeddingService
from ..embeddings.vectorize import VectorizeService, metadata_in_filter
from ..errors import (
    ConfigurationError,
    GuardrailError,
    Phase3Error,
    ProviderUnavailableError,
    RetrievalError,
)
from ..jev.client import JEVClient
from ..jev.router import TypedDecisionRouter
from ..jev.schemas import TaskType
from ..llm.base import ChatMessage, ChatRequest
from ..llm.router import (
    ProviderRouter,
    TaskDesignation,
    complete_with_deepseek,
    get_router,
)
from ..retrieval.service import (
    AuthorizedChunk,
    RetrievedChunk,
    RetrievalService,
    rrf_fuse,
)
from ..telemetry.core import TelemetryEvent, telemetry_context

logger = logging.getLogger("oau_ai.research_gap")

# Gap classification types as required by the functional specification.
GAP_TYPE_TOPIC = "topic_gap"
GAP_TYPE_METHODOLOGICAL = "methodological_gap"
GAP_TYPE_POPULATION_CONTEXT = "population_context_gap"
GAP_TYPE_EVIDENCE = "evidence_gap"
GAP_TYPE_CONTRADICTORY = "contradictory_findings"

ALL_GAP_TYPES = [
    GAP_TYPE_TOPIC,
    GAP_TYPE_METHODOLOGICAL,
    GAP_TYPE_POPULATION_CONTEXT,
    GAP_TYPE_EVIDENCE,
    GAP_TYPE_CONTRADICTORY,
]

# Source origin types.
SOURCE_AUTHOR_LIMITATION = "author_stated"
SOURCE_SYSTEM_INFERRED = "system_inferred"
# Gaps whose descriptions overlap at least this much (Jaccard over content
# words) are the same finding phrased twice.
CONSOLIDATION_THRESHOLD = 0.6


@dataclass
class ResearchGapCitation:
    """A validated citation mapping to actual retrieved evidence."""

    chunk_id: str
    document_id: str
    backend_thesis_id: str
    text_snippet: str
    page_number: Optional[int]
    section: Optional[str]
    relevance_score: float


@dataclass
class ResearchGap:
    """A single identified research gap with full provenance."""

    gap_type: str
    description: str
    supporting_evidence: str
    source_thesis_references: List[str]
    page_numbers: List[Optional[int]]
    chunk_citations: List[ResearchGapCitation]
    source_origin: str  # "author_stated" or "system_inferred"
    explanation: str
    suggested_research_direction: str
    confidence: float


@dataclass
class ResearchGapResponse:
    """Structured research gap detection response."""

    gaps: List[ResearchGap]
    insufficient_evidence: bool
    confidence: float
    decision_engine: str
    llm_tier: int
    trace_id: str
    request_id: str
    message: Optional[str] = None


class ResearchGapService:
    """Detects research gaps from retrieved thesis content.

    Pipeline:
    1. JEV classification (security/decision gate)
    2. Verify document access
    3. Hybrid retrieval (dense Vectorize + lexical PostgreSQL FTS, RRF fused)
    4. Optional cross-encoder reranking
    5. Fetch authorized chunk text + provenance from PostgreSQL
    6. DeepSeek gap analysis using only retrieved evidence
    7. Citation validation against actual evidence
    8. Structured abstention if evidence is insufficient
    """

    def __init__(
        self,
        db_session=None,
        llm_router: Optional[ProviderRouter] = None,
        retrieval_service: Optional[RetrievalService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        vectorize_service: Optional[VectorizeService] = None,
        jev_client: Optional[JEVClient] = None,
        reranker: Optional[Any] = None,
    ) -> None:
        self.db_session = db_session
        self.llm_router = llm_router or get_router()
        self.retrieval_service = retrieval_service or RetrievalService(db_session)
        self.embedding_service = embedding_service or EmbeddingService()
        self.vectorize_service = vectorize_service or VectorizeService()
        self.jev_client = jev_client or JEVClient()
        self.reranker = reranker

    async def detect_gaps(
        self,
        research_question: str,
        actor_context: ActorContext,
        document_ids: Optional[List[str]] = None,
        top_k: int = 10,
        request_id: Optional[str] = None,
    ) -> ResearchGapResponse:
        """Detect research gaps from retrieved thesis evidence.

        Two-phase JEV execution:
        Phase 1 (pre-retrieval): Security-only screening — prompt injection
        and policy enforcement, no evidence required. This allows legitimate
        research-gap requests to proceed to retrieval without being blocked
        for missing evidence.
        Phase 2 (post-retrieval): Full JEV classification with retrieved
        evidence present in state, enabling evidence-dependent guardrails.

        Pipeline:
        1. JEV phase 1: security screening (no evidence)
        2. Verify document access
        3. Hybrid retrieval of thesis content
        4. JEV phase 2: full classification with evidence
        5. Optional cross-encoder reranking
        6. Fetch authorized chunk text + provenance from PostgreSQL
        7. DeepSeek gap analysis using only retrieved evidence
        8. Citation validation against actual evidence
        9. Structured abstention if evidence is insufficient
        """
        trace_id = actor_context.trace_id or str(uuid.uuid4())
        request_id = request_id or str(uuid.uuid4())

        with telemetry_context(
            component="research_gap_service",
            event_type="gap_analysis",
            trace_id=trace_id,
            model_provider="deepseek",
            llm_tier=1,
        ) as _:
            # Phase 1: JEV security screening — no evidence required.
            # This checks prompt injection and policy enforcement only,
            # allowing legitimate research questions to proceed to retrieval.
            jev_decision = await self._classify_with_jev(
                research_question,
                actor_context,
                trace_id,
                require_evidence=False,
            )
            if jev_decision.decision.value == "block":
                return ResearchGapResponse(
                    gaps=[],
                    insufficient_evidence=True,
                    confidence=0.0,
                    decision_engine="jev",
                    llm_tier=1,
                    trace_id=trace_id,
                    request_id=request_id,
                    message=f"Request blocked by JEV: {jev_decision.fallback_reason.value}",
                )

            # Step 2: Verify document access
            if document_ids:
                accessible_ids = await self.retrieval_service.verify_access_before_retrieval(
                    actor_context, document_ids
                )
            else:
                accessible_ids = None

            # Step 3: Hybrid retrieval
            query_embedding = await self._embed_question(research_question)
            vectorize_results = await self._query_vectorize(
                query_embedding, top_k, accessible_ids, actor_context
            )

            retrieved_chunks = await self.retrieval_service.hybrid_retrieve(
                actor_context=actor_context,
                query=research_question,
                query_vector=query_embedding,
                vectorize_results=vectorize_results,
                document_ids=accessible_ids,
                top_k=top_k,
            )

            # Step 4: Optional reranking
            if retrieved_chunks and self.reranker:
                retrieved_chunks = self.reranker.rerank(
                    research_question, retrieved_chunks, top_k=top_k
                )

            # Step 5: Convert to AuthorizedChunk for generation
            authorized_chunks = self._to_authorized_chunks(retrieved_chunks)

            if not authorized_chunks:
                return ResearchGapResponse(
                    gaps=[],
                    insufficient_evidence=True,
                    confidence=0.0,
                    decision_engine="deepseek",
                    llm_tier=1,
                    trace_id=trace_id,
                    request_id=request_id,
                    message="No accessible evidence found for gap analysis.",
                )

            # Phase 2: JEV full classification with retrieved evidence present.
            # Evidence-dependent guardrails now have data to evaluate.
            evidence_list = [
                {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                }
                for chunk in authorized_chunks
            ]
            jev_decision = await self._classify_with_jev(
                research_question,
                actor_context,
                trace_id,
                require_evidence=True,
                evidence=evidence_list,
            )
            if jev_decision.decision.value == "block":
                return ResearchGapResponse(
                    gaps=[],
                    insufficient_evidence=True,
                    confidence=0.0,
                    decision_engine="jev",
                    llm_tier=1,
                    trace_id=trace_id,
                    request_id=request_id,
                    message=f"Request blocked by JEV: {jev_decision.fallback_reason.value}",
                )

            # Step 6: DeepSeek gap analysis using only retrieved evidence
            gap_result = await self._analyze_gaps(
                research_question, authorized_chunks, trace_id
            )

            # Step 7: Validate citations against actual evidence
            validated_gaps = self._validate_gap_citations(
                gap_result, authorized_chunks
            )

            # Step 7b: Consolidate duplicate gaps so the same finding is not
            # reported twice with different wording.
            validated_gaps = self._consolidate_gaps(validated_gaps)

            # Step 8: Determine if evidence is sufficient
            insufficient_evidence = self._is_insufficient(validated_gaps)

            return ResearchGapResponse(
                gaps=validated_gaps,
                insufficient_evidence=insufficient_evidence,
                confidence=self._calculate_confidence(validated_gaps),
                decision_engine="deepseek",
                llm_tier=1,
                trace_id=trace_id,
                request_id=request_id,
                message=(
                    "Insufficient evidence to identify research gaps with confidence."
                    if insufficient_evidence
                    else None
                ),
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
        self,
        question: str,
        actor_context: ActorContext,
        trace_id: str,
        require_evidence: bool = True,
        evidence: Optional[List[dict]] = None,
    ) -> object:
        """Classify the gap analysis request using JEV decision layer.

        Args:
            require_evidence: When False (phase 1), skips the evidence-required
                guardrail check so legitimate research questions can proceed
                to retrieval. When True (phase 2), evidence must be present
                for research-style queries.
            evidence: Pre-retrieved evidence chunks for phase 2 evaluation.
        """
        router = TypedDecisionRouter(
            jev_client=self.jev_client,
        )
        state = {
            "user_input": question,
            "query": question,
            "evidence": evidence or [],
            "actor_context": actor_context.to_dict(),
        }
        decision = await router.route(
            task_type=TaskType.RESEARCH_GAP_ANALYSIS,
            state=state,
            user_id=actor_context.user_id,
            require_evidence=require_evidence,
        )
        return decision

    async def _embed_question(self, question: str) -> List[float]:
        """Generate an embedding for the gap analysis question.

        Raises:
            ConfigurationError: If the embedding service is not available.
        """
        result = self.embedding_service.embed_text(question)
        return result.vector

    async def _query_vectorize(
        self,
        query_vector: List[float],
        top_k: int,
        accessible_ids: Optional[List[str]],
        actor_context: ActorContext,
    ) -> List[dict]:
        """Query Vectorize for nearest neighbors, then filter by access."""
        if not self.vectorize_service.is_configured():
            logger.warning("Vectorize not configured; skipping semantic retrieval.")
            return []

        try:
            filter_metadata = {}
            if accessible_ids:
                filter_metadata = metadata_in_filter("document_id", accessible_ids)

            result = self.vectorize_service.query(
                vector=query_vector,
                top_k=top_k,
                filter=filter_metadata,
            )

            matches = result.get("result", {}).get("matches", [])
            return matches
        except ProviderUnavailableError as exc:
            logger.warning("Vectorize query failed: %s", exc.message)
            return []

    async def _analyze_gaps(
        self,
        research_question: str,
        chunks: List[AuthorizedChunk],
        trace_id: str,
    ) -> dict:
        """Analyze research gaps using DeepSeek with only retrieved evidence.

        The model is instructed to:
        - Identify gaps across topic, methodological, population/context,
          evidence, and contradictory findings categories
        - Distinguish author-stated limitations from system-inferred gaps
        - Return only gaps backed by actual retrieved evidence
        - Provide page numbers, chunk citations, and confidence for each gap
        - Never fabricate citations, findings, or gaps
        """
        context_parts = []
        for i, chunk in enumerate(chunks):
            page_info = f" (page {chunk.page_number})" if chunk.page_number else ""
            thesis_info = (
                f" [thesis: {chunk.backend_thesis_id}]"
            )
            context_parts.append(
                f"[Source {i+1}]{thesis_info}{page_info}\n"
                f"{chunk.text}\n"
                f"  chunk_id={chunk.chunk_id}, document_id={chunk.document_id}"
            )

        context = "\n\n---\n\n".join(context_parts)

        system_prompt = (
            "You are an expert academic research assistant specialized in "
            "research gap detection. "
            "Analyze the provided thesis excerpts to identify potential "
            "research gaps. "
            "You must ONLY use the provided evidence — never invent "
            "citations, findings, or gaps. "
            "Classify each gap into one of: topic_gap, methodological_gap, "
            "population_context_gap, evidence_gap, contradictory_findings. "
            "Distinguish between gaps explicitly stated by authors "
            "(author_stated) and gaps inferred by your analysis "
            "(system_inferred). "
            "For each gap, provide: gap description, supporting evidence "
            "from the text, source thesis references, page numbers or "
            "chunk citations, explanation of why it represents a gap, "
            "suggested research direction, and confidence level (0.0-1.0). "
            "If the evidence is insufficient to identify any gaps, state "
            "that clearly. "
            "Return your answer as a JSON object with keys: gaps (array), "
            "insufficient_evidence (boolean), confidence (float), message "
            "(string)."
        )

        user_prompt = (
            f"Research Question: {research_question}\n\n"
            f"Evidence (thesis excerpts):\n{context}\n\n"
            "Identify research gaps based ONLY on the evidence above. "
            "Return a JSON object."
        )

        response = complete_with_deepseek(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2048,
            temperature=0.2,
            json_mode=True,
        )

        return self._parse_gap_response(response.content)

    def _parse_gap_response(self, content: str) -> dict:
        """Parse the DeepSeek JSON response into a structured dict.

        Handles both valid JSON and graceful degradation for malformed
        responses.
        """
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            # Try to extract JSON from within markdown code blocks or text.
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except (json.JSONDecodeError, ValueError):
                    return {
                        "gaps": [],
                        "insufficient_evidence": True,
                        "confidence": 0.0,
                        "message": "Failed to parse gap analysis response.",
                    }
            else:
                return {
                    "gaps": [],
                    "insufficient_evidence": True,
                    "confidence": 0.0,
                    "message": "Failed to parse gap analysis response.",
                }

        # Ensure required keys exist with sensible defaults.
        if "gaps" not in data:
            data["gaps"] = []
        if "insufficient_evidence" not in data:
            data["insufficient_evidence"] = True
        if "confidence" not in data:
            data["confidence"] = 0.0
        if "message" not in data:
            data["message"] = None

        return data

    def _validate_gap_citations(
        self, gap_result: dict, chunks: List[AuthorizedChunk]
    ) -> List[ResearchGap]:
        """Validate that every citation in each gap maps to actual evidence.

        Performs anti-fabrication checks:
        1. Each cited chunk_id must refer to a real retrieved chunk.
        2. The cited text snippet must have meaningful word overlap with
           the source chunk text.
        3. Page numbers must match the source chunk's page.

        Strips invalid citations from each gap. Removes gaps that have
        no valid citations remaining.
        """
        valid_chunk_ids = {c.chunk_id for c in chunks}
        chunk_map = {c.chunk_id: c for c in chunks}

        validated_gaps: List[ResearchGap] = []

        for gap_data in gap_result.get("gaps", []):
            gap_type = gap_data.get("gap_type", GAP_TYPE_TOPIC)
            description = gap_data.get("description", "")
            supporting_evidence = gap_data.get("supporting_evidence", "")
            source_thesis_refs = gap_data.get("source_thesis_references", [])
            source_origin = gap_data.get("source_origin", SOURCE_SYSTEM_INFERRED)
            explanation = gap_data.get("explanation", "")
            suggested_direction = gap_data.get("suggested_research_direction", "")
            confidence = float(gap_data.get("confidence", 0.5))

            # Validate each citation.
            validated_citations: List[ResearchGapCitation] = []
            page_numbers: List[Optional[int]] = []

            for cit in gap_data.get("citations", []):
                chunk_id = cit.get("chunk_id", "")
                if chunk_id not in valid_chunk_ids:
                    continue  # Fabricated citation — skip.

                chunk = chunk_map[chunk_id]
                text_snippet = cit.get("text_snippet", "")

                # Anti-fabrication: snippet must overlap with actual chunk text.
                if not self._text_overlaps(text_snippet, chunk.text):
                    continue

                page_number = cit.get("page_number")
                if page_number is not None and page_number != chunk.page_number:
                    # Page number mismatch — use actual page from chunk.
                    page_number = chunk.page_number

                validated_citations.append(
                    ResearchGapCitation(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        backend_thesis_id=chunk.backend_thesis_id,
                        text_snippet=text_snippet[:200],
                        page_number=page_number if page_number else chunk.page_number,
                        section=chunk.section,
                        relevance_score=cit.get("relevance_score", 0.0),
                    )
                )
                page_numbers.append(
                    page_number if page_number else chunk.page_number
                )

            # Only include gaps that have at least one valid citation.
            if not validated_citations:
                continue

            validated_gaps.append(
                ResearchGap(
                    gap_type=gap_type,
                    description=description,
                    supporting_evidence=supporting_evidence,
                    source_thesis_references=source_thesis_refs,
                    page_numbers=page_numbers,
                    chunk_citations=validated_citations,
                    source_origin=source_origin,
                    explanation=explanation,
                    suggested_research_direction=suggested_direction,
                    confidence=confidence,
                )
            )

        return validated_gaps

    @staticmethod
    def _text_overlaps(text_a: str, text_b: str, min_overlap_words: int = 1) -> bool:
        """Check whether two text strings share meaningful words.

        Used as an anti-fabrication check for citations.
        """
        if not text_a or not text_b:
            return False

        words_a = set(
            w.strip(".,!?;:\"'()[]{}").lower()
            for w in text_a.split()
            if len(w.strip(".,!?;:\"'()[]{}")) > 3
        )
        words_b = set(
            w.strip(".,!?;:\"'()[]{}").lower()
            for w in text_b.split()
            if len(w.strip(".,!?;:\"'()[]{}")) > 3
        )

        overlap = words_a & words_b
        return len(overlap) >= min_overlap_words

    @staticmethod
    def _gap_words(gap: ResearchGap) -> set:
        text = f"{gap.description} {gap.supporting_evidence}"
        return {
            word.strip(".,!?;:\"'()[]{}").lower()
            for word in text.split()
            if len(word.strip(".,!?;:\"'()[]{}")) > 3
        }

    def _consolidate_gaps(self, gaps: List[ResearchGap]) -> List[ResearchGap]:
        """Merge gaps that describe the same finding under the same type.

        Overlap is Jaccard similarity over content words. The surviving gap
        keeps the highest confidence, unions the citations and references, and
        keeps the author-stated origin if either side had it, so a duplicate
        never dilutes the evidence or downgrades an explicit author limitation.
        """
        consolidated: List[ResearchGap] = []

        for gap in gaps:
            words = self._gap_words(gap)
            match = None
            for existing in consolidated:
                if existing.gap_type != gap.gap_type:
                    continue
                other = self._gap_words(existing)
                if not words or not other:
                    continue
                if len(words & other) / len(words | other) >= CONSOLIDATION_THRESHOLD:
                    match = existing
                    break

            if match is None:
                consolidated.append(gap)
                continue

            seen = {citation.chunk_id for citation in match.chunk_citations}
            for citation in gap.chunk_citations:
                if citation.chunk_id not in seen:
                    match.chunk_citations.append(citation)
                    seen.add(citation.chunk_id)

            for reference in gap.source_thesis_references:
                if reference not in match.source_thesis_references:
                    match.source_thesis_references.append(reference)

            for page in gap.page_numbers:
                if page not in match.page_numbers:
                    match.page_numbers.append(page)

            if gap.source_origin == SOURCE_AUTHOR_LIMITATION:
                match.source_origin = SOURCE_AUTHOR_LIMITATION
            match.confidence = max(match.confidence, gap.confidence)

        return consolidated

    def _is_insufficient(self, gaps: List[ResearchGap]) -> bool:
        """Determine whether the evidence is insufficient for gap analysis."""
        if not gaps:
            return True
        # If all gaps have very low confidence, evidence is insufficient.
        avg_confidence = sum(g.confidence for g in gaps) / len(gaps)
        return avg_confidence < 0.30

    def _calculate_confidence(self, gaps: List[ResearchGap]) -> float:
        """Calculate deterministic confidence based on gap quality."""
        if not gaps:
            return 0.0
        avg_confidence = sum(g.confidence for g in gaps) / len(gaps)
        # Scale based on number of gaps and citation coverage.
        citation_coverage = sum(
            len(g.chunk_citations) for g in gaps
        ) / max(len(gaps), 1)
        confidence = min(avg_confidence * 0.7 + citation_coverage * 0.3, 1.0)
        return round(confidence, 3)
