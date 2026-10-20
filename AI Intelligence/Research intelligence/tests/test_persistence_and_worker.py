import pytest, json, uuid
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from db.models import AIJob, JobStatus, AIDocument, AIChunk
from worker.main import process_job
from api.routes import ingest_document, delete_document

@pytest.mark.asyncio
async def test_worker_retries_and_terminal_failure():
    db = AsyncMock(spec=AsyncSession)
    job = AIJob(id="job-1", document_id="doc-1", status=JobStatus.PENDING, attempts=2, max_attempts=3)
    doc = AIDocument(id="doc-1", backend_thesis_id="b-1", object_key="test.pdf")
    
    job_result, doc_result = MagicMock(), MagicMock()
    job_result.scalar_one_or_none.return_value = job
    doc_result.scalar_one.return_value = doc
    db.execute.side_effect = [job_result, doc_result]
    
    with patch('worker.main.ObjectStore') as MockStore:
        MockStore.return_value.download.side_effect = Exception("S3 Timeout")
        await process_job("job-1", db)
        assert job.status == JobStatus.FAILED
        db.commit.assert_called()

@pytest.mark.asyncio
async def test_worker_idempotency():
    db = AsyncMock(spec=AsyncSession)
    job = AIJob(id="job-2", status=JobStatus.SUCCESS)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    db.execute.return_value = mock_result
    
    await process_job("job-2", db)
    db.commit.assert_not_called()

@pytest.mark.asyncio
async def test_api_ingest_idempotency():
    db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = AIDocument(backend_thesis_id="existing-1")
    db.execute.return_value = mock_result
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await ingest_document({"backend_thesis_id": "existing-1"}, db)
    assert exc_info.value.status_code == 409

@pytest.mark.asyncio
async def test_api_delete_cascade_cleanup():
    db = AsyncMock(spec=AsyncSession)
    doc = AIDocument(id="doc-99", backend_thesis_id="thesis-99")
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    db.execute.return_value = mock_result
    
    await delete_document("thesis-99", db)
    
    # Verify explicit cleanup calls were made before deleting the doc
    assert db.execute.call_count >= 2 # At least delete chunks and delete jobs
    db.delete.assert_called_with(doc)
    db.commit.assert_called()

@pytest.mark.asyncio
async def test_permission_enforcement_unauthorized():
    from api.routes import verify_internal_token
    from fastapi import HTTPException
    
    # Should raise 401 if token is missing or wrong
    with pytest.raises(HTTPException) as exc_info:
        verify_internal_token(x_internal_service_token="wrong-token")
    assert exc_info.value.status_code == 401