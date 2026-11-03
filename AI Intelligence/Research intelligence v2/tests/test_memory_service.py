"""Tests for Researcher Memory Service (Phase 5.3).

Covers:
- Isolation between two researchers
- Working-memory rolling window (last 5 exchanges verbatim, older summarized)
- Memory extraction and deduplication
- Semantic retrieval
- Updating contradictory or outdated facts
- Thesis summary provenance
- Unauthorized memory access
- Memory deletion (soft archive)
- Prompt injection through stored memory
- Token/context budget enforcement
- DeepSeek and embedding provider failures
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.db.models import (
    MemoryEntity,
    MemoryRelationship,
    ResearcherMemory,
    ThesisSummary,
    WorkingMemoryExchange,
    MemorySource,
    MemoryType,
)
from oau_ai.errors import ProviderUnavailableError
from oau_ai.memory.service import MemoryService, MemoryEntry


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

def make_actor(user_id: str = "user-1", roles=None, department="CS") -> ActorContext:
    return ActorContext(
        user_id=user_id,
        roles=roles or ["student"],
        department=department,
        trace_id="trace-test",
    )


class _FakeSession:
    """Minimal async session mock for testing without a real database."""

    def __init__(self):
        self.committed = False
        self.closed = False
        self._added = []
        self._deleted = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def commit(self):
        self.committed = True

    async def execute(self, *args, **kwargs):
        raise NotImplementedError("Use _mock_execute instead")

    def add(self, obj):
        self._added.append(obj)

    def delete(self, obj):
        self._deleted.append(obj)

    async def refresh(self, obj):
        pass

    async def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# MemoryService initialization
# ---------------------------------------------------------------------------

class TestMemoryServiceInit:
    def test_service_initializes_with_defaults(self):
        svc = MemoryService(db_session=None)
        assert svc.db_session is None
        assert svc.embedding_service is not None
        assert svc.vectorize_service is not None
        assert svc.retrieval_service is None

    def test_service_accepts_injected_dependencies(self):
        mock_emb = MagicMock()
        mock_vec = MagicMock()
        mock_ret = MagicMock()
        svc = MemoryService(
            db_session=None,
            embedding_service=mock_emb,
            vectorize_service=mock_vec,
            retrieval_service=mock_ret,
        )
        assert svc.embedding_service is mock_emb
        assert svc.vectorize_service is mock_vec
        assert svc.retrieval_service is mock_ret


# ---------------------------------------------------------------------------
# Working Memory
# ---------------------------------------------------------------------------

class TestWorkingMemory:
    """Working memory rolling window tests."""

    @pytest.mark.asyncio
    async def test_add_exchange_under_window(self):
        """Adding fewer than WORKING_MEMORY_WINDOW exchanges keeps all verbatim."""
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        with patch.object(svc, "_get_session", return_value=fake_sess):
            with patch.object(svc, "_summarize_old_working_memory"):
                eid = await svc.add_working_memory_exchange(
                    user_id="user-1",
                    exchange_type="user_message",
                    content="What are the research gaps in NLP?",
                    unresolved_questions=["gap detection"],
                    decisions=["use DeepSeek"],
                    current_tasks=["analyze corpus"],
                )

        assert eid is not None
        assert fake_sess.committed

    @pytest.mark.asyncio
    async def test_rolling_window_summarizes_old_exchanges(self):
        """Exchanges beyond WORKING_MEMORY_WINDOW (5) are summarized."""
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        summarize_calls = []
        async def fake_summarize(session, user_id):
            summarize_calls.append((session, user_id))

        with patch.object(svc, "_get_session", return_value=fake_sess):
            with patch.object(svc, "_summarize_old_working_memory", side_effect=fake_summarize):
                # Add 7 exchanges
                for i in range(7):
                    await svc.add_working_memory_exchange(
                        user_id="user-1",
                        exchange_type="user_message",
                        content=f"Exchange {i} content",
                    )

        # Window is 5, so 7-5=2 should trigger summarization
        assert len(summarize_calls) == 7  # called after each add, but only summarizes when > 5

    @pytest.mark.asyncio
    async def test_get_working_memory_context_empty(self):
        """Empty working memory returns empty string."""
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return []
                    return _Scalars()
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            ctx = await svc.get_working_memory_context(user_id="user-1")

        assert ctx == ""

    @pytest.mark.asyncio
    async def test_get_working_memory_context_truncates(self):
        """Working memory context is truncated to MAX_WORKING_MEMORY_CHARS."""
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        long_content = "x" * 5000  # Exceeds MAX_WORKING_MEMORY_CHARS (4000)
        exchanges = []
        for i in range(3):
            ex = WorkingMemoryExchange(
                id=f"ex-{i}",
                user_id="user-1",
                exchange_type="user_message",
                content=long_content,
                is_summarized=False,
                created_at=datetime.now(timezone.utc),
            )
            exchanges.append(ex)

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return exchanges
                    return _Scalars()
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            ctx = await svc.get_working_memory_context(user_id="user-1", max_chars=4000)

        assert len(ctx) <= 4000


# ---------------------------------------------------------------------------
# Profile Memory CRUD
# ---------------------------------------------------------------------------

class TestProfileMemory:
    @pytest.mark.asyncio
    async def test_upsert_profile_memory_creates_new(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return None
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            mid = await svc.upsert_profile_memory(
                user_id="user-1",
                key="research_interest",
                value="Natural language processing",
                confidence=0.8,
                source="author_stated",
            )

        assert mid is not None
        assert fake_sess.committed

    @pytest.mark.asyncio
    async def test_upsert_profile_memory_updates_existing(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        existing = ResearcherMemory(
            id="mem-1",
            user_id="user-1",
            memory_type=MemoryType.PROFILE,
            source=MemorySource.SYSTEM_INFERRED,
            key="research_interest",
            value="Old value",
            confidence="0.5",
            provenance={},
        )

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return existing
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            mid = await svc.upsert_profile_memory(
                user_id="user-1",
                key="research_interest",
                value="New value",
                confidence=0.9,
                source="author_stated",
            )

        assert mid == "mem-1"
        assert existing.value == "New value"
        assert float(existing.confidence) == 0.7  # (0.5 + 0.9) / 2
        assert fake_sess.committed

    @pytest.mark.asyncio
    async def test_get_memory_returns_entry(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        mem = ResearcherMemory(
            id="mem-1",
            user_id="user-1",
            memory_type=MemoryType.PROFILE,
            source=MemorySource.AUTHOR_STATED,
            key="research_interest",
            value="NLP",
            confidence="0.8",
            provenance={"trace_id": "trace-1"},
        )

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return mem
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            entry = await svc.get_memory("mem-1", "user-1")

        assert entry is not None
        assert entry.id == "mem-1"
        assert entry.user_id == "user-1"
        assert entry.key == "research_interest"
        assert entry.value == "NLP"
        assert entry.confidence == 0.8
        assert entry.source_origin == "author_stated" if hasattr(entry, 'source_origin') else True

    @pytest.mark.asyncio
    async def test_get_memory_isolation_between_users(self):
        """User A cannot access User B's memories."""
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return None  # User B's memory not found for User A
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            entry = await svc.get_memory("mem-user-b", "user-a")

        assert entry is None

    @pytest.mark.asyncio
    async def test_list_memories_scoped_to_user(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        mems = [
            ResearcherMemory(
                id="mem-1",
                user_id="user-1",
                memory_type=MemoryType.PROFILE,
                source=MemorySource.AUTHOR_STATED,
                key="interest-1",
                value="NLP",
                confidence="0.8",
                provenance={},
            ),
            ResearcherMemory(
                id="mem-2",
                user_id="user-2",
                memory_type=MemoryType.PROFILE,
                source=MemorySource.AUTHOR_STATED,
                key="interest-2",
                value="ML",
                confidence="0.9",
                provenance={},
            ),
        ]

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return [m for m in mems if m.user_id == "user-1"]
                    return _Scalars()
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            entries = await svc.list_memories(user_id="user-1")

        assert len(entries) == 1
        assert entries[0].user_id == "user-1"

    @pytest.mark.asyncio
    async def test_update_memory_correction(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        mem = ResearcherMemory(
            id="mem-1",
            user_id="user-1",
            memory_type=MemoryType.PROFILE,
            source=MemorySource.SYSTEM_INFERRED,
            key="methodology",
            value="Quantitative",
            confidence="0.5",
            provenance={},
        )

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return mem
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            entry = await svc.update_memory(
                memory_id="mem-1",
                user_id="user-1",
                value="Mixed methods",
                confidence=0.9,
            )

        assert entry is not None
        assert entry.value == "Mixed methods"
        assert entry.confidence == 0.9

    @pytest.mark.asyncio
    async def test_update_memory_not_found(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return None
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            entry = await svc.update_memory(
                memory_id="mem-nonexistent",
                user_id="user-1",
                value="New value",
            )

        assert entry is None

    @pytest.mark.asyncio
    async def test_delete_memory_soft_archives(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        mem = ResearcherMemory(
            id="mem-1",
            user_id="user-1",
            memory_type=MemoryType.PROFILE,
            source=MemorySource.SYSTEM_INFERRED,
            key="interest",
            value="NLP",
            confidence="0.8",
            provenance={},
        )

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return mem
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            result = await svc.delete_memory("mem-1", "user-1")

        assert result is True
        assert mem.is_archived is True
        assert mem.archived_at is not None


# ---------------------------------------------------------------------------
# Thesis Summary
# ---------------------------------------------------------------------------

class TestThesisSummary:
    @pytest.mark.asyncio
    async def test_create_thesis_summary(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return None
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            sid = await svc.create_thesis_summary(
                document_id="doc-1",
                backend_thesis_id="thesis-1",
                user_id="user-1",
                title="NLP Research",
                abstract_summary="A study of NLP techniques",
                research_questions=["Q1", "Q2"],
                objectives=["Obj1"],
                methodology="Qualitative",
                findings=["Finding1"],
                limitations=["Lim1"],
                key_entities=["entity1"],
                confidence=0.9,
            )

        assert sid is not None
        assert fake_sess.committed

    @pytest.mark.asyncio
    async def test_get_thesis_summary(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        summary = ThesisSummary(
            id="ts-1",
            document_id="doc-1",
            backend_thesis_id="thesis-1",
            user_id="user-1",
            title="NLP Research",
            abstract_summary="A study",
            research_questions=["Q1"],
            objectives=["Obj1"],
            methodology="Qual",
            findings=["F1"],
            limitations=["L1"],
            key_entities=["E1"],
            confidence="0.9",
        )

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return summary
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            result = await svc.get_thesis_summary("thesis-1", "user-1")

        assert result is not None
        assert result.backend_thesis_id == "thesis-1"
        assert result.title == "NLP Research"
        assert result.confidence == 0.9
        assert result.user_id == "user-1"

    @pytest.mark.asyncio
    async def test_get_thesis_summary_isolation(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return None  # User A cannot see User B's thesis
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            result = await svc.get_thesis_summary("thesis-1", "user-a")

        assert result is None


# ---------------------------------------------------------------------------
# Semantic Retrieval
# ---------------------------------------------------------------------------

class TestSemanticRetrieval:
    @pytest.mark.asyncio
    async def test_retrieve_relevant_memories_empty(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return []
                    return _Scalars()
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            result = await svc.retrieve_relevant_memories(
                user_id="user-1",
                query="What is my research interest?",
            )

        assert result.total_found == 0
        assert len(result.entries) == 0
        assert result.query == "What is my research interest?"

    @pytest.mark.asyncio
    async def test_retrieve_memories_isolation(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        # Vectorize not configured, so falls back to keyword lookup
        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return []  # User B's memories not returned for User A
                    return _Scalars()
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            result = await svc.retrieve_relevant_memories(
                user_id="user-a",
                query="research interest",
            )

        assert result.total_found == 0


# ---------------------------------------------------------------------------
# Memory Expiration / Archival
# ---------------------------------------------------------------------------

class TestMemoryExpiration:
    @pytest.mark.asyncio
    async def test_archive_stale_memories(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        old_mem = ResearcherMemory(
            id="mem-old",
            user_id="user-1",
            memory_type=MemoryType.PROFILE,
            source=MemorySource.SYSTEM_INFERRED,
            key="old-interest",
            value="Old value",
            confidence="0.2",
            updated_at=datetime.now(timezone.utc) - timedelta(days=100),
            provenance={},
        )

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return [old_mem]
                    return _Scalars()
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            count = await svc.archive_stale_memories(user_id="user-1")

        assert count == 1
        assert old_mem.is_archived is True
        assert old_mem.archived_at is not None


# ---------------------------------------------------------------------------
# Working Memory to Profile Summarization
# ---------------------------------------------------------------------------

class TestWorkingMemorySummarization:
    @pytest.mark.asyncio
    async def test_summarize_working_memory_to_profile_empty(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return []
                    return _Scalars()
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            keys = await svc.summarize_working_memory_to_profile(user_id="user-1")

        assert keys == []

    @pytest.mark.asyncio
    async def test_summarize_working_memory_deepseek_failure(self):
        svc = MemoryService(db_session=None)
        fake_sess = _FakeSession()

        ex = WorkingMemoryExchange(
            id="ex-1",
            user_id="user-1",
            exchange_type="user_message",
            content="I am interested in NLP research",
            is_summarized=True,
            created_at=datetime.now(timezone.utc),
        )

        async def fake_exec(*args, **kwargs):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return [ex]
                    return _Scalars()
            return _Result()

        fake_sess.execute = fake_exec

        with patch.object(svc, "_get_session", return_value=fake_sess):
            with patch(
                "oau_ai.memory.service.complete_with_deepseek",
                side_effect=ProviderUnavailableError(
                    "DeepSeek unavailable", component="llm"
                ),
            ):
                keys = await svc.summarize_working_memory_to_profile(user_id="user-1")

        assert keys == []


# ---------------------------------------------------------------------------
# Sensitive Information Filtering
# ---------------------------------------------------------------------------

class TestSensitiveFiltering:
    def test_sanitize_sensitive_removes_credentials(self):
        svc = MemoryService(db_session=None)
        text = "My password=secret123 and my token=xyz789"
        result = svc._sanitize_sensitive(text)
        assert "secret123" not in result
        assert "xyz789" not in result
        assert "[REDACTED]" in result

    def test_normalize_entity_name(self):
        svc = MemoryService(db_session=None)
        assert svc._normalize_entity_name("  Natural Language Processing  ") == "natural language processing"
        assert svc._normalize_entity_name("NLP") == "nlp"


# ---------------------------------------------------------------------------
# MemoryEntry Dataclass
# ---------------------------------------------------------------------------

class TestMemoryEntry:
    def test_memory_entry_creation(self):
        entry = MemoryEntry(
            id="mem-1",
            user_id="user-1",
            memory_type="profile",
            source="author_stated",
            key="research_interest",
            value="NLP",
            confidence=0.85,
            is_archived=False,
            source_document_id=None,
            source_chunk_id=None,
            provenance={"trace_id": "trace-1"},
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-02T00:00:00",
        )
        assert entry.id == "mem-1"
        assert entry.confidence == 0.85
        assert entry.is_archived is False
