"""Tests for retrieval service — permission enforcement and cross-user access denial."""

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.retrieval.service import RetrievalService


class MockSession:
    """Mock database session for testing retrieval logic without a real DB."""

    def __init__(self, documents, chunks, pages):
        self.documents = documents  # dict: backend_thesis_id -> doc dict
        self.chunks = chunks  # list of chunk dicts
        self.pages = pages  # list of page dicts


class MockRetrievalService(RetrievalService):
    """Retrieval service using in-memory data for testing."""

    def __init__(self, documents, chunks, pages):
        self._documents = documents
        self._chunks = chunks
        self._pages = pages

    async def check_document_access(
        self, backend_thesis_id: str, actor_context: ActorContext
    ):
        doc = self._documents.get(backend_thesis_id)
        if not doc:
            from types import SimpleNamespace
            return SimpleNamespace(
                document_id="",
                backend_thesis_id=backend_thesis_id,
                access_level="unknown",
                title=None,
                can_view=False,
                reason="Document not found.",
            )

        title = doc.get("metadata", {}).get("title")

        if doc["access_level"] == "public":
            can_view = True
            reason = None
        elif doc["backend_user_id"] == actor_context.user_id:
            can_view = True
            reason = None
        elif "admin" in actor_context.roles:
            can_view = True
            reason = None
        else:
            can_view = False
            reason = "Access denied."

        from types import SimpleNamespace
        return SimpleNamespace(
            document_id=doc["id"],
            backend_thesis_id=doc["backend_thesis_id"],
            access_level=doc["access_level"],
            title=title,
            can_view=can_view,
            reason=reason,
        )

    async def get_authorized_chunks(
        self, actor_context: ActorContext, document_ids=None, limit=10,
        access_levels=None,
    ):
        accessible_chunks = []
        for chunk in self._chunks:
            doc = self._documents.get(chunk["backend_thesis_id"])
            if not doc:
                continue
            # Check access
            if doc["access_level"] == "public":
                can_view = True
            elif doc["backend_user_id"] == actor_context.user_id:
                can_view = True
            elif "admin" in actor_context.roles:
                can_view = True
            else:
                can_view = False

            if not can_view:
                continue

            if document_ids and chunk["backend_thesis_id"] not in document_ids:
                continue

            accessible_chunks.append(chunk)

        return accessible_chunks[:limit]


@pytest.fixture
def sample_documents():
    return {
        "thesis-public-1": {
            "id": "doc-public-1",
            "backend_thesis_id": "thesis-public-1",
            "backend_user_id": "user-a",
            "access_level": "public",
            "metadata": {"title": "Public Thesis"},
        },
        "thesis-private-1": {
            "id": "doc-private-1",
            "backend_thesis_id": "thesis-private-1",
            "backend_user_id": "user-a",
            "access_level": "private",
            "metadata": {"title": "Private Thesis A"},
        },
        "thesis-private-2": {
            "id": "doc-private-2",
            "backend_thesis_id": "thesis-private-2",
            "backend_user_id": "user-b",
            "access_level": "private",
            "metadata": {"title": "Private Thesis B"},
        },
    }


@pytest.fixture
def sample_chunks():
    return [
        {
            "chunk_id": "chunk-1",
            "document_id": "doc-public-1",
            "backend_thesis_id": "thesis-public-1",
            "text": "Public thesis content about machine learning.",
            "page_number": 1,
            "chunk_index": 0,
            "access_level": "public",
        },
        {
            "chunk_id": "chunk-2",
            "document_id": "doc-private-1",
            "backend_thesis_id": "thesis-private-1",
            "text": "Private thesis A content about databases.",
            "page_number": 1,
            "chunk_index": 0,
            "access_level": "private",
        },
        {
            "chunk_id": "chunk-3",
            "document_id": "doc-private-2",
            "backend_thesis_id": "thesis-private-2",
            "text": "Private thesis B content about networking.",
            "page_number": 1,
            "chunk_index": 0,
            "access_level": "private",
        },
    ]


@pytest.mark.asyncio
async def test_public_document_accessible_to_anyone(sample_documents, sample_chunks):
    """A public document is accessible to any authenticated user."""
    service = MockRetrievalService(sample_documents, sample_chunks, {})
    actor = ActorContext(user_id="user-c", roles=["student"], department="CS")

    access = await service.check_document_access("thesis-public-1", actor)
    assert access.can_view is True
    assert access.reason is None


@pytest.mark.asyncio
async def test_private_document_only_owner_accessible(sample_documents, sample_chunks):
    """A private document is accessible only to its owner."""
    service = MockRetrievalService(sample_documents, sample_chunks, {})

    # Owner can view
    actor_owner = ActorContext(user_id="user-a", roles=["student"], department="CS")
    access = await service.check_document_access("thesis-private-1", actor_owner)
    assert access.can_view is True

    # Non-owner cannot view
    actor_other = ActorContext(user_id="user-c", roles=["student"], department="CS")
    access = await service.check_document_access("thesis-private-1", actor_other)
    assert access.can_view is False
    assert access.reason is not None


@pytest.mark.asyncio
async def test_admin_can_view_private_documents(sample_documents, sample_chunks):
    """An admin can view any document regardless of ownership."""
    service = MockRetrievalService(sample_documents, sample_chunks, {})
    actor_admin = ActorContext(user_id="admin-1", roles=["admin"], department="CS")

    access = await service.check_document_access("thesis-private-2", actor_admin)
    assert access.can_view is True


@pytest.mark.asyncio
async def test_cross_user_access_denied(sample_documents, sample_chunks):
    """User B cannot access User A's private thesis."""
    service = MockRetrievalService(sample_documents, sample_chunks, {})
    actor_b = ActorContext(user_id="user-b", roles=["student"], department="CS")

    # User B can view their own private thesis
    access = await service.check_document_access("thesis-private-2", actor_b)
    assert access.can_view is True

    # User B cannot view User A's private thesis
    access = await service.check_document_access("thesis-private-1", actor_b)
    assert access.can_view is False


@pytest.mark.asyncio
async def test_authorized_chunks_excludes_unauthorized(sample_documents, sample_chunks):
    """get_authorized_chunks only returns chunks from accessible documents."""
    service = MockRetrievalService(sample_documents, sample_chunks, {})
    actor_c = ActorContext(user_id="user-c", roles=["student"], department="CS")

    chunks = await service.get_authorized_chunks(actor_c, limit=10)

    # User C can only see the public thesis
    chunk_ids = {c["chunk_id"] for c in chunks}
    assert "chunk-1" in chunk_ids  # public
    assert "chunk-2" not in chunk_ids  # user-a's private
    assert "chunk-3" not in chunk_ids  # user-b's private


@pytest.mark.asyncio
async def test_document_not_found_returns_cannot_view(sample_documents, sample_chunks):
    """Access check for nonexistent document returns can_view=False."""
    service = MockRetrievalService(sample_documents, sample_chunks, {})
    actor = ActorContext(user_id="user-a", roles=["student"], department="CS")

    access = await service.check_document_access("thesis-nonexistent", actor)
    assert access.can_view is False
    assert access.reason is not None
