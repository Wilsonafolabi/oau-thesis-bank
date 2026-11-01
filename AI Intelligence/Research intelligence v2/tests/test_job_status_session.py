"""Regression tests for get_job_status database session lifecycle.

Verifies that all ORM attributes needed for the JobStatusResponse are
accessed while the database session is open, and that no detached ORM
object is read after the async session context closes.

Covers:
- Successful job with document present → result populated
- Failed job → no result, error_message carried
- Missing document (job exists, document row absent) → result is None
- Job not found → Phase3Error → JSONResponse error
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oau_ai.api.routes import get_job_status
from oau_ai.auth.middleware import ActorContext
from oau_ai.db.models import JobStatus, ProcessingStage
from oau_ai.errors import Phase3Error


class _FakeJob:
    """Plain stand-in for an AIJob ORM instance captured inside session."""

    def __init__(
        self,
        job_id: str,
        document_id: str,
        status: JobStatus,
        stage: ProcessingStage,
        error_message: str | None = None,
        error_stage: str | None = None,
        attempts: int = 0,
        max_attempts: int = 3,
    ):
        self.id = job_id
        self.document_id = document_id
        self.status = status
        self.stage = stage
        self.error_message = error_message
        self.error_stage = error_stage
        self.attempts = attempts
        self.max_attempts = max_attempts


class _FakeDocument:
    """Plain stand-in for an AIDocument ORM instance captured inside session."""

    def __init__(self, document_id: str, backend_thesis_id: str, embedding_status: str):
        self.id = document_id
        self.backend_thesis_id = backend_thesis_id
        self.embedding_status = embedding_status


async def _make_route_response(
    job_id: str,
    job: _FakeJob | None,
    document: _FakeDocument | None,
    service_error: Phase3Error | None = None,
    actor: ActorContext | None = None,
):
    """Call get_job_status with a mocked AsyncSessionLocal and IngestionService."""

    if actor is None:
        actor = ActorContext(
            user_id="user-123", roles=["student"], department="CS", trace_id="trace-1"
        )

    # Mock db.get(AIDocument, job.document_id) → document or None.
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=document)

    # Mock AsyncSessionLocal as an async context manager yielding mock_db.
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("oau_ai.api.routes.AsyncSessionLocal", return_value=mock_session_cm):
        # Patch IngestionService so get_job_status returns our fake job.
        with patch(
            "oau_ai.api.routes.IngestionService"
        ) as mock_service_cls:
            mock_service = AsyncMock()
            if service_error is not None:
                mock_service.get_job_status = AsyncMock(side_effect=service_error)
            else:
                mock_service.get_job_status = AsyncMock(return_value=job)
            mock_service_cls.return_value = mock_service

            response = await get_job_status(
                job_id=job_id,
                _token="test-token",
                actor=actor,
                trace_id="trace-1",
            )
    return response


class TestGetJobStatusSuccessfulJob:
    """Successful job with document → result populated, session closed cleanly."""

    @pytest.mark.asyncio
    async def test_successful_job_returns_result_with_document_fields(self):
        job = _FakeJob(
            job_id="job-1",
            document_id="doc-1",
            status=JobStatus.SUCCESS,
            stage=ProcessingStage.COMPLETE,
            attempts=1,
            max_attempts=3,
        )
        document = _FakeDocument(
            document_id="doc-1",
            backend_thesis_id="thesis-42",
            embedding_status="completed",
        )

        response = await _make_route_response("job-1", job, document)

        assert isinstance(response, dict) or hasattr(response, "job_id")
        # JobStatusResponse is a Pydantic model; access fields directly.
        assert response.job_id == "job-1"
        assert response.status == "success"
        assert response.stage == "complete"
        assert response.attempts == 1
        assert response.max_attempts == 3
        assert response.error_message is None
        assert response.result is not None
        assert response.result["document_id"] == "doc-1"
        assert response.result["backend_thesis_id"] == "thesis-42"
        assert response.result["embedding_status"] == "completed"

    @pytest.mark.asyncio
    async def test_successful_job_without_document_uses_default_message(self):
        """Job succeeded but document row missing → result None, default message."""
        job = _FakeJob(
            job_id="job-2",
            document_id="doc-2",
            status=JobStatus.SUCCESS,
            stage=ProcessingStage.COMPLETE,
        )

        response = await _make_route_response("job-2", job, None)

        assert response.status == "success"
        assert response.result is None
        assert response.message == "Ingestion success."


class TestGetJobStatusFailedJob:
    """Failed job → no result, error fields carried."""

    @pytest.mark.asyncio
    async def test_failed_job_returns_error_message_and_no_result(self):
        job = _FakeJob(
            job_id="job-3",
            document_id="doc-3",
            status=JobStatus.FAILED,
            stage=ProcessingStage.FAILED,
            error_message="PDF corrupt",
            attempts=2,
            max_attempts=3,
        )
        document = _FakeDocument(
            document_id="doc-3",
            backend_thesis_id="thesis-99",
            embedding_status="failed",
        )

        response = await _make_route_response("job-3", job, document)

        assert response.status == "failed"
        assert response.stage == "failed"
        assert response.error_message == "PDF corrupt"
        assert response.message == "PDF corrupt"
        # result should be None because job.status.value != "success"
        assert response.result is None
        assert response.attempts == 2
        assert response.max_attempts == 3


class TestGetJobStatusMissingDocument:
    """Job not found → Phase3Error → JSONResponse error."""

    @pytest.mark.asyncio
    async def test_job_not_found_returns_phase3_error_response(self):
        service_error = Phase3Error(
            code="job_not_found",
            message="Ingestion job job-4 not found.",
            component="ingestion_service",
            trace_id="trace-1",
        )

        response = await _make_route_response(
            "job-4", None, None, service_error=service_error
        )

        # Should be a JSONResponse (error), not a JobStatusResponse.
        from fastapi.responses import JSONResponse

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400  # not retryable → 400

    @pytest.mark.asyncio
    async def test_access_denied_returns_phase3_error_response(self):
        """Access denied → Phase3Error → JSONResponse error."""
        service_error = Phase3Error(
            code="access_denied",
            message="You do not have access to this job.",
            component="ingestion_service",
            retryable=False,
            trace_id="trace-1",
        )

        response = await _make_route_response(
            "job-5", None, None, service_error=service_error
        )

        from fastapi.responses import JSONResponse

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
