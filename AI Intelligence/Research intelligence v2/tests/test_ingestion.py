"""Tests for ingestion service — persistence and state transitions."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from oau_ai.auth.middleware import ActorContext
from oau_ai.db.models import (
    AIDocument,
    AIJob,
    AIPage,
    AIChunk,
    JobStatus,
    ProcessingStage,
)
from oau_ai.ingestion.service import IngestionService


@pytest.mark.asyncio
async def test_ingestion_service_create_document_and_job():
    """Creating a document and job persists them in the DB session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    actor = ActorContext(
        user_id="user-123",
        roles=["student"],
        department="CS",
        trace_id="trace-abc",
    )

    # Create a real temp file so Path.read_bytes works
    import tempfile
    from pathlib import Path as _Path
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 fake pdf content")
        tmp_path = f.name
    try:
        # Configure mock: no existing document
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute.return_value = mock_result

        with patch("pathlib.Path.unlink"), patch("pathlib.Path.read_bytes", return_value=b"fake content"):
            service = IngestionService(db_session=mock_db)
            document, job = await service.create_document_and_job(
                actor_context=actor,
                file_path=tmp_path,
                filename="test.pdf",
                backend_thesis_id="thesis-123",
                access_level="private",
            )

        assert document.backend_thesis_id == "thesis-123"
        assert document.backend_user_id == "user-123"
        assert document.access_level == "private"
        assert document.embedding_status == "pending"

        assert job.document_id == document.id
        assert job.status == JobStatus.PENDING
        assert job.stage == ProcessingStage.EXTRACTION

        # Verify add was called for both document and job
        assert mock_db.add.call_count >= 2
        mock_db.commit.assert_called()
    finally:
        _Path(tmp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_ingestion_service_duplicate_document():
    """Creating a document with duplicate backend_thesis_id raises error."""
    mock_db = AsyncMock()
    existing = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = existing

    actor = ActorContext(
        user_id="user-123",
        roles=["student"],
        department="CS",
        trace_id="trace-abc",
    )

    import tempfile
    from pathlib import Path as _Path
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 fake pdf content")
        tmp_path = f.name
    try:
        # Configure mock: existing document found (duplicate)
        existing_doc = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing_doc)
        mock_db.execute.return_value = mock_result

        service = IngestionService(db_session=mock_db)

        with pytest.raises(Exception) as exc_info:
            await service.create_document_and_job(
                actor_context=actor,
                file_path=tmp_path,
                filename="test.pdf",
                backend_thesis_id="thesis-duplicate",
                access_level="private",
            )

        assert "already exists" in str(exc_info.value).lower()
    finally:
        _Path(tmp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_ingestion_service_access_denied_on_process():
    """Processing a job for a document the actor doesn't own raises access denied."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get = AsyncMock()

    # Mock a document owned by someone else
    mock_document = MagicMock()
    mock_document.backend_user_id = "other-user"
    mock_document.id = "doc-1"
    mock_document.backend_thesis_id = "thesis-1"
    mock_document.object_key = "/tmp/test.pdf"
    mock_document.thesis_metadata = {"title": "Test"}
    mock_db.get.return_value = mock_document

    actor = ActorContext(
        user_id="user-123",
        roles=["student"],
        department="CS",
        trace_id="trace-abc",
    )

    mock_job = MagicMock()
    mock_job.id = "job-1"
    mock_job.document_id = "doc-1"
    mock_job.status = JobStatus.PENDING
    mock_job.stage = ProcessingStage.EXTRACTION
    mock_job.attempts = 0
    mock_job.max_attempts = 3

    # Override get to return job first, then document
    call_count = [0]
    async def mock_get(model, id_val):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_job
        return mock_document
    mock_db.get = mock_get

    service = IngestionService(db_session=mock_db)

    with pytest.raises(Exception) as exc_info:
        await service.process_job("job-1", actor)

    assert "access" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ingestion_job_never_marks_success_on_failure():
    """When processing fails, job status is FAILED, never SUCCESS."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get = AsyncMock()

    mock_job = MagicMock()
    mock_job.id = "job-1"
    mock_job.document_id = "doc-1"
    mock_job.status = JobStatus.PENDING
    mock_job.stage = ProcessingStage.EXTRACTION
    mock_job.attempts = 0
    mock_job.max_attempts = 3

    mock_document = MagicMock()
    mock_document.backend_user_id = "user-123"
    mock_document.id = "doc-1"
    mock_document.backend_thesis_id = "thesis-1"
    mock_document.object_key = "/tmp/test.pdf"
    mock_document.thesis_metadata = {"title": "Test"}
    mock_document.embedding_status = "pending"

    call_count = [0]
    async def mock_get(model, id_val):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_job
        return mock_document
    mock_db.get = mock_get

    actor = ActorContext(
        user_id="user-123",
        roles=["student"],
        department="CS",
        trace_id="trace-abc",
    )

    service = IngestionService(db_session=mock_db)

    # Make extraction fail
    with patch.object(
        service, "_extract_pages", side_effect=Exception("PDF corrupt")
    ):
        try:
            await service.process_job("job-1", actor)
        except Exception:
            pass

    # Job should be FAILED, not SUCCESS
    assert mock_job.status == JobStatus.FAILED
    assert mock_job.stage == ProcessingStage.FAILED
    assert mock_job.error_message is not None


@pytest.mark.asyncio
async def test_ingestion_get_job_status_access_control():
    """get_job_status enforces access control."""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock()

    mock_job = MagicMock()
    mock_job.id = "job-1"
    mock_job.document_id = "doc-1"

    mock_document = MagicMock()
    mock_document.backend_user_id = "other-user"
    mock_document.id = "doc-1"

    call_count = [0]
    async def mock_get(model, id_val):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_job
        return mock_document
    mock_db.get = mock_get

    actor = ActorContext(
        user_id="user-123",
        roles=["student"],
        department="CS",
        trace_id="trace-abc",
    )

    service = IngestionService(db_session=mock_db)

    with pytest.raises(Exception) as exc_info:
        await service.get_job_status("job-1", actor)

    assert "access" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ingestion_get_job_status_owner_can_view():
    """Document owner can view their own job status."""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock()

    mock_job = MagicMock()
    mock_job.id = "job-1"
    mock_job.document_id = "doc-1"

    mock_document = MagicMock()
    mock_document.backend_user_id = "user-123"
    mock_document.id = "doc-1"

    call_count = [0]
    async def mock_get(model, id_val):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_job
        return mock_document
    mock_db.get = mock_get

    actor = ActorContext(
        user_id="user-123",
        roles=["student"],
        department="CS",
        trace_id="trace-abc",
    )

    service = IngestionService(db_session=mock_db)
    job = await service.get_job_status("job-1", actor)
    assert job.id == "job-1"
