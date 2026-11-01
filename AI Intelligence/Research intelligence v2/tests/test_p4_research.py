"""P4 regression tests — topic analysis, gap consolidation, recommendations.

Deterministic: database sessions, retrieval and providers are mocked.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.recommendations.service import RecommendationService
from oau_ai.research_gap.service import (
    SOURCE_AUTHOR_LIMITATION,
    SOURCE_SYSTEM_INFERRED,
    GAP_TYPE_METHODOLOGICAL,
    GAP_TYPE_TOPIC,
    ResearchGap,
    ResearchGapCitation,
    ResearchGapService,
)
from oau_ai.retrieval.service import RetrievedChunk
from oau_ai.topics.service import TopicService


def _actor(user_id="user-1", roles=None):
    return ActorContext(
        user_id=user_id, roles=roles or ["student"], department="CS", trace_id="t-p4"
    )


def _doc(thesis_id, title=None, department=None, faculty=None, year=None):
    document = MagicMock()
    document.backend_thesis_id = str(thesis_id)
    metadata = {}
    if title is not None:
        metadata["title"] = title
    if department is not None:
        metadata["department"] = department
    if faculty is not None:
        metadata["faculty"] = faculty
    if year is not None:
        metadata["year"] = year
    document.thesis_metadata = metadata
    return document


class _DocSession:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    async def execute(self, statement, *args, **kwargs):
        self.queries.append(str(statement))
        result = MagicMock()
        result.scalars.return_value.all.return_value = self.documents
        return result

    async def close(self):
        return None


# --------------------------------------------------------------------------
# §3 Topic discovery and trends
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topics_ranked_by_document_frequency():
    session = _DocSession(
        [
            _doc(1, title="Crop rotation and soil nitrogen"),
            _doc(2, title="Crop rotation in smallholder farming"),
            _doc(3, title="Machine learning for credit scoring"),
        ]
    )
    service = TopicService(db_session=session)

    analysis = await service.analyze(_actor())

    names = [topic.name for topic in analysis.topics]
    assert names[0] in {"crop", "rotation"}
    crop = next(t for t in analysis.topics if t.name == "rotation")
    assert crop.document_count == 2
    assert crop.thesis_ids == ["1", "2"]


@pytest.mark.asyncio
async def test_department_and_faculty_distribution():
    session = _DocSession(
        [
            _doc(1, title="A", department="Computer Science", faculty="Technology"),
            _doc(2, title="B", department="Computer Science", faculty="Technology"),
            _doc(3, title="C", department="Agriculture", faculty="Science"),
        ]
    )
    service = TopicService(db_session=session)

    analysis = await service.analyze(_actor())

    departments = {d.name: d.document_count for d in analysis.departments}
    faculties = {f.name: f.document_count for f in analysis.faculties}
    assert departments["Computer Science"] == 2
    assert faculties["Technology"] == 2


@pytest.mark.asyncio
async def test_year_trend_aggregation():
    session = _DocSession(
        [
            _doc(1, title="A", year=2021),
            _doc(2, title="B", year=2021),
            _doc(3, title="C", year=2023),
        ]
    )
    service = TopicService(db_session=session)

    analysis = await service.analyze(_actor())

    years = {point.year: point.document_count for point in analysis.years}
    assert years == {2021: 2, 2023: 1}
    assert [point.year for point in analysis.years] == [2021, 2023]


@pytest.mark.asyncio
async def test_empty_repository_is_reported_honestly():
    service = TopicService(db_session=_DocSession([]))

    analysis = await service.analyze(_actor())

    assert analysis.total_documents == 0
    assert analysis.topics == []
    assert any("No accessible documents" in note for note in analysis.limitations)


@pytest.mark.asyncio
async def test_missing_metadata_is_disclosed():
    session = _DocSession(
        [
            _doc(1, title="A", department="CS", year=2020),
            _doc(2, title="B"),
        ]
    )
    service = TopicService(db_session=session)

    analysis = await service.analyze(_actor())

    assert any("no department metadata" in note for note in analysis.limitations)


@pytest.mark.asyncio
async def test_analysis_query_applies_access_conditions():
    session = _DocSession([])
    service = TopicService(db_session=session)

    await service.analyze(_actor(user_id="user-9"))

    assert "access_level" in session.queries[0] or "backend_user_id" in session.queries[0]


# --------------------------------------------------------------------------
# §2 Gap consolidation
# --------------------------------------------------------------------------


def _citation(chunk_id, thesis_id="1"):
    return ResearchGapCitation(
        chunk_id=chunk_id,
        document_id=f"doc-{thesis_id}",
        backend_thesis_id=thesis_id,
        text_snippet="snippet",
        page_number=3,
        section=None,
        relevance_score=0.9,
    )


def _gap(gap_type, description, origin=SOURCE_SYSTEM_INFERRED, chunk_id="c1", confidence=0.7):
    return ResearchGap(
        gap_type=gap_type,
        description=description,
        supporting_evidence=description,
        source_thesis_references=["1"],
        page_numbers=[3],
        chunk_citations=[_citation(chunk_id)],
        source_origin=origin,
        explanation="explanation",
        suggested_research_direction="direction",
        confidence=confidence,
    )


def test_duplicate_gaps_are_consolidated():
    service = ResearchGapService.__new__(ResearchGapService)
    gaps = [
        _gap(GAP_TYPE_TOPIC, "Underexplored crop rotation effects on soil nitrogen", chunk_id="c1"),
        _gap(GAP_TYPE_TOPIC, "Underexplored crop rotation effects on soil nitrogen", chunk_id="c2"),
    ]

    merged = service._consolidate_gaps(gaps)

    assert len(merged) == 1
    assert {c.chunk_id for c in merged[0].chunk_citations} == {"c1", "c2"}


def test_consolidation_keeps_author_stated_origin_and_top_confidence():
    service = ResearchGapService.__new__(ResearchGapService)
    gaps = [
        _gap(GAP_TYPE_METHODOLOGICAL, "Limited longitudinal methodology in farming studies", confidence=0.4),
        _gap(
            GAP_TYPE_METHODOLOGICAL,
            "Limited longitudinal methodology in farming studies",
            origin=SOURCE_AUTHOR_LIMITATION,
            chunk_id="c9",
            confidence=0.9,
        ),
    ]

    merged = service._consolidate_gaps(gaps)

    assert len(merged) == 1
    assert merged[0].source_origin == SOURCE_AUTHOR_LIMITATION
    assert merged[0].confidence == 0.9
    assert {c.chunk_id for c in merged[0].chunk_citations} == {"c1", "c9"}


def test_distinct_gaps_are_not_merged():
    service = ResearchGapService.__new__(ResearchGapService)
    gaps = [
        _gap(GAP_TYPE_TOPIC, "Underexplored crop rotation effects on soil nitrogen"),
        _gap(GAP_TYPE_METHODOLOGICAL, "Limited longitudinal methodology in farming studies"),
        _gap(GAP_TYPE_TOPIC, "Satellite imagery rarely used for yield prediction"),
    ]

    assert len(service._consolidate_gaps(gaps)) == 3


# --------------------------------------------------------------------------
# §4 Recommendations
# --------------------------------------------------------------------------


def _chunk(chunk_id, thesis_id="1", text="crop rotation improves soil nitrogen", score=0.5):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{thesis_id}",
        backend_thesis_id=str(thesis_id),
        text=text,
        page_number=1,
        section=None,
        chunk_index=0,
        access_level="public",
        provenance={"source_file": f"thesis-{thesis_id}"},
        fused_score=score,
    )


def _service(chunks, memory_text=""):
    retrieval = MagicMock()
    retrieval.hybrid_retrieve = AsyncMock(return_value=chunks)
    retrieval.check_document_access = AsyncMock(return_value=MagicMock(can_view=True, title="Seed"))
    vectorize = MagicMock()
    vectorize.is_configured = MagicMock(return_value=False)
    memory = MagicMock()
    memory.build_memory_context = AsyncMock(return_value=(memory_text, []))
    return RecommendationService(
        retrieval_service=retrieval,
        embedding_service=MagicMock(),
        vectorize_service=vectorize,
        memory_service=memory,
    )


@pytest.mark.asyncio
async def test_recommendation_groups_evidence_by_thesis():
    service = _service([_chunk("c1", "1"), _chunk("c2", "1"), _chunk("c3", "2", score=0.3)])

    result = await service.recommend(_actor(), query="crop rotation soil nitrogen")

    assert result.insufficient_evidence is False
    assert [r.backend_thesis_id for r in result.recommendations] == ["1", "2"]
    assert len(result.recommendations[0].evidence) == 2


@pytest.mark.asyncio
async def test_recommendation_orders_by_score_then_support():
    service = _service(
        [_chunk("c1", "1", score=0.2), _chunk("c2", "2", score=0.9)]
    )

    result = await service.recommend(_actor(), query="soil nitrogen")

    assert result.recommendations[0].backend_thesis_id == "2"


@pytest.mark.asyncio
async def test_explanation_cites_shared_terms():
    service = _service([_chunk("c1", "1", text="crop rotation improves soil nitrogen")])

    result = await service.recommend(_actor(), query="crop rotation nitrogen")

    explanation = result.recommendations[0].explanation
    assert "rotation" in explanation or "crop" in explanation
    assert "Supported by 1 retrieved passage" in explanation


@pytest.mark.asyncio
async def test_evidence_strength_is_bounded():
    service = _service([_chunk(f"c{i}", "1", score=0.5) for i in range(5)])

    result = await service.recommend(_actor(), query="crop rotation")

    strength = result.recommendations[0].evidence_strength
    assert 0.0 <= strength <= 1.0


@pytest.mark.asyncio
async def test_no_context_abstains():
    service = _service([])

    result = await service.recommend(_actor())

    assert result.insufficient_evidence is True
    assert result.recommendations == []
    assert result.context_source == "none"


@pytest.mark.asyncio
async def test_no_evidence_abstains_and_warns_about_repository_scope():
    service = _service([])

    result = await service.recommend(_actor(), query="quantum computing")

    assert result.insufficient_evidence is True
    assert any("does not mean the topic is unstudied" in note for note in result.limitations)


@pytest.mark.asyncio
async def test_memory_context_used_when_no_query():
    service = _service([_chunk("c1", "1")], memory_text="[Memory: research_interest] soil science")

    result = await service.recommend(_actor())

    assert result.context_source == "memory"
    service.memory_service.build_memory_context.assert_awaited_once()
    # Identity always comes from the actor context.
    _, kwargs = service.memory_service.build_memory_context.call_args
    assert kwargs["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_recommendations_are_limited_to_top_k():
    service = _service([_chunk(f"c{i}", str(i), score=0.5) for i in range(1, 8)])

    result = await service.recommend(_actor(), query="soil", top_k=3)

    assert len(result.recommendations) == 3


@pytest.mark.asyncio
async def test_recommendation_limitations_disclaim_quality():
    service = _service([_chunk("c1", "1")])

    result = await service.recommend(_actor(), query="soil")

    assert any("quality" in note for note in result.recommendations[0].limitations)
    assert any("novelty" in note for note in result.limitations)
