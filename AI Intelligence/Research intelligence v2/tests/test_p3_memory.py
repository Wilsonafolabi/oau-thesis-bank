"""P3 regression tests — research memory and grounded thesis summaries.

Deterministic: database sessions, retrieval and the LLM provider are all
mocked. No network, no model downloads, no paid calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.db.models import MemorySource, MemoryType, ResearcherMemory
from oau_ai.errors import Phase3Error, ProviderUnavailableError
from oau_ai.memory.service import (
    MAX_MEMORY_CONTEXT_CHARS,
    SUMMARY_BATCH_CHARS,
    MemoryEntry,
    MemorySearchResult,
    MemoryService,
    ThesisSummaryData,
)


def _actor(user_id="user-1", roles=None):
    return ActorContext(
        user_id=user_id, roles=roles or ["student"], department="CS", trace_id="t-p3"
    )


def _entry(
    entry_id,
    key="research_interest",
    value="natural language processing",
    confidence=0.8,
    updated="2026-01-01T00:00:00+00:00",
    corrected=False,
    user_id="user-1",
    memory_type="profile",
):
    return MemoryEntry(
        id=entry_id,
        user_id=user_id,
        memory_type=memory_type,
        source="author_stated",
        key=key,
        value=value,
        confidence=confidence,
        is_archived=False,
        source_document_id=None,
        source_chunk_id=None,
        provenance={"user_corrected": True} if corrected else {},
        created_at=updated,
        updated_at=updated,
    )


class _RecordingSession:
    """Captures executed statements and returns no rows."""

    def __init__(self):
        self.queries = []
        self.committed = False

    async def execute(self, statement, *args, **kwargs):
        self.queries.append(str(statement))
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.all.return_value = []
        return result

    async def commit(self):
        self.committed = True

    async def close(self):
        return None

    @property
    def last_query(self):
        return self.queries[-1] if self.queries else ""


# --------------------------------------------------------------------------
# §2/§3 Selective retrieval: ranking, dedupe, budget, isolation
# --------------------------------------------------------------------------


def test_ranking_prefers_relevant_memory_over_unrelated():
    service = MemoryService(db_session=None)
    entries = [
        _entry("m1", "research_interest", "natural language processing"),
        _entry("m2", "hobby", "cooking jollof rice on weekends"),
    ]

    ranked = service._rank_entries(entries, "What is my research interest?")

    assert ranked[0].id == "m1"


def test_ranking_favours_user_corrected_memory():
    service = MemoryService(db_session=None)
    entries = [
        _entry("inferred", "methodology", "quantitative survey", confidence=0.9),
        _entry("corrected", "methodology", "mixed methods", confidence=0.4, corrected=True),
    ]

    ranked = service._rank_entries(entries, "methodology")

    assert ranked[0].id == "corrected"


def test_dedupe_collapses_overlapping_values_keeping_strongest():
    service = MemoryService(db_session=None)
    entries = [
        _entry("m1", "research_interest", "natural language processing", confidence=0.5),
        _entry(
            "m2",
            "research_interest",
            "natural language processing and computer vision",
            confidence=0.9,
        ),
    ]

    kept = service._dedupe_entries(entries)

    assert [e.id for e in kept] == ["m2"]


def test_dedupe_keeps_corrected_value_over_higher_confidence_duplicate():
    service = MemoryService(db_session=None)
    entries = [
        _entry("stale", "methodology", "mixed methods", confidence=0.95),
        _entry("fixed", "methodology", "mixed methods", confidence=0.3, corrected=True),
    ]

    kept = service._dedupe_entries(entries)

    assert [e.id for e in kept] == ["fixed"]


def test_dedupe_keeps_distinct_memories():
    service = MemoryService(db_session=None)
    entries = [
        _entry("m1", "research_interest", "natural language processing"),
        _entry("m2", "research_interest", "soil microbiology"),
    ]

    assert len(service._dedupe_entries(entries)) == 2


def test_char_budget_stops_before_exceeding_limit():
    service = MemoryService(db_session=None)
    entries = [_entry(f"m{i}", "k", "x" * 200) for i in range(10)]

    kept = service._apply_char_budget(entries, 500)

    # 1 + 200 + 24 = 225 per entry -> two fit, three would exceed 500.
    assert len(kept) == 2


def test_drop_empty_values():
    service = MemoryService(db_session=None)
    assert service._dedupe_entries([_entry("m1", "k", "   ")]) == []


@pytest.mark.asyncio
async def test_empty_memory_produces_no_context():
    service = MemoryService(db_session=None)
    service.retrieve_relevant_memories = AsyncMock(
        return_value=MemorySearchResult(entries=[], total_found=0, query="q")
    )

    text, entries = await service.build_memory_context("user-1", "q")

    assert text == ""
    assert entries == []


@pytest.mark.asyncio
async def test_memory_context_respects_budget():
    service = MemoryService(db_session=None)
    service.retrieve_relevant_memories = AsyncMock(
        return_value=MemorySearchResult(
            entries=[_entry(f"m{i}", "key", "value " * 60) for i in range(6)],
            total_found=6,
            query="q",
        )
    )

    text, _ = await service.build_memory_context("user-1", "q", max_chars=300)

    assert len(text) <= 300


@pytest.mark.asyncio
async def test_keyword_lookup_is_scoped_to_the_actor():
    session = _RecordingSession()
    service = MemoryService(db_session=session)

    await service.retrieve_relevant_memories("user-b", "research interest")

    assert "user_id" in session.last_query


@pytest.mark.asyncio
async def test_memory_types_filter_is_applied():
    session = _RecordingSession()
    service = MemoryService(db_session=session)

    await service.retrieve_relevant_memories(
        "user-1", "research interest", memory_types=["profile"]
    )

    assert "memory_type" in session.last_query


# --------------------------------------------------------------------------
# §5 Correction precedence
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correction_is_not_overwritten_by_inferred_memory():
    service = MemoryService(db_session=None)
    session = _RecordingSession()
    existing = ResearcherMemory(
        id="mem-1",
        user_id="user-1",
        memory_type=MemoryType.PROFILE,
        source=MemorySource.AUTHOR_STATED,
        key="methodology",
        value="mixed methods",
        confidence="0.4",
        provenance={"user_corrected": True},
    )

    async def fake_exec(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        return result

    session.execute = fake_exec

    with patch.object(service, "_get_session", return_value=session):
        await service.upsert_profile_memory(
            user_id="user-1",
            key="methodology",
            value="quantitative survey",
            confidence=0.9,
            source=MemorySource.EXTRACTED_FROM_CONVERSATION.value,
        )

    assert existing.value == "mixed methods"
    assert float(existing.confidence) == 0.4


@pytest.mark.asyncio
async def test_author_stated_value_may_replace_a_correction():
    service = MemoryService(db_session=None)
    session = _RecordingSession()
    existing = ResearcherMemory(
        id="mem-1",
        user_id="user-1",
        memory_type=MemoryType.PROFILE,
        source=MemorySource.AUTHOR_STATED,
        key="methodology",
        value="mixed methods",
        confidence="0.4",
        provenance={"user_corrected": True},
    )

    async def fake_exec(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        return result

    session.execute = fake_exec

    with patch.object(service, "_get_session", return_value=session):
        await service.upsert_profile_memory(
            user_id="user-1",
            key="methodology",
            value="ethnography",
            confidence=0.8,
            source=MemorySource.AUTHOR_STATED.value,
        )

    assert existing.value == "ethnography"


@pytest.mark.asyncio
async def test_update_marks_memory_as_user_corrected():
    service = MemoryService(db_session=None)
    session = _RecordingSession()
    existing = ResearcherMemory(
        id="mem-1",
        user_id="user-1",
        memory_type=MemoryType.PROFILE,
        source=MemorySource.SYSTEM_INFERRED,
        key="methodology",
        value="old",
        confidence="0.5",
        provenance={},
    )

    async def fake_exec(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        return result

    session.execute = fake_exec

    with patch.object(service, "_get_session", return_value=session):
        entry = await service.update_memory("mem-1", "user-1", value="mixed methods")

    assert entry is not None
    assert entry.provenance.get("user_corrected") is True


# --------------------------------------------------------------------------
# §4 Grounded thesis summaries
# --------------------------------------------------------------------------


def _chunk(text):
    chunk = MagicMock()
    chunk.text = text
    return chunk


def _chunks_session(chunks):
    session = _RecordingSession()

    async def fake_exec(*args, **kwargs):
        result = MagicMock()
        result.scalars.return_value.all.return_value = chunks
        result.scalar_one_or_none.return_value = None
        return result

    session.execute = fake_exec
    return session


def _access(document_id="doc-1", can_view=True, title="Soil and Crops"):
    access = MagicMock()
    access.document_id = document_id
    access.can_view = can_view
    access.title = title
    return access


def _summary_payload(**overrides):
    payload = {
        "research_problem": "Low crop yields in the region",
        "objectives": ["Evaluate rotation effects"],
        "research_questions": ["Does rotation raise nitrogen?"],
        "methodology": "Field trial over two seasons",
        "dataset": "240 farm plots in Oyo State",
        "findings": ["Rotation raised nitrogen by 12%"],
        "contributions": ["A local rotation guideline"],
        "limitations": ["Single region"],
        "future_work": ["Multi-region replication"],
        "key_entities": ["crop rotation", "nitrogen"],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _summary_service(chunks, access=None, chunks_session=None):
    service = MemoryService(db_session=None)
    retrieval = MagicMock()
    retrieval.check_document_access = AsyncMock(
        return_value=access or _access()
    )
    service.retrieval_service = retrieval
    service.create_thesis_summary = AsyncMock()
    service.get_thesis_summary = AsyncMock(
        return_value=ThesisSummaryData(
            document_id="doc-1",
            backend_thesis_id="thesis-1",
            user_id="user-1",
            title="Soil and Crops",
            abstract_summary="Research problem: Low crop yields",
            research_questions=["Does rotation raise nitrogen?"],
            objectives=["Evaluate rotation effects"],
            methodology="Field trial",
            findings=["Rotation raised nitrogen by 12%"],
            limitations=["Single region"],
            key_entities=["crop rotation"],
            confidence=0.8,
            missing_sections=[],
        )
    )
    session = chunks_session or _chunks_session(chunks)
    service._get_session = AsyncMock(return_value=session)
    return service


@pytest.mark.asyncio
async def test_generated_summary_is_grounded_in_source_chunks():
    service = _summary_service([_chunk("Rotation raised nitrogen by 12%.")])

    with patch(
        "oau_ai.memory.service.complete_with_deepseek",
        return_value=MagicMock(content=_summary_payload()),
    ):
        await service.generate_thesis_summary(_actor(), "thesis-1")

    kwargs = service.create_thesis_summary.call_args.kwargs
    assert kwargs["findings"] == [
        "Rotation raised nitrogen by 12%",
        "Contribution: A local rotation guideline",
    ]
    assert kwargs["limitations"] == [
        "Single region",
        "Future work: Multi-region replication",
    ]
    assert "Dataset / study population: 240 farm plots" in kwargs["abstract_summary"]


@pytest.mark.asyncio
async def test_missing_sections_are_reported_not_invented():
    service = _summary_service([_chunk("Only a problem statement exists.")])
    payload = _summary_payload(
        objectives=[],
        research_questions=[],
        methodology=None,
        dataset=None,
        findings=[],
        contributions=[],
        limitations=[],
        future_work=[],
        key_entities=[],
    )

    with patch(
        "oau_ai.memory.service.complete_with_deepseek",
        return_value=MagicMock(content=payload),
    ):
        await service.generate_thesis_summary(_actor(), "thesis-1")

    kwargs = service.create_thesis_summary.call_args.kwargs
    assert kwargs["findings"] == []
    assert kwargs["limitations"] == []
    assert kwargs["objectives"] == []
    # Coverage-based confidence, not a model-reported number.
    assert kwargs["confidence"] == round(1 / 9, 2)


@pytest.mark.asyncio
async def test_provider_failure_does_not_store_a_summary():
    service = _summary_service([_chunk("Some text")])

    with patch(
        "oau_ai.memory.service.complete_with_deepseek",
        side_effect=ProviderUnavailableError(
            message="deepseek down", component="deepseek"
        ),
    ):
        with pytest.raises(ProviderUnavailableError):
            await service.generate_thesis_summary(_actor(), "thesis-1")

    service.create_thesis_summary.assert_not_called()


@pytest.mark.asyncio
async def test_no_chunks_raises_source_unavailable():
    service = _summary_service([])

    with pytest.raises(Phase3Error) as exc:
        await service.generate_thesis_summary(_actor(), "thesis-1")

    assert exc.value.code == "summary_source_unavailable"
    service.create_thesis_summary.assert_not_called()


@pytest.mark.asyncio
async def test_access_denied_before_reading_any_text():
    service = _summary_service(
        [_chunk("private thesis text")], access=_access(can_view=False)
    )

    with patch("oau_ai.memory.service.complete_with_deepseek") as llm:
        with pytest.raises(Phase3Error) as exc:
            await service.generate_thesis_summary(_actor("user-b"), "thesis-1")

    assert exc.value.code == "access_denied"
    llm.assert_not_called()
    service.create_thesis_summary.assert_not_called()


@pytest.mark.asyncio
async def test_long_document_is_digested_in_batches():
    long_text = "x" * (SUMMARY_BATCH_CHARS * 2 + 100)
    service = _summary_service([_chunk(long_text)])
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append(messages[-1]["content"])
        if len(calls) <= 2:
            return MagicMock(content="digest")
        return MagicMock(content=_summary_payload())

    with patch("oau_ai.memory.service.complete_with_deepseek", side_effect=fake_complete):
        await service.generate_thesis_summary(_actor(), "thesis-1")

    assert len(calls) == 4  # three batch digests + one final extraction
    assert len(calls[-1]) < len(long_text)


@pytest.mark.asyncio
async def test_invalid_json_never_becomes_a_summary():
    service = _summary_service([_chunk("text")])

    with patch(
        "oau_ai.memory.service.complete_with_deepseek",
        return_value=MagicMock(content="not json at all"),
    ):
        with pytest.raises(Phase3Error) as exc:
            await service.generate_thesis_summary(_actor(), "thesis-1")

    assert exc.value.code == "summary_parse_failed"
    service.create_thesis_summary.assert_not_called()


def test_stored_summary_reports_missing_sections():
    service = MemoryService(db_session=None)
    summary = MagicMock()
    summary.abstract_summary = "Research problem: Low yields"
    summary.objectives = []
    summary.research_questions = []
    summary.methodology = None
    summary.findings = ["Rotation raised nitrogen"]
    summary.limitations = []
    summary.key_entities = []

    missing = service._derive_missing_sections(summary)

    assert "research_problem" not in missing
    assert "findings" not in missing
    assert "objectives" in missing
    assert "methodology" in missing
    assert "future_work" in missing


def test_stored_summary_recovers_labelled_sections():
    service = MemoryService(db_session=None)
    summary = MagicMock()
    summary.abstract_summary = (
        "Research problem: Low yields\n\nDataset / study population: 240 plots"
    )
    summary.objectives = ["obj"]
    summary.research_questions = ["rq"]
    summary.methodology = "field trial"
    summary.findings = ["finding", "Contribution: guideline"]
    summary.limitations = ["limit", "Future work: multi-region"]
    summary.key_entities = ["rotation"]

    sections = service._sections_from_stored(summary)

    assert sections["research_problem"] == "Low yields"
    assert sections["dataset"] == "240 plots"
    assert sections["contributions"] == ["guideline"]
    assert sections["future_work"] == ["multi-region"]
    assert service._derive_missing_sections(summary) == []
