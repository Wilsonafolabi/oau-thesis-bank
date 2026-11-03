"""Topic discovery and trend analysis over the thesis repository.

Deterministic metadata aggregation only — no LLM calls. Everything is computed
from document records the actor is authorised to see, so the analysis can never
surface a private thesis title, department or year.

Access rules are the P2 rules, reused rather than re-implemented.
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
from ..db.models import AIDocument
from ..db.session import get_session_factory as AsyncSessionLocal
from ..retrieval.service import _build_access_conditions

logger = logging.getLogger("oau_ai.topics")

MAX_DOCUMENTS = 500
MAX_TOPICS = 25
MIN_TERM_LENGTH = 4

STOPWORDS = {
    "about", "above", "after", "again", "against", "along", "among", "analysis",
    "based", "because", "been", "before", "being", "between", "both", "case",
    "cases", "could", "during", "effect", "effects", "from", "into", "itself",
    "more", "most", "other", "over", "paper", "role", "such", "study", "than",
    "that", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "using", "very", "were", "what", "when", "where",
    "which", "while", "with", "within", "would", "your",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")


@dataclass
class TopicCount:
    name: str
    document_count: int
    thesis_ids: List[str] = field(default_factory=list)


@dataclass
class TrendPoint:
    year: Optional[int]
    document_count: int


@dataclass
class TopicAnalysis:
    total_documents: int
    analysed_documents: int
    topics: List[TopicCount]
    departments: List[TopicCount]
    faculties: List[TopicCount]
    years: List[TrendPoint]
    limitations: List[str]


class TopicService:
    """Aggregates topic, department, faculty and year signals."""

    def __init__(self, db_session: Optional[AsyncSession] = None) -> None:
        self.db_session = db_session

    async def _session(self):
        if self.db_session is not None:
            return self.db_session
        return AsyncSessionLocal()()

    async def _load_documents(
        self, actor: ActorContext, max_documents: int
    ) -> List[AIDocument]:
        session = await self._session()
        try:
            result = await session.execute(
                select(AIDocument)
                .where(_build_access_conditions(actor))
                .limit(max_documents)
            )
            return list(result.scalars().all())
        finally:
            if self.db_session is None:
                await session.close()

    @staticmethod
    def _keywords(text: str) -> List[str]:
        terms = []
        for raw in _TOKEN_RE.findall(text or ""):
            term = raw.strip("-'").lower()
            if len(term) >= MIN_TERM_LENGTH and term not in STOPWORDS:
                terms.append(term)
        return terms

    async def analyze(
        self,
        actor: ActorContext,
        max_documents: int = MAX_DOCUMENTS,
        max_topics: int = MAX_TOPICS,
    ) -> TopicAnalysis:
        """Return topic/department/faculty/year aggregates for the actor."""
        bounded = max(1, min(int(max_documents), MAX_DOCUMENTS))
        documents = await self._load_documents(actor, bounded)

        topic_docs: Dict[str, set] = defaultdict(set)
        department_docs: Dict[str, set] = defaultdict(set)
        faculty_docs: Dict[str, set] = defaultdict(set)
        year_counts: Counter = Counter()

        for document in documents:
            metadata = document.thesis_metadata or {}
            thesis_id = document.backend_thesis_id

            title = metadata.get("title") or ""
            for term in set(self._keywords(title)):
                topic_docs[term].add(thesis_id)

            department = (metadata.get("department") or "").strip()
            if department:
                department_docs[department].add(thesis_id)

            faculty = (metadata.get("faculty") or "").strip()
            if faculty:
                faculty_docs[faculty].add(thesis_id)

            year = metadata.get("year")
            if isinstance(year, int):
                year_counts[year] += 1
            elif isinstance(year, str) and year.strip().isdigit():
                year_counts[int(year.strip())] += 1

        topics = [
            TopicCount(name=name, document_count=count, thesis_ids=sorted(ids))
            for name, count, ids in self._rank(topic_docs, max_topics)
        ]
        departments = [
            TopicCount(name=name, document_count=count, thesis_ids=sorted(ids))
            for name, count, ids in self._rank(department_docs, max_topics)
        ]
        faculties = [
            TopicCount(name=name, document_count=count, thesis_ids=sorted(ids))
            for name, count, ids in self._rank(faculty_docs, max_topics)
        ]
        years = [
            TrendPoint(year=year, document_count=year_counts[year])
            for year in sorted(year_counts)
        ]

        limitations = []
        if not documents:
            limitations.append(
                "No accessible documents in the repository, so no topic "
                "analysis could be produced."
            )
        else:
            with_metadata = sum(
                1 for d in documents if (d.thesis_metadata or {}).get("department")
            )
            if with_metadata < len(documents):
                limitations.append(
                    f"{len(documents) - with_metadata} of {len(documents)} "
                    "documents carry no department metadata and are excluded "
                    "from that breakdown."
                )
            if not year_counts:
                limitations.append("No year metadata available for trend analysis.")

        return TopicAnalysis(
            total_documents=len(documents),
            analysed_documents=len(documents),
            topics=topics,
            departments=departments,
            faculties=faculties,
            years=years,
            limitations=limitations,
        )

    @staticmethod
    def _rank(
        buckets: Dict[str, set], limit: int
    ) -> List[tuple]:
        ordered = sorted(
            buckets.items(), key=lambda item: (-len(item[1]), item[0])
        )
        return [(name, len(ids), ids) for name, ids in ordered[:limit]]
