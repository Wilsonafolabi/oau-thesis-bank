"""Researcher Memory Service — Phase 5.3.

Implements a persistent, user-specific memory system with four layers:

A. Working Memory — rolling window of last 5 exchanges per researcher,
   older exchanges summarized.
B. Researcher Profile Memory — stable context (interests, department,
   objectives, methodologies, preferences, supervisor).
C. Research and Document Memory — compact thesis summaries linked to
   source documents.
D. Semantic and Entity Memory — entities, relationships, time-aware
   updates, semantic retrieval via Vectorize with user_id isolation.

Storage: PostgreSQL is the canonical store. Vectorize is used only for
semantic memory retrieval with user_id-based isolation — no new database
is introduced.

Memory lifecycle:
1. Candidate extraction from conversation
2. Fact validation and normalization (LLM inferences are NOT stored as
   personal facts)
3. Deduplication
4. Relevance scoring
5. Memory creation and updates
6. Expiration/archival of stale info
7. Semantic retrieval
8. Memory summarization
9. Memory correction and deletion

Sensitive personal information, credentials, and unrelated private
details are never extracted into researcher memory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.middleware import ActorContext
from ..db.models import (
    AIChunk,
    AIDocument,
    MemoryEntity,
    MemoryRelationship,
    ResearcherMemory,
    ThesisSummary,
    WorkingMemoryExchange,
    MemorySource,
    MemoryType,
)
from ..db.session import get_session_factory as AsyncSessionLocal
from ..embeddings.service import EmbeddingService
from ..embeddings.vectorize import VectorizeService, metadata_in_filter
from ..errors import ConfigurationError, Phase3Error, ProviderUnavailableError
from ..llm.router import complete_with_deepseek, get_router
from ..retrieval.service import RetrievalService
from ..telemetry.core import TelemetryEvent, telemetry_context

logger = logging.getLogger("oau_ai.memory")

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

WORKING_MEMORY_WINDOW = 5  # Last 5 exchanges kept verbatim
MEMORY_DEFAULT_CONFIDENCE = "0.5"
MEMORY_HIGH_CONFIDENCE = "0.85"
MEMORY_STALE_DAYS = 90  # Memories older than this may be archived
MEMORY_LOW_CONFIDENCE_ARCHIVE = "0.3"  # Archive if confidence below this
MAX_SEMANTIC_RESULTS = 10
MAX_WORKING_MEMORY_CHARS = 4000  # Token budget for working memory context

# Selective retrieval: durable context is injected into prompts, so it is
# capped and ranked rather than dumped wholesale.
MAX_MEMORY_CONTEXT_CHARS = 1500
MEMORY_RELEVANCE_WEIGHT = 0.5
MEMORY_CONFIDENCE_WEIGHT = 0.3
MEMORY_RECENCY_WEIGHT = 0.2
MEMORY_CORRECTION_BONUS = 0.2
MEMORY_RECENCY_HALF_LIFE_DAYS = 90.0

# Thesis summarisation limits (bounded so long documents stay within budget).
SUMMARY_MAX_SOURCE_CHARS = 24000
SUMMARY_BATCH_CHARS = 6000
SUMMARY_SECTIONS = (
    "research_problem",
    "objectives",
    "research_questions",
    "methodology",
    "dataset",
    "findings",
    "contributions",
    "limitations",
    "future_work",
)
SENSITIVE_PATTERNS = [
    r"password\s*[:=]\s*\S+",
    r"password\s+(?:is\s+)?\S+",
    r"api[_-]?key\s*[:=]\s*\S+",
    r"secret\s*[:=]\s*\S+",
    r"token\s*[:=]\s*\S+",
    r"credential\s*[:=]\s*\S+",
]


@dataclass
class MemoryEntry:
    """A single memory entry returned by the service."""

    id: str
    user_id: str
    memory_type: str
    source: str
    key: str
    value: str
    confidence: float
    is_archived: bool
    source_document_id: Optional[str]
    source_chunk_id: Optional[str]
    provenance: Dict[str, Any]
    created_at: str
    updated_at: str


@dataclass
class MemorySearchResult:
    """Result of semantic memory search."""

    entries: List[MemoryEntry]
    total_found: int
    query: str


@dataclass
class ThesisSummaryData:
    """Structured thesis summary."""

    document_id: str
    backend_thesis_id: str
    user_id: str
    title: Optional[str]
    abstract_summary: Optional[str]
    research_questions: List[str]
    objectives: List[str]
    methodology: Optional[str]
    findings: List[str]
    limitations: List[str]
    key_entities: List[str]
    confidence: float
    missing_sections: List[str] = field(default_factory=list)


class MemoryService:
    """Researcher memory service — persistent, user-specific memory.

    Provides CRUD operations for researcher memories with full lifecycle
    management: extraction, validation, deduplication, relevance scoring,
    creation, updates, expiration, semantic retrieval, summarization,
    correction, and deletion.
    """

    def __init__(
        self,
        db_session=None,
        embedding_service: Optional[EmbeddingService] = None,
        vectorize_service: Optional[VectorizeService] = None,
        retrieval_service: Optional[RetrievalService] = None,
    ) -> None:
        self.db_session = db_session
        self.embedding_service = embedding_service or EmbeddingService()
        self.vectorize_service = vectorize_service or VectorizeService()
        self.retrieval_service = retrieval_service

    # ------------------------------------------------------------------
    # Session helper
    # ------------------------------------------------------------------

    async def _get_session(self) -> AsyncSession:
        if self.db_session is not None:
            return self.db_session
        factory = AsyncSessionLocal()
        return factory()

    # ------------------------------------------------------------------
    # A. Working Memory
    # ------------------------------------------------------------------

    async def add_working_memory_exchange(
        self,
        user_id: str,
        exchange_type: str,
        content: str,
        unresolved_questions: Optional[List[str]] = None,
        decisions: Optional[List[str]] = None,
        current_tasks: Optional[List[str]] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        """Add a working memory exchange.

        Maintains a rolling window: when more than WORKING_MEMORY_WINDOW
        verbatim exchanges exist, the oldest is summarized and marked
        is_summarized=True.
        """
        exchange_id = str(uuid.uuid4())
        session = await self._get_session()
        try:
            exchange = WorkingMemoryExchange(
                id=exchange_id,
                user_id=user_id,
                exchange_type=exchange_type,
                content=content,
                unresolved_questions=unresolved_questions or [],
                decisions=decisions or [],
                current_tasks=current_tasks or [],
                is_summarized=False,
            )
            session.add(exchange)
            await session.commit()

            # Enforce rolling window: summarize oldest non-summarized exchanges
            # beyond the window.
            await self._summarize_old_working_memory(session, user_id)

            return exchange_id
        finally:
            if self.db_session is None:
                await session.close()

    async def _summarize_old_working_memory(
        self, session: AsyncSession, user_id: str
    ) -> None:
        """Summarize working memory exchanges beyond the rolling window."""
        # Get non-summarized exchanges ordered by created_at desc
        result = await session.execute(
            select(WorkingMemoryExchange)
            .where(
                and_(
                    WorkingMemoryExchange.user_id == user_id,
                    WorkingMemoryExchange.is_summarized == False,  # noqa: E712
                )
            )
            .order_by(WorkingMemoryExchange.created_at.desc())
        )
        exchanges = result.scalars().all()

        if len(exchanges) <= WORKING_MEMORY_WINDOW:
            return

        # Mark all but the last WORKING_MEMORY_WINDOW as summarized
        to_summarize = exchanges[WORKING_MEMORY_WINDOW:]
        for ex in to_summarize:
            ex.is_summarized = True
            ex.summary = f"[Summarized exchange from {ex.created_at.date().isoformat()}]"

        await session.commit()

    async def get_working_memory_context(
        self, user_id: str, max_chars: int = MAX_WORKING_MEMORY_CHARS
    ) -> str:
        """Get working memory context for LLM prompt injection.

        Returns recent verbatim exchanges plus summaries of older ones,
        truncated to fit within the token budget.
        """
        session = await self._get_session()
        try:
            result = await session.execute(
                select(WorkingMemoryExchange)
                .where(WorkingMemoryExchange.user_id == user_id)
                .order_by(WorkingMemoryExchange.created_at.desc())
            )
            exchanges = result.scalars().all()

            if not exchanges:
                return ""

            parts: List[str] = []
            total_chars = 0

            # Process most recent first
            for ex in exchanges:
                if ex.is_summarized:
                    entry = f"[Summary] {ex.summary or ex.content}\n"
                else:
                    entry = f"[{ex.exchange_type}] {ex.content}\n"

                if total_chars + len(entry) > max_chars:
                    break
                parts.insert(0, entry)
                total_chars += len(entry)

            return "\n".join(parts)
        finally:
            if self.db_session is None:
                await session.close()

    # ------------------------------------------------------------------
    # B. Researcher Profile Memory
    # ------------------------------------------------------------------

    async def upsert_profile_memory(
        self,
        user_id: str,
        key: str,
        value: str,
        confidence: float = 0.5,
        source: str = MemorySource.SYSTEM_INFERRED.value,
        trace_id: Optional[str] = None,
    ) -> str:
        """Create or update a researcher profile memory entry.

        If a memory with the same user_id + key exists, it is updated
        (confidence averaged). Otherwise a new entry is created.
        """
        session = await self._get_session()
        try:
            result = await session.execute(
                select(ResearcherMemory).where(
                    and_(
                        ResearcherMemory.user_id == user_id,
                        ResearcherMemory.key == key,
                        ResearcherMemory.memory_type == MemoryType.PROFILE,
                        ResearcherMemory.is_archived == False,  # noqa: E712
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                provenance = dict(existing.provenance or {})
                if (
                    provenance.get("user_corrected")
                    and source != MemorySource.AUTHOR_STATED.value
                ):
                    # An explicit user correction outranks anything the system
                    # later infers, so a stale value is never reintroduced.
                    logger.info("memory.corrected_value_preserved key=%s", key)
                    return existing.id

                # Average confidence
                old_conf = float(existing.confidence)
                new_conf = round((old_conf + confidence) / 2, 2)
                existing.confidence = str(new_conf)
                existing.value = value
                existing.source = source
                existing.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return existing.id
            else:
                memory_id = str(uuid.uuid4())
                memory = ResearcherMemory(
                    id=memory_id,
                    user_id=user_id,
                    memory_type=MemoryType.PROFILE,
                    source=source,
                    key=key,
                    value=value,
                    confidence=str(confidence),
                    source_document_id=None,
                    source_chunk_id=None,
                    provenance={"trace_id": trace_id},
                )
                session.add(memory)
                await session.commit()
                return memory_id
        finally:
            if self.db_session is None:
                await session.close()

    # ------------------------------------------------------------------
    # C. Research and Document Memory (Thesis Summaries)
    # ------------------------------------------------------------------

    async def create_thesis_summary(
        self,
        document_id: str,
        backend_thesis_id: str,
        user_id: str,
        title: Optional[str],
        abstract_summary: Optional[str],
        research_questions: List[str],
        objectives: List[str],
        methodology: Optional[str],
        findings: List[str],
        limitations: List[str],
        key_entities: List[str],
        confidence: float = 0.5,
        source_hash: Optional[str] = None,
        source_version: Optional[str] = None,
        generated_at: Optional[datetime] = None,
    ) -> str:
        """Create or update a thesis summary.

        Linked to the original document for provenance. Reused across
        conversations instead of reprocessing entire documents.

        When ``source_hash`` is supplied and differs from the stored hash, the
        previous row is kept as history (``superseded_by`` points at the new
        row) and the new row carries ``version + 1``. Without a hash the
        existing row is updated in place, preserving legacy behaviour.
        """
        fields = {
            "title": title,
            "abstract_summary": abstract_summary,
            "research_questions": research_questions,
            "objectives": objectives,
            "methodology": methodology,
            "findings": findings,
            "limitations": limitations,
            "key_entities": key_entities,
            "confidence": str(confidence),
            "source_hash": source_hash,
            "source_version": source_version,
            "generated_at": generated_at or datetime.now(timezone.utc),
        }

        session = await self._get_session()
        try:
            result = await session.execute(
                select(ThesisSummary).where(
                    and_(
                        ThesisSummary.backend_thesis_id == backend_thesis_id,
                        ThesisSummary.user_id == user_id,
                        ThesisSummary.superseded_by.is_(None),
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if (
                existing
                and source_hash
                and existing.source_hash
                and source_hash != existing.source_hash
            ):
                new_id = str(uuid.uuid4())
                session.add(
                    ThesisSummary(
                        id=new_id,
                        document_id=document_id,
                        backend_thesis_id=backend_thesis_id,
                        user_id=user_id,
                        version=(existing.version or 1) + 1,
                        **fields,
                    )
                )
                existing.superseded_by = new_id
                await session.commit()
                return new_id

            if existing:
                for name, value in fields.items():
                    setattr(existing, name, value)
                existing.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return existing.id

            summary_id = str(uuid.uuid4())
            session.add(
                ThesisSummary(
                    id=summary_id,
                    document_id=document_id,
                    backend_thesis_id=backend_thesis_id,
                    user_id=user_id,
                    version=1,
                    **fields,
                )
            )
            await session.commit()
            return summary_id
        finally:
            if self.db_session is None:
                await session.close()

    async def get_thesis_summary(
        self, backend_thesis_id: str, user_id: str
    ) -> Optional[ThesisSummaryData]:
        """Retrieve the current thesis summary for a user."""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(ThesisSummary).where(
                    and_(
                        ThesisSummary.backend_thesis_id == backend_thesis_id,
                        ThesisSummary.user_id == user_id,
                        ThesisSummary.superseded_by.is_(None),
                    )
                )
            )
            summary = result.scalar_one_or_none()
            if not summary:
                return None
            return ThesisSummaryData(
                document_id=summary.document_id,
                backend_thesis_id=summary.backend_thesis_id,
                user_id=summary.user_id,
                title=summary.title,
                abstract_summary=summary.abstract_summary,
                research_questions=summary.research_questions or [],
                objectives=summary.objectives or [],
                methodology=summary.methodology,
                findings=summary.findings or [],
                limitations=summary.limitations or [],
                key_entities=summary.key_entities or [],
                confidence=float(summary.confidence),
                missing_sections=self._derive_missing_sections(summary),
            )
        finally:
            if self.db_session is None:
                await session.close()

    # ------------------------------------------------------------------
    # C2. Grounded thesis summarisation from extracted chunks
    # ------------------------------------------------------------------

    _DIGEST_PROMPT = (
        "You condense part of an academic thesis. Keep only content that is "
        "explicitly present in the text: research problem, aim, objectives, "
        "research questions, methodology, dataset or study population, "
        "findings, contributions, limitations, future work. "
        "Do not infer, embellish or add outside knowledge. "
        "Write dense plain prose, at most 200 words."
    )

    _SUMMARY_PROMPT = (
        "You extract a structured summary of an academic thesis from its own "
        "text. Return ONLY a JSON object with exactly these keys: "
        "research_problem (string), objectives (array of strings), "
        "research_questions (array of strings), methodology (string), "
        "dataset (string), findings (array of strings), "
        "contributions (array of strings), limitations (array of strings), "
        "future_work (array of strings), key_entities (array of strings). "
        "Use null or [] for any section the text does not state. "
        "Never invent findings, numbers, datasets or claims that are absent. "
        "Do not include credentials, personal contact details or secrets."
    )

    async def generate_thesis_summary(
        self,
        actor_context: ActorContext,
        backend_thesis_id: str,
        max_source_chars: int = SUMMARY_MAX_SOURCE_CHARS,
    ) -> ThesisSummaryData:
        """Summarise a thesis from its own extracted text.

        Grounding rules:
        - Document access is enforced before any text is read (P2 rules).
        - Source text comes from persisted chunks, never from client metadata.
        - Missing sections are returned as empty/null and reported in
          ``missing_sections``; nothing is invented to fill them.
        - Provider failure propagates, so no partial summary is ever stored.
        """
        retrieval = self.retrieval_service or RetrievalService(self.db_session)
        access = await retrieval.check_document_access(
            backend_thesis_id, actor_context
        )
        if not access.can_view or not access.document_id:
            raise Phase3Error(
                code="access_denied",
                message="You do not have access to this thesis.",
                component="memory_service",
                trace_id=actor_context.trace_id,
                retryable=False,
            )

        session = await self._get_session()
        try:
            result = await session.execute(
                select(AIChunk)
                .where(AIChunk.document_id == access.document_id)
                .order_by(AIChunk.chunk_index)
            )
            chunks = result.scalars().all()
        finally:
            if self.db_session is None:
                await session.close()

        if not chunks:
            raise Phase3Error(
                code="summary_source_unavailable",
                message=(
                    "No extracted text is available for this thesis, so no "
                    "summary can be produced."
                ),
                component="memory_service",
                trace_id=actor_context.trace_id,
                retryable=False,
            )

        source_text = "\n\n".join(chunk.text for chunk in chunks)
        sections = await self._summarize_source(source_text, max_source_chars)

        findings = list(sections.get("findings") or [])
        findings.extend(
            f"Contribution: {item}" for item in sections.get("contributions") or []
        )
        limitations = list(sections.get("limitations") or [])
        limitations.extend(
            f"Future work: {item}" for item in sections.get("future_work") or []
        )

        await self.create_thesis_summary(
            document_id=access.document_id,
            backend_thesis_id=backend_thesis_id,
            user_id=actor_context.user_id,
            title=(access.title or "").strip() or None,
            abstract_summary=self._compose_problem_block(sections),
            research_questions=sections.get("research_questions") or [],
            objectives=sections.get("objectives") or [],
            methodology=sections.get("methodology"),
            findings=findings,
            limitations=limitations,
            key_entities=sections.get("key_entities") or [],
            confidence=self._summary_confidence(sections),
            source_hash=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            source_version=f"chunks:{len(chunks)}",
        )

        stored = await self.get_thesis_summary(backend_thesis_id, actor_context.user_id)
        if stored is None:
            raise Phase3Error(
                code="summary_persistence_failed",
                message="The generated summary could not be stored.",
                component="memory_service",
                trace_id=actor_context.trace_id,
                retryable=True,
            )
        return stored

    async def _summarize_source(
        self, source_text: str, max_source_chars: int
    ) -> Dict[str, Any]:
        """Summarise bounded source text, digesting in batches when long."""
        text = source_text[:max_source_chars]

        if len(text) > SUMMARY_BATCH_CHARS:
            batches = [
                text[start : start + SUMMARY_BATCH_CHARS]
                for start in range(0, len(text), SUMMARY_BATCH_CHARS)
            ][:8]
            digests: List[str] = []
            for batch in batches:
                digests.append(
                    await self._llm_text(
                        self._DIGEST_PROMPT, batch, json_mode=False
                    )
                )
            text = "\n\n".join(digests)

        raw = await self._llm_text(
            self._SUMMARY_PROMPT,
            f"Text:\n{text}\n\nReturn the JSON object.",
            json_mode=True,
        )
        return self._parse_summary(raw)

    async def _llm_text(
        self, system_prompt: str, user_content: str, json_mode: bool
    ) -> str:
        """Single provider call. Failures propagate — never a silent empty."""
        response = complete_with_deepseek(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1024,
            temperature=0.1,
            json_mode=json_mode,
        )
        return response.content

    def _parse_summary(self, raw: str) -> Dict[str, Any]:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise Phase3Error(
                code="summary_parse_failed",
                message="The summarisation response was not valid JSON.",
                component="memory_service",
                retryable=True,
            ) from exc

        if not isinstance(payload, dict):
            raise Phase3Error(
                code="summary_parse_failed",
                message="The summarisation response was not a JSON object.",
                component="memory_service",
                retryable=True,
            )

        return {
            "research_problem": self._as_text(payload.get("research_problem")),
            "objectives": self._as_list(payload.get("objectives")),
            "research_questions": self._as_list(payload.get("research_questions")),
            "methodology": self._as_text(payload.get("methodology")),
            "dataset": self._as_text(payload.get("dataset")),
            "findings": self._as_list(payload.get("findings")),
            "contributions": self._as_list(payload.get("contributions")),
            "limitations": self._as_list(payload.get("limitations")),
            "future_work": self._as_list(payload.get("future_work")),
            "key_entities": self._as_list(payload.get("key_entities")),
        }

    @staticmethod
    def _as_text(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _as_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _compose_problem_block(sections: Dict[str, Any]) -> Optional[str]:
        """Fold problem + dataset into the free-text field, explicitly labelled."""
        parts: List[str] = []
        if sections.get("research_problem"):
            parts.append(f"Research problem: {sections['research_problem']}")
        if sections.get("dataset"):
            parts.append(f"Dataset / study population: {sections['dataset']}")
        return "\n\n".join(parts) or None

    @staticmethod
    def _summary_confidence(sections: Dict[str, Any]) -> float:
        """Deterministic coverage of the sections the text actually supported."""
        present = 0
        for name in SUMMARY_SECTIONS:
            value = sections.get(name)
            if value:
                present += 1
        return round(present / len(SUMMARY_SECTIONS), 2)

    def _sections_from_stored(self, summary) -> Dict[str, Any]:
        """Recover the section map from what is actually persisted."""
        problem = summary.abstract_summary or ""
        dataset = None
        research_problem = problem.strip() or None
        if "Dataset / study population:" in problem:
            head, _, tail = problem.partition("Dataset / study population:")
            research_problem = head.replace("Research problem:", "").strip() or None
            dataset = tail.strip() or None
        elif problem.startswith("Research problem:"):
            research_problem = problem.replace("Research problem:", "", 1).strip() or None

        findings = summary.findings or []
        limitations = summary.limitations or []
        return {
            "research_problem": research_problem,
            "objectives": summary.objectives or [],
            "research_questions": summary.research_questions or [],
            "methodology": summary.methodology,
            "dataset": dataset,
            "findings": [f for f in findings if not f.startswith("Contribution:")],
            "contributions": [
                f.replace("Contribution:", "", 1).strip()
                for f in findings
                if f.startswith("Contribution:")
            ],
            "limitations": [
                item
                for item in limitations
                if not item.startswith("Future work:")
            ],
            "future_work": [
                item.replace("Future work:", "", 1).strip()
                for item in limitations
                if item.startswith("Future work:")
            ],
            "key_entities": summary.key_entities or [],
        }

    def _derive_missing_sections(self, summary) -> List[str]:
        sections = self._sections_from_stored(summary)
        return [name for name in SUMMARY_SECTIONS if not sections.get(name)]

    # ------------------------------------------------------------------
    # D. Semantic and Entity Memory
    # ------------------------------------------------------------------

    async def extract_entities(
        self,
        user_id: str,
        text: str,
        trace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Extract entities from text using DeepSeek.

        Extracts research topics, researchers, institutions, supervisors,
        departments. Sensitive PII and credentials are filtered out.
        """
        # Filter sensitive patterns before sending to LLM
        sanitized = self._sanitize_sensitive(text)

        system_prompt = (
            "You are an entity extraction assistant for academic research. "
            "Extract entities from the provided text. Entity types: topic, "
            "researcher, institution, supervisor, department. "
            "Return ONLY a JSON array of objects with keys: entity_type, "
            "entity_name, description, confidence (0.0-1.0). "
            "Do NOT extract passwords, API keys, tokens, credentials, or "
            "other sensitive personal information. "
            "If no entities are found, return an empty array."
        )

        user_prompt = f"Text:\n{sanitized}\n\nReturn JSON array."

        try:
            response = complete_with_deepseek(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1024,
                temperature=0.1,
                json_mode=True,
            )
        except ProviderUnavailableError:
            logger.warning("DeepSeek unavailable for entity extraction")
            return []

        try:
            entities = json.loads(response.content)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse entity extraction response")
            return []

        if not isinstance(entities, list):
            return []

        # Persist extracted entities
        session = await self._get_session()
        try:
            persisted: List[Dict[str, Any]] = []
            for ent in entities:
                entity_type = ent.get("entity_type", "topic")
                entity_name = ent.get("entity_name", "")
                if not entity_name:
                    continue

                normalized = self._normalize_entity_name(entity_name)

                # Check for existing entity (deduplication)
                existing = await self._find_existing_entity(
                    session, user_id, normalized, entity_type
                )

                if existing:
                    existing.occurrence_count += 1
                    existing.last_seen_at = datetime.now(timezone.utc)
                    # Average confidence
                    old_conf = float(existing.confidence)
                    new_conf = round(
                        (old_conf + float(ent.get("confidence", 0.5))) / 2, 2
                    )
                    existing.confidence = str(new_conf)
                    persisted.append(
                        {
                            "id": existing.id,
                            "entity_type": existing.entity_type,
                            "entity_name": existing.entity_name,
                            "normalized_name": existing.normalized_name,
                            "confidence": new_conf,
                            "action": "updated",
                        }
                    )
                else:
                    entity_id = str(uuid.uuid4())
                    entity = MemoryEntity(
                        id=entity_id,
                        user_id=user_id,
                        entity_type=entity_type,
                        entity_name=entity_name,
                        normalized_name=normalized,
                        description=ent.get("description"),
                        confidence=str(ent.get("confidence", 0.5)),
                        provenance={"trace_id": trace_id},
                    )
                    session.add(entity)
                    persisted.append(
                        {
                            "id": entity_id,
                            "entity_type": entity_type,
                            "entity_name": entity_name,
                            "normalized_name": normalized,
                            "confidence": float(ent.get("confidence", 0.5)),
                            "action": "created",
                        }
                    )

            await session.commit()
            return persisted
        finally:
            if self.db_session is None:
                await session.close()

    async def _find_existing_entity(
        self,
        session: AsyncSession,
        user_id: str,
        normalized_name: str,
        entity_type: str,
    ) -> Optional[MemoryEntity]:
        """Find an existing entity by normalized name and type."""
        result = await session.execute(
            select(MemoryEntity).where(
                and_(
                    MemoryEntity.user_id == user_id,
                    MemoryEntity.normalized_name == normalized_name,
                    MemoryEntity.entity_type == entity_type,
                )
            )
        )
        return result.scalar_one_or_none()

    async def add_entity_relationship(
        self,
        user_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
        confidence: float = 0.5,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a relationship between two entities."""
        session = await self._get_session()
        try:
            rel_id = str(uuid.uuid4())
            rel = MemoryRelationship(
                id=rel_id,
                user_id=user_id,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship_type=relationship_type,
                confidence=str(confidence),
                provenance=provenance or {},
            )
            session.add(rel)
            await session.commit()
            return rel_id
        finally:
            if self.db_session is None:
                await session.close()

    async def list_entities(self, user_id: str) -> List[MemoryEntity]:
        """List entities extracted for a researcher, scoped to the owner."""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(MemoryEntity)
                .where(MemoryEntity.user_id == user_id)
                .order_by(MemoryEntity.last_seen_at.desc())
            )
            return list(result.scalars().all())
        finally:
            if self.db_session is None:
                await session.close()

    async def list_relationships(self, user_id: str) -> List[MemoryRelationship]:
        """List entity relationships for a researcher, scoped to the owner."""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(MemoryRelationship)
                .where(MemoryRelationship.user_id == user_id)
                .order_by(MemoryRelationship.created_at.desc())
            )
            return list(result.scalars().all())
        finally:
            if self.db_session is None:
                await session.close()

    # ------------------------------------------------------------------
    # Memory retrieval (semantic + profile)
    # ------------------------------------------------------------------

    async def retrieve_relevant_memories(
        self,
        user_id: str,
        query: str,
        top_k: int = MAX_SEMANTIC_RESULTS,
        memory_types: Optional[List[str]] = None,
        trace_id: Optional[str] = None,
        max_chars: Optional[int] = None,
    ) -> MemorySearchResult:
        """Retrieve memories relevant to a query.

        Uses Vectorize for semantic search (if configured) with user_id
        filter for isolation, combined with direct profile memory lookup.
        """
        semantic_entries: List[MemoryEntry] = []

        # Try Vectorize semantic search
        if self.vectorize_service.is_configured():
            try:
                embedding_result = self.embedding_service.embed_text(query)
                vector_results = self.vectorize_service.query(
                    vector=embedding_result.vector,
                    top_k=top_k * 2,
                    filter=metadata_in_filter("user_id", [user_id]),
                )
                matches = vector_results.get("result", {}).get("matches", [])
                for match in matches[:top_k]:
                    metadata = match.get("metadata", {})
                    mem_id = metadata.get("memory_id")
                    if mem_id:
                        entry = await self._get_memory_entry_by_id(session=None, memory_id=mem_id, user_id=user_id)
                        if entry:
                            semantic_entries.append(entry)
            except Exception as exc:
                logger.warning("Vectorize semantic search failed: %s", exc)

        # Fallback: direct profile memory lookup by keyword matching
        if not semantic_entries:
            keyword_entries = await self._lookup_profile_memories_by_keyword(
                user_id, query, top_k, memory_types
            )
            semantic_entries.extend(keyword_entries)

        if memory_types:
            allowed = set(memory_types)
            semantic_entries = [
                entry for entry in semantic_entries if entry.memory_type in allowed
            ]

        unique_entries = self._dedupe_entries(semantic_entries)
        ranked = self._rank_entries(unique_entries, query)
        budgeted = self._apply_char_budget(
            ranked, max_chars if max_chars is not None else MAX_MEMORY_CONTEXT_CHARS
        )
        await self._touch_memories([entry.id for entry in budgeted])

        return MemorySearchResult(
            entries=budgeted[:top_k],
            total_found=len(ranked),
            query=query,
        )

    async def _touch_memories(self, memory_ids: List[str]) -> None:
        """Record last-used timestamps for the memories actually returned."""
        if not memory_ids:
            return
        session = await self._get_session()
        try:
            await session.execute(
                update(ResearcherMemory)
                .where(ResearcherMemory.id.in_(memory_ids))
                .values(last_used_at=datetime.now(timezone.utc))
            )
            await session.commit()
        except Exception:  # noqa: BLE001
            # Usage tracking must never break retrieval.
            logger.debug("memory.last_used_update_failed ids=%d", len(memory_ids))
        finally:
            if self.db_session is None:
                await session.close()

    async def build_memory_context(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        max_chars: int = MAX_MEMORY_CONTEXT_CHARS,
    ) -> Tuple[str, List[MemoryEntry]]:
        """Build the prompt-injectable memory block within a strict budget.

        Returns ("", []) when nothing relevant was retrieved — callers must not
        synthesise context in that case.
        """
        result = await self.retrieve_relevant_memories(
            user_id=user_id, query=query, top_k=top_k, max_chars=max_chars
        )
        if not result.entries:
            return "", []

        lines = [f"[Memory: {e.key}] {e.value}" for e in result.entries]
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars].rsplit("\n", 1)[0]
        return text, result.entries

    @staticmethod
    def _normalize_value(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    @staticmethod
    def _content_words(text: str) -> Set[str]:
        return {
            word.strip(".,!?;:\"'()[]{}").lower()
            for word in (text or "").split()
            if len(word.strip(".,!?;:\"'()[]{}")) > 3
        }

    def _relevance(self, query: str, entry: MemoryEntry) -> float:
        query_words = self._content_words(query)
        if not query_words:
            return 0.0
        entry_words = self._content_words(f"{entry.key} {entry.value}")
        return len(query_words & entry_words) / len(query_words)

    @staticmethod
    def _recency(entry: MemoryEntry) -> float:
        try:
            updated = datetime.fromisoformat(entry.updated_at)
        except (TypeError, ValueError):
            return 0.0
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_days = max(
            (datetime.now(timezone.utc) - updated).total_seconds(), 0.0
        ) / 86400.0
        return 0.5 ** (age_days / MEMORY_RECENCY_HALF_LIFE_DAYS)

    def _score(self, query: str, entry: MemoryEntry) -> float:
        score = (
            MEMORY_RELEVANCE_WEIGHT * self._relevance(query, entry)
            + MEMORY_CONFIDENCE_WEIGHT * max(0.0, min(entry.confidence, 1.0))
            + MEMORY_RECENCY_WEIGHT * self._recency(entry)
        )
        if (entry.provenance or {}).get("user_corrected"):
            score += MEMORY_CORRECTION_BONUS
        return score

    def _rank_entries(
        self, entries: List[MemoryEntry], query: str
    ) -> List[MemoryEntry]:
        return sorted(entries, key=lambda e: self._score(query, e), reverse=True)

    @staticmethod
    def _beats(candidate: MemoryEntry, incumbent: MemoryEntry) -> bool:
        """True when the candidate should replace an overlapping memory."""
        candidate_corrected = bool((candidate.provenance or {}).get("user_corrected"))
        incumbent_corrected = bool((incumbent.provenance or {}).get("user_corrected"))
        if candidate_corrected != incumbent_corrected:
            return candidate_corrected
        return candidate.confidence > incumbent.confidence

    def _dedupe_entries(self, entries: List[MemoryEntry]) -> List[MemoryEntry]:
        """Collapse duplicate and overlapping memories, keeping the stronger.

        Never drops a user-corrected value in favour of an inferred one.
        """
        kept: List[MemoryEntry] = []
        seen_ids: Set[str] = set()

        for entry in entries:
            if entry.id in seen_ids:
                continue
            seen_ids.add(entry.id)

            normalized = self._normalize_value(entry.value)
            if not normalized:
                continue

            duplicate_index = None
            for index, existing in enumerate(kept):
                if existing.key != entry.key:
                    continue
                other = self._normalize_value(existing.value)
                if normalized == other or normalized in other or other in normalized:
                    duplicate_index = index
                    break

            if duplicate_index is None:
                kept.append(entry)
            elif self._beats(entry, kept[duplicate_index]):
                kept[duplicate_index] = entry

        return kept

    @staticmethod
    def _apply_char_budget(
        entries: List[MemoryEntry], max_chars: int
    ) -> List[MemoryEntry]:
        """Keep whole memories only, stopping at the character budget."""
        kept: List[MemoryEntry] = []
        total = 0
        for entry in entries:
            cost = len(entry.key) + len(entry.value) + 24
            if kept and total + cost > max_chars:
                break
            kept.append(entry)
            total += cost
        return kept

    async def _get_memory_entry_by_id(
        self,
        session: Optional[AsyncSession],
        memory_id: str,
        user_id: str,
    ) -> Optional[MemoryEntry]:
        """Get a single memory entry by ID, scoped to user."""
        own_session = session is None
        if own_session:
            session = await self._get_session()
        try:
            result = await session.execute(
                select(ResearcherMemory).where(
                    and_(
                        ResearcherMemory.id == memory_id,
                        ResearcherMemory.user_id == user_id,
                        ResearcherMemory.is_archived == False,  # noqa: E712
                    )
                )
            )
            mem = result.scalar_one_or_none()
            if not mem:
                return None
            return self._mem_to_entry(mem)
        finally:
            if own_session and self.db_session is None:
                await session.close()

    async def _lookup_profile_memories_by_keyword(
        self,
        user_id: str,
        query: str,
        top_k: int,
        memory_types: Optional[List[str]] = None,
    ) -> List[MemoryEntry]:
        """Lookup profile memories by keyword matching (Vectorize fallback)."""
        session = await self._get_session()
        try:
            words = [w.lower() for w in query.split() if len(w) > 3]
            if not words:
                return []

            conditions = []
            for word in words:
                conditions.append(
                    ResearcherMemory.value.ilike(f"%{word}%")
                )
                conditions.append(ResearcherMemory.key.ilike(f"%{word}%"))

            if not conditions:
                return []

            filters = [
                ResearcherMemory.user_id == user_id,
                ResearcherMemory.is_archived == False,  # noqa: E712
                or_(*conditions),
            ]
            if memory_types:
                filters.append(ResearcherMemory.memory_type.in_(memory_types))

            result = await session.execute(
                select(ResearcherMemory)
                .where(and_(*filters))
                .limit(top_k)
            )
            mems = result.scalars().all()
            return [self._mem_to_entry(m) for m in mems]
        finally:
            if self.db_session is None:
                await session.close()

    # ------------------------------------------------------------------
    # Memory CRUD
    # ------------------------------------------------------------------

    async def get_memory(self, memory_id: str, user_id: str) -> Optional[MemoryEntry]:
        """Get a single memory by ID, scoped to owner."""
        session = await self._get_session()
        try:
            return await self._get_memory_entry_by_id(session, memory_id, user_id)
        finally:
            if self.db_session is None:
                await session.close()

    async def list_memories(
        self,
        user_id: str,
        memory_type: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        """List memories for a user, optionally filtered by type."""
        session = await self._get_session()
        try:
            conditions = [
                ResearcherMemory.user_id == user_id,
            ]
            if not include_archived:
                conditions.append(ResearcherMemory.is_archived == False)  # noqa: E712
            if memory_type:
                conditions.append(ResearcherMemory.memory_type == memory_type)

            result = await session.execute(
                select(ResearcherMemory)
                .where(and_(*conditions))
                .order_by(ResearcherMemory.updated_at.desc())
                .limit(limit)
            )
            mems = result.scalars().all()
            return [self._mem_to_entry(m) for m in mems]
        finally:
            if self.db_session is None:
                await session.close()

    async def update_memory(
        self,
        memory_id: str,
        user_id: str,
        value: Optional[str] = None,
        confidence: Optional[float] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[MemoryEntry]:
        """Update a memory entry (correction)."""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(ResearcherMemory).where(
                    and_(
                        ResearcherMemory.id == memory_id,
                        ResearcherMemory.user_id == user_id,
                        ResearcherMemory.is_archived == False,  # noqa: E712
                    )
                )
            )
            mem = result.scalar_one_or_none()
            if not mem:
                return None

            provenance = dict(mem.provenance or {})
            if value is not None:
                mem.value = value
                provenance["user_corrected"] = True
                provenance["corrected_at"] = datetime.now(timezone.utc).isoformat()
            if confidence is not None:
                mem.confidence = str(confidence)
                provenance["user_corrected"] = True
            if trace_id:
                provenance["last_corrected_trace_id"] = trace_id
                provenance["last_corrected_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
            if provenance != (mem.provenance or {}):
                mem.provenance = provenance
            mem.updated_at = datetime.now(timezone.utc)

            await session.commit()
            return self._mem_to_entry(mem)
        finally:
            if self.db_session is None:
                await session.close()

    async def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """Delete (soft archive) a memory entry."""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(ResearcherMemory).where(
                    and_(
                        ResearcherMemory.id == memory_id,
                        ResearcherMemory.user_id == user_id,
                    )
                )
            )
            mem = result.scalar_one_or_none()
            if not mem:
                return False

            mem.is_archived = True
            mem.archived_at = datetime.now(timezone.utc)
            await session.commit()
            return True
        finally:
            if self.db_session is None:
                await session.close()

    # ------------------------------------------------------------------
    # Memory lifecycle: expiration / archival
    # ------------------------------------------------------------------

    async def archive_stale_memories(
        self, user_id: Optional[str] = None
    ) -> int:
        """Archive memories that are stale (old + low confidence).

        Returns the number of memories archived.
        """
        session = await self._get_session()
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(
                days=MEMORY_STALE_DAYS
            )
            conditions = [
                ResearcherMemory.is_archived == False,  # noqa: E712
                ResearcherMemory.confidence <= MEMORY_LOW_CONFIDENCE_ARCHIVE,
                or_(
                    ResearcherMemory.updated_at < cutoff_date,
                    ResearcherMemory.expires_at
                    < datetime.now(timezone.utc),
                ),
            ]
            if user_id:
                conditions.append(ResearcherMemory.user_id == user_id)

            result = await session.execute(
                select(ResearcherMemory).where(and_(*conditions))
            )
            mems = result.scalars().all()

            for mem in mems:
                mem.is_archived = True
                mem.archived_at = datetime.now(timezone.utc)

            await session.commit()
            return len(mems)
        finally:
            if self.db_session is None:
                await session.close()

    # ------------------------------------------------------------------
    # Memory summarization (working memory -> profile)
    # ------------------------------------------------------------------

    async def summarize_working_memory_to_profile(
        self, user_id: str, trace_id: Optional[str] = None
    ) -> List[str]:
        """Summarize summarized working memory exchanges into profile memories.

        Extracts stable facts (interests, objectives, methodologies) from
        summarized exchanges and upserts them as profile memories.
        Returns list of created/updated memory keys.
        """
        session = await self._get_session()
        try:
            result = await session.execute(
                select(WorkingMemoryExchange)
                .where(
                    and_(
                        WorkingMemoryExchange.user_id == user_id,
                        WorkingMemoryExchange.is_summarized == True,  # noqa: E712
                    )
                )
                .order_by(WorkingMemoryExchange.created_at.desc())
            )
            exchanges = result.scalars().all()

            if not exchanges:
                return []

            # Combine all summarized content
            combined = "\n".join(
                f"{ex.exchange_type}: {ex.summary or ex.content}"
                for ex in exchanges
            )

            # Use DeepSeek to extract stable facts
            system_prompt = (
                "Extract stable research profile facts from the conversation "
                "history below. Return ONLY a JSON array of objects with keys: "
                "key, value, confidence (0.0-1.0). Keys should be short "
                "identifiers like 'research_interest', 'primary_methodology', "
                "preferred_department, etc. Do NOT extract credentials, "
                "passwords, or sensitive personal information. "
                "If no stable facts can be extracted, return an empty array."
            )
            user_prompt = f"Conversation history:\n{combined}\n\nReturn JSON array."

            try:
                response = complete_with_deepseek(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.1,
                    json_mode=True,
                )
            except ProviderUnavailableError:
                logger.warning("DeepSeek unavailable for memory summarization")
                return []

            try:
                facts = json.loads(response.content)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse memory summarization response")
                return []

            if not isinstance(facts, list):
                return []

            created_keys: List[str] = []
            for fact in facts:
                key = fact.get("key", "")
                val = fact.get("value", "")
                conf = float(fact.get("confidence", 0.5))
                if key and val:
                    mem_id = await self.upsert_profile_memory(
                        user_id=user_id,
                        key=key,
                        value=val,
                        confidence=conf,
                        source=MemorySource.EXTRACTED_FROM_CONVERSATION.value,
                        trace_id=trace_id,
                    )
                    created_keys.append(key)

            return created_keys
        finally:
            if self.db_session is None:
                await session.close()

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _mem_to_entry(self, mem: ResearcherMemory) -> MemoryEntry:
        """Convert ORM model to dataclass."""
        return MemoryEntry(
            id=mem.id,
            user_id=mem.user_id,
            memory_type=mem.memory_type.value
            if hasattr(mem.memory_type, "value")
            else str(mem.memory_type),
            source=mem.source.value
            if hasattr(mem.source, "value")
            else str(mem.source),
            key=mem.key,
            value=mem.value,
            confidence=float(mem.confidence),
            is_archived=mem.is_archived,
            source_document_id=mem.source_document_id,
            source_chunk_id=mem.source_chunk_id,
            provenance=mem.provenance or {},
            created_at=mem.created_at.isoformat() if mem.created_at else "",
            updated_at=mem.updated_at.isoformat() if mem.updated_at else "",
        )

    @staticmethod
    def _normalize_entity_name(name: str) -> str:
        """Normalize an entity name for deduplication."""
        return re.sub(r"\s+", " ", name.strip().lower())

    @staticmethod
    def _sanitize_sensitive(text: str) -> str:
        """Remove sensitive patterns from text before LLM processing."""
        sanitized = text
        for pattern in SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.I)
        return sanitized
