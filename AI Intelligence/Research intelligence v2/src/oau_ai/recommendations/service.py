"""Research recommendations grounded in authorised repository evidence.

Ranking is deterministic and evidence-derived: candidates come from the P2
hybrid retrieval boundary (access enforced in PostgreSQL), are grouped by
thesis, and are scored from the fused retrieval score plus how many distinct
chunks support them.

No LLM call is made. Nothing here claims academic novelty or research quality:
a thesis absent from the repository is *unseen*, not non-existent, and high
similarity is relevance to the caller's context, not merit.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..auth.middleware import ActorContext
from ..embeddings.service import EmbeddingService
from ..embeddings.vectorize import VectorizeService
from ..errors import Phase3Error, ProviderUnavailableError
from ..memory.service import MemoryService
from ..retrieval.service import RetrievalService, RetrievedChunk

logger = logging.getLogger("oau_ai.recommendations")

RECOMMENDATION_THESIS = "existing_thesis"
RECOMMENDATION_TOPIC = "related_topic"

MAX_CANDIDATE_CHUNKS = 50
MAX_EVIDENCE_PER_ITEM = 3
MAX_EXPLANATION_TERMS = 6

STOPWORDS = {
    "about", "after", "analysis", "based", "between", "could", "during",
    "effect", "effects", "from", "into", "study", "that", "their", "there",
    "these", "they", "this", "through", "using", "were", "what", "when",
    "where", "which", "while", "with", "would",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")


@dataclass
class EvidenceRef:
    chunk_id: str
    document_id: str
    backend_thesis_id: str
    text_snippet: str
    page_number: Optional[int]


@dataclass
class Recommendation:
    recommendation_type: str
    title: str
    backend_thesis_id: Optional[str]
    explanation: str
    evidence: List[EvidenceRef]
    evidence_strength: float
    limitations: List[str] = field(default_factory=list)


@dataclass
class RecommendationResponse:
    context_source: str
    query: str
    recommendations: List[Recommendation]
    insufficient_evidence: bool
    message: Optional[str] = None
    limitations: List[str] = field(default_factory=list)


class RecommendationService:
    """Builds evidence-backed thesis recommendations for an actor."""

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        vectorize_service: Optional[VectorizeService] = None,
        memory_service: Optional[MemoryService] = None,
        db_session=None,
    ) -> None:
        self.db_session = db_session
        self.retrieval_service = retrieval_service or RetrievalService(db_session)
        self.embedding_service = embedding_service or EmbeddingService()
        self.vectorize_service = vectorize_service or VectorizeService()
        self.memory_service = memory_service or MemoryService(db_session=db_session)

    @staticmethod
    def _terms(text: str) -> List[str]:
        terms = []
        for raw in _TOKEN_RE.findall(text or ""):
            token = raw.strip("-'").lower()
            if len(token) > 3 and token not in STOPWORDS:
                terms.append(token)
        return terms

    async def _memory_context(self, actor: ActorContext) -> str:
        try:
            context, _ = await self.memory_service.build_memory_context(
                user_id=actor.user_id, query="research interests objectives", top_k=5
            )
            return context
        except Exception:  # noqa: BLE001
            logger.warning("recommendations.memory_unavailable")
            return ""

    async def _query_vectorize(self, text: str, top_k: int) -> List[dict]:
        if not self.vectorize_service.is_configured():
            return []
        try:
            embedding = self.embedding_service.embed_text(text)
            result = self.vectorize_service.query(
                vector=embedding.vector, top_k=min(top_k * 4, MAX_CANDIDATE_CHUNKS)
            )
            return result.get("result", {}).get("matches", [])
        except (ProviderUnavailableError, Phase3Error) as exc:
            logger.warning("recommendations.vectorize_degraded: %s", exc)
            return []

    async def recommend(
        self,
        actor: ActorContext,
        query: Optional[str] = None,
        seed_thesis_id: Optional[str] = None,
        top_k: int = 5,
    ) -> RecommendationResponse:
        """Recommend existing theses relevant to the caller's research context."""
        bounded_top_k = max(1, min(int(top_k), 20))

        if query and query.strip():
            context_text = query.strip()
            context_source = "request"
        else:
            memory_text = await self._memory_context(actor)
            if memory_text:
                context_text = memory_text
                context_source = "memory"
            elif seed_thesis_id:
                context_text = await self._seed_text(actor, seed_thesis_id)
                context_source = "seed_thesis"
            else:
                return RecommendationResponse(
                    context_source="none",
                    query="",
                    recommendations=[],
                    insufficient_evidence=True,
                    message=(
                        "No research context was supplied and no stored research "
                        "interests were found, so no recommendation can be made."
                    ),
                )

        if not context_text:
            return RecommendationResponse(
                context_source=context_source,
                query="",
                recommendations=[],
                insufficient_evidence=True,
                message="The research context could not be read.",
            )

        matches = await self._query_vectorize(context_text, bounded_top_k)
        chunks = await self.retrieval_service.hybrid_retrieve(
            actor_context=actor,
            query=context_text,
            query_vector=[],
            vectorize_results=matches,
            top_k=min(bounded_top_k * 2, 20),
        )

        if not chunks:
            return RecommendationResponse(
                context_source=context_source,
                query=context_text,
                recommendations=[],
                insufficient_evidence=True,
                message="No accessible repository evidence matches this context.",
                limitations=[
                    "An empty result means nothing in this repository matched; it "
                    "does not mean the topic is unstudied elsewhere.",
                ],
            )

        grouped = self._group_by_thesis(chunks)
        ranked = sorted(
            grouped.values(),
            key=lambda group: (-group["top_score"], -len(group["chunks"]), group["thesis_id"]),
        )[:bounded_top_k]

        context_terms = set(self._terms(context_text))
        recommendations = [
            self._build_recommendation(group, context_terms, rank)
            for rank, group in enumerate(ranked)
        ]

        return RecommendationResponse(
            context_source=context_source,
            query=context_text,
            recommendations=recommendations,
            insufficient_evidence=False,
            limitations=[
                "Recommendations reflect similarity to your stated context within "
                "this repository, not research quality or academic novelty.",
                "Absence of a topic from this repository is not evidence that the "
                "topic is unstudied.",
            ],
        )

    async def _seed_text(self, actor: ActorContext, thesis_id: str) -> str:
        access = await self.retrieval_service.check_document_access(thesis_id, actor)
        if not access.can_view:
            return ""
        return access.title or ""

    @staticmethod
    def _group_by_thesis(chunks: List[RetrievedChunk]) -> Dict[str, dict]:
        grouped: Dict[str, dict] = {}
        for chunk in chunks:
            key = chunk.backend_thesis_id
            group = grouped.setdefault(
                key,
                {
                    "thesis_id": key,
                    "document_id": chunk.document_id,
                    "title": (chunk.provenance or {}).get("source_file") or key,
                    "top_score": 0.0,
                    "chunks": [],
                },
            )
            group["chunks"].append(chunk)
            score = chunk.fused_score or chunk.dense_score or chunk.lexical_score or 0.0
            group["top_score"] = max(group["top_score"], float(score))
        return grouped

    def _build_recommendation(
        self, group: dict, context_terms: set, rank: int
    ) -> Recommendation:
        chunks: List[RetrievedChunk] = group["chunks"][:MAX_EVIDENCE_PER_ITEM]
        overlap: List[str] = []
        for chunk in chunks:
            for term in self._terms(chunk.text):
                if term in context_terms and term not in overlap:
                    overlap.append(term)

        if overlap:
            shared = ", ".join(overlap[:MAX_EXPLANATION_TERMS])
            explanation = (
                f"Matches your research context on: {shared}. "
                f"Supported by {len(group['chunks'])} retrieved passage(s)."
            )
        else:
            explanation = (
                "Retrieved as semantically related to your research context. "
                f"Supported by {len(group['chunks'])} retrieved passage(s)."
            )

        # Evidence strength from retrieval rank and support count, bounded 0..1.
        support = min(len(group["chunks"]) / 3.0, 1.0)
        strength = round(min(0.5 * support + 0.5 * (1.0 / (rank + 1)), 1.0), 3)

        return Recommendation(
            recommendation_type=RECOMMENDATION_THESIS,
            title=group["title"],
            backend_thesis_id=group["thesis_id"],
            explanation=explanation,
            evidence=[
                EvidenceRef(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    backend_thesis_id=chunk.backend_thesis_id,
                    text_snippet=chunk.text[:200],
                    page_number=chunk.page_number,
                )
                for chunk in chunks
            ],
            evidence_strength=strength,
            limitations=[
                "Similarity to your context; this is not a judgement of quality.",
            ],
        )
