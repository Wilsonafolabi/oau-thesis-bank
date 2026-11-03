"""Tests for retrieval security: unauthorized document exclusion.

Unit tests use mocked database sessions; no live services.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.db.models import AIDocument, AIChunk
from oau_ai.errors import Phase3Error
from oau_ai.retrieval.service import DocumentAccess, RetrievalService


@pytest.mark.asyncio
async def test_check_document_access_public_document():
    """Public document is accessible to anyone."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_document = MagicMock()
    mock_document.access_level = "public"
    mock_document.backend_user_id = "other-user"
    mock_document.id = "doc-1"
    mock_document.backend_thesis_id = "thesis-1"
    mock_document.thesis_metadata = {"title": "Public Thesis"}
    mock_document.created_at = None
    mock_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_result

    service = RetrievalService(db_session=mock_session)
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    access = await service.check_document_access("thesis-1", actor)

    assert access.can_view is True
    assert access.access_level == "public"


@pytest.mark.asyncio
async def test_check_document_access_owner():
    """Document owner can view their own private document."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_document = MagicMock()
    mock_document.access_level = "private"
    mock_document.backend_user_id = "user-1"
    mock_document.id = "doc-1"
    mock_document.backend_thesis_id = "thesis-1"
    mock_document.thesis_metadata = {"title": "Private Thesis"}
    mock_document.created_at = None
    mock_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_result

    service = RetrievalService(db_session=mock_session)
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    access = await service.check_document_access("thesis-1", actor)

    assert access.can_view is True


@pytest.mark.asyncio
async def test_check_document_access_cross_user_denied():
    """Non-owner non-admin cannot view another user's private document."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_document = MagicMock()
    mock_document.access_level = "private"
    mock_document.backend_user_id = "user-a"
    mock_document.id = "doc-1"
    mock_document.backend_thesis_id = "thesis-1"
    mock_document.thesis_metadata = {"title": "User A's Private Thesis"}
    mock_document.created_at = None
    mock_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_result

    service = RetrievalService(db_session=mock_session)
    actor = ActorContext(user_id="user-b", roles=["student"], department="CS")

    access = await service.check_document_access("thesis-1", actor)

    assert access.can_view is False
    assert "denied" in (access.reason or "").lower()


@pytest.mark.asyncio
async def test_check_document_access_admin_can_view():
    """Admin can view any document regardless of access level."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_document = MagicMock()
    mock_document.access_level = "private"
    mock_document.backend_user_id = "user-a"
    mock_document.id = "doc-1"
    mock_document.backend_thesis_id = "thesis-1"
    mock_document.thesis_metadata = {"title": "Private Thesis"}
    mock_document.created_at = None
    mock_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_result

    service = RetrievalService(db_session=mock_session)
    actor = ActorContext(user_id="user-b", roles=["admin"], department="CS")

    access = await service.check_document_access("thesis-1", actor)

    assert access.can_view is True


@pytest.mark.asyncio
async def test_get_chunk_by_id_denies_unauthorized():
    """get_chunk_by_id returns None for unauthorized chunks."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = None  # No chunk found (or access denied)
    mock_session.execute.return_value = mock_result

    service = RetrievalService(db_session=mock_session)
    actor = ActorContext(user_id="user-b", roles=["student"], department="CS")

    result = await service.get_chunk_by_id("chunk-1", actor)

    assert result is None


@pytest.mark.asyncio
async def test_verify_access_before_retrieval_raises_when_none_accessible():
    """verify_access_before_retrieval raises Phase3Error when no documents are accessible."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    service = RetrievalService(db_session=mock_session)
    actor = ActorContext(user_id="user-b", roles=["student"], department="CS")

    # All documents denied
    async def mock_check_access(thesis_id, actor_ctx):
        return DocumentAccess(
            document_id="",
            backend_thesis_id=thesis_id,
            access_level="private",
            title=None,
            can_view=False,
            reason="denied",
        )

    service.check_document_access = mock_check_access

    with pytest.raises(Phase3Error) as exc_info:
        await service.verify_access_before_retrieval(actor, ["thesis-a", "thesis-b"])

    assert exc_info.value.code == "no_accessible_documents"
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_get_authorized_chunks_excludes_unauthorized_documents():
    """get_authorized_chunks SQL query applies access conditions."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.execute.return_value = mock_result

    service = RetrievalService(db_session=mock_session)
    actor = ActorContext(user_id="user-1", roles=["student"], department="CS")

    results = await service.get_authorized_chunks(
        actor, document_ids=["doc-1", "doc-2"], limit=10
    )

    assert results == []
    # Verify execute was called with access-filtering query
    call_args = mock_session.execute.call_args
    assert call_args is not None
    query_str = str(call_args[0][0])
    # Should reference access_level or backend_user_id (access conditions)
    assert "access_level" in query_str or "backend_user_id" in query_str

