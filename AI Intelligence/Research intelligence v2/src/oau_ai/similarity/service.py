"""Text similarity detection and plagiarism assessment.

Two distinct layers:

1. ``SimilarityService`` — finds passages of a submitted text that overlap
   repository documents the actor may access. Lexical shingle containment is
   always computed; semantic (dense) comparison is optional and only used when
   the existing embedding/Vectorize infrastructure is configured.

2. ``PlagiarismAssessmentService`` — interprets those matches. It never issues a
   verdict: every result is an assessment with its supporting evidence, and a
   similarity score is never presented as proof of plagiarism.

Access control is the P2 rule set, applied in SQL before any chunk text is read.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.middleware import ActorContext
from ..db.models import AIDocument, AIChunk
from ..db.session import get_session_factory as AsyncSessionLocal
from ..errors import Phase3Error
from ..retrieval.service import RetrievalService, _build_access_conditions

logger = logging.getLogger("oau_ai.similarity")

SHINGLE_SIZE = 5
PASSAGE_WORDS = 200
MAX_TEXT_CHARS = 100_000
MAX_PASSAGES = 200
MAX_CHUNKS = 1500
MAX_MATCHES = 20

EXACT_THRESHOLD = 0.95
NEAR_EXACT_THRESHOLD = 0.60

ATTRIBUTION_PRESENT = "attribution_present"
REVIEW_REQUIRED = "review_required"
NO_SIGNIFICANT_OVERLAP = "no_significant_overlap"

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_QUOTE_RE = re.compile(r"[\"“”«»]")
_CITATION_RE = re.compile(
    r"(\(\s*[A-Z][A-Za-z\-']+(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z\-']+))?,?\s*\d{4}[a-z]?\s*\))"
    r"|(\[\d{1,3}\])"
)

DISCLAIMER = (
    "Similarity and overlap are indicators for human review. They are not a "
    "finding of plagiarism and must not be used as an automated disciplinary "
    "decision."
)


@dataclass
class SimilarityMatch:
    match_type: str  # exact | near_exact | partial | semantic
    score: float
    document_id: str
    backend_thesis_id: str
    title: Optional[str]
    chunk_id: str
    page_number: Optional[int]
    source_excerpt: str
    submitted_excerpt: str


@dataclass
class SimilarityResult:
    input_mode: str
    passages_scanned: int
    chunks_scanned: int
    matches: List[SimilarityMatch]
    exact_matches: List[SimilarityMatch] = field(default_factory=list)
    semantic_matches: List[SimilarityMatch] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)


@dataclass
class PassageAssessment:
    assessment: str
    reason: str
    quoted: bool
    cited: bool
    submitted_excerpt: str
    matches: List[SimilarityMatch]


@dataclass
class PlagiarismAssessment:
    status: str
    passages: List[PassageAssessment]
    matched_source_count: int
    limitations: List[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _words(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


def shingles(words: List[str], size: int = SHINGLE_SIZE) -> set:
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def split_passages(text: str, words_per_passage: int = PASSAGE_WORDS) -> List[str]:
    tokens = _normalise(text).split()
    if not tokens:
        return []
    passages = []
    for start in range(0, len(tokens), words_per_passage):
        passages.append(" ".join(tokens[start : start + words_per_passage]))
        if len(passages) >= MAX_PASSAGES:
            break
    return passages


class SimilarityService:
    """Finds overlapping passages between a submission and the repository."""

    def __init__(
        self,
        db_session: Optional[AsyncSession] = None,
        embedding_service=None,
        vectorize_service=None,
        enable_semantic: bool = True,
        retrieval_service: Optional[RetrievalService] = None,
    ) -> None:
        self.db_session = db_session
        self.embedding_service = embedding_service
        self.vectorize_service = vectorize_service
        self.enable_semantic = enable_semantic
        self.retrieval_service = retrieval_service

    async def _session(self):
        if self.db_session is not None:
            return self.db_session
        return AsyncSessionLocal()()

    async def _load_chunks(self, actor: ActorContext) -> List[tuple]:
        session = await self._session()
        try:
            result = await session.execute(
                select(AIChunk, AIDocument)
                .join(AIDocument, AIChunk.document_id == AIDocument.id)
                .where(_build_access_conditions(actor))
                .limit(MAX_CHUNKS)
            )
            return list(result.all())
        finally:
            if self.db_session is None:
                await session.close()

    async def compare_text(
        self,
        actor: ActorContext,
        text: str,
        min_score: float = 0.25,
        max_matches: int = MAX_MATCHES,
        exclude_document_ids: Optional[List[str]] = None,
    ) -> SimilarityResult:
        """Compare submitted text against accessible repository chunks."""
        if text is None or not text.strip():
            raise Phase3Error(
                code="empty_text",
                message="No text was supplied for comparison.",
                component="similarity_service",
                retryable=False,
            )
        if len(text) > MAX_TEXT_CHARS:
            raise Phase3Error(
                code="text_too_large",
                message=f"Text exceeds the {MAX_TEXT_CHARS} character limit.",
                component="similarity_service",
                retryable=False,
            )

        threshold = max(0.0, min(float(min_score), 1.0))
        passages = split_passages(text)
        if not passages:
            raise Phase3Error(
                code="empty_text",
                message="The submitted text contains no comparable content.",
                component="similarity_service",
                retryable=False,
            )

        excluded = set(exclude_document_ids or [])
        rows = [
            (chunk, document)
            for chunk, document in await self._load_chunks(actor)
            if document.id not in excluded
        ]

        postings: Dict[str, List[int]] = defaultdict(list)
        for index, (chunk, _document) in enumerate(rows):
            for shingle in shingles(_words(chunk.text)):
                postings[shingle].append(index)

        matches: List[SimilarityMatch] = []
        for passage in passages:
            passage_shingles = shingles(_words(passage))
            if not passage_shingles:
                continue
            hits: Counter = Counter()
            for shingle in passage_shingles:
                for index in postings.get(shingle, ()):
                    hits[index] += 1
            for index, hit_count in hits.items():
                containment = hit_count / len(passage_shingles)
                if containment < threshold:
                    continue
                chunk, document = rows[index]
                matches.append(
                    self._build_match(
                        containment, chunk, document, passage
                    )
                )

        matches = self._dedupe(matches)

        semantic: List[SimilarityMatch] = []
        limitations: List[str] = []
        if self.enable_semantic:
            semantic, limitations = await self._semantic_matches(
                actor, passages[:5], threshold, excluded
            )
            matches.extend(semantic)

        matches.sort(key=lambda m: m.score, reverse=True)
        capped = matches[: max(1, min(int(max_matches), MAX_MATCHES))]

        if not rows:
            limitations.append(
                "No accessible repository documents were available to compare "
                "against."
            )

        return SimilarityResult(
            input_mode="text",
            passages_scanned=len(passages),
            chunks_scanned=len(rows),
            matches=capped,
            exact_matches=[m for m in capped if m.match_type in ("exact", "near_exact")],
            semantic_matches=[m for m in capped if m.match_type == "semantic"],
            limitations=limitations,
        )

    def _build_match(self, score, chunk, document, passage) -> SimilarityMatch:
        if score >= EXACT_THRESHOLD:
            match_type = "exact"
        elif score >= NEAR_EXACT_THRESHOLD:
            match_type = "near_exact"
        else:
            match_type = "partial"
        return SimilarityMatch(
            match_type=match_type,
            score=round(float(score), 4),
            document_id=document.id,
            backend_thesis_id=document.backend_thesis_id,
            title=(document.thesis_metadata or {}).get("title"),
            chunk_id=chunk.id,
            page_number=None,
            source_excerpt=(chunk.text or "")[:300],
            submitted_excerpt=passage[:300],
        )

    @staticmethod
    def _dedupe(matches: List[SimilarityMatch]) -> List[SimilarityMatch]:
        """Keep the strongest match per (document, chunk, submission excerpt)."""
        best: Dict[tuple, SimilarityMatch] = {}
        for match in matches:
            key = (match.document_id, match.chunk_id, match.submitted_excerpt[:120])
            current = best.get(key)
            if current is None or match.score > current.score:
                best[key] = match
        return list(best.values())

    async def _semantic_matches(
        self, actor, passages, threshold, excluded
    ) -> tuple:
        """Optional dense comparison; degrades with an explicit limitation."""
        if not self.embedding_service or not self.vectorize_service:
            return [], [
                "Semantic comparison is not configured; results are lexical "
                "(exact / near-exact overlap) only."
            ]
        try:
            if not self.vectorize_service.is_configured():
                return [], [
                    "Semantic comparison unavailable (vector index not "
                    "configured); results are lexical only."
                ]
        except Exception:  # noqa: BLE001
            return [], ["Semantic comparison unavailable; results are lexical only."]

        hits: Dict[str, tuple] = {}
        try:
            for passage in passages:
                embedding = self.embedding_service.embed_text(passage)
                response = self.vectorize_service.query(
                    vector=embedding.vector, top_k=5
                )
                for hit in response.get("result", {}).get("matches", []):
                    score = float(hit.get("score", 0.0))
                    if score < threshold:
                        continue
                    metadata = hit.get("metadata", {})
                    chunk_id = metadata.get("chunk_id")
                    if not chunk_id:
                        continue
                    if metadata.get("document_id") in excluded:
                        continue
                    current = hits.get(chunk_id)
                    if current is None or score > current[0]:
                        hits[chunk_id] = (score, passage)
        except Exception as exc:  # noqa: BLE001
            logger.warning("similarity.semantic_failed: %s", exc)
            return [], ["Semantic comparison failed; results are lexical only."]

        if not hits:
            return [], []

        # Vectorize metadata is only a hint: every hit is re-resolved against
        # the database with the actor's access rules, exactly as in P2.
        retrieval = self.retrieval_service or RetrievalService(self.db_session)
        resolved, unresolved = await retrieval.resolve_authorized_chunks(
            list(hits), actor
        )
        if unresolved:
            logger.info("similarity.semantic_pruned unresolved=%d", len(unresolved))

        matches: List[SimilarityMatch] = []
        for chunk_id, (score, passage) in hits.items():
            chunk = resolved.get(chunk_id)
            if chunk is None:
                continue
            matches.append(
                SimilarityMatch(
                    match_type="semantic",
                    score=round(score, 4),
                    document_id=chunk.document_id,
                    backend_thesis_id=chunk.backend_thesis_id,
                    title=(chunk.provenance or {}).get("source_file"),
                    chunk_id=chunk.chunk_id,
                    page_number=chunk.page_number,
                    source_excerpt=(chunk.text or "")[:300],
                    submitted_excerpt=passage[:300],
                )
            )
        return matches, []


class PlagiarismAssessmentService:
    """Interprets similarity evidence. Never issues a verdict."""

    def __init__(self, similarity_service: Optional[SimilarityService] = None) -> None:
        self.similarity_service = similarity_service or SimilarityService()

    async def assess(
        self,
        actor: ActorContext,
        text: str,
        min_score: float = 0.25,
        exclude_document_ids: Optional[List[str]] = None,
    ) -> PlagiarismAssessment:
        result = await self.similarity_service.compare_text(
            actor,
            text,
            min_score=min_score,
            exclude_document_ids=exclude_document_ids,
        )

        if not result.matches:
            return PlagiarismAssessment(
                status=NO_SIGNIFICANT_OVERLAP,
                passages=[],
                matched_source_count=0,
                limitations=result.limitations,
            )

        by_passage: Dict[str, List[SimilarityMatch]] = defaultdict(list)
        for match in result.matches:
            by_passage[match.submitted_excerpt].append(match)

        assessments: List[PassageAssessment] = []
        for excerpt, matches in by_passage.items():
            quoted, cited = self._attribution_signals(text, excerpt)
            attributions = quoted or cited

            if attributions:
                status = ATTRIBUTION_PRESENT
                reason = (
                    "Overlapping text is quoted or carries an in-text citation, "
                    "so it is attributed rather than presented as original."
                )
            else:
                status = REVIEW_REQUIRED
                reason = (
                    f"{len(matches)} source passage(s) overlap this text with no "
                    "quotation or citation detected nearby. A human should check "
                    "whether attribution is missing."
                )

            assessments.append(
                PassageAssessment(
                    assessment=status,
                    reason=reason,
                    quoted=quoted,
                    cited=cited,
                    submitted_excerpt=excerpt,
                    matches=matches,
                )
            )

        overall = (
            ATTRIBUTION_PRESENT
            if all(item.assessment == ATTRIBUTION_PRESENT for item in assessments)
            else REVIEW_REQUIRED
        )

        limitations = list(result.limitations)
        limitations.append(
            "Only repository documents the requester can access were compared; "
            "external sources and the open web were not searched."
        )

        return PlagiarismAssessment(
            status=overall,
            passages=assessments,
            matched_source_count=len({m.document_id for m in result.matches}),
            limitations=limitations,
        )

    @staticmethod
    def _attribution_signals(text: str, excerpt: str) -> tuple:
        """Detect quotation marks and in-text citations near the excerpt."""
        needle = _normalise(excerpt)[:120]
        haystack = _normalise(text)
        position = haystack.find(needle)
        window = haystack[max(0, position - 200) : position + len(needle) + 200] if position >= 0 else haystack[:400]
        quoted = bool(_QUOTE_RE.search(window))
        cited = bool(_CITATION_RE.search(window))
        return quoted, cited
