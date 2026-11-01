"""P1 regression tests — ingestion reliability.

Covers the failure modes that previously produced a false SUCCESS:
- scanned/empty PDFs with no extractable text
- documents that chunk to nothing
- documents whose embeddings produce no vectors
- Vectorize confirming fewer vectors than were submitted
- retry/duplicate handling (only failed ingestions may be retried)
- vector cleanup when a document is deleted
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.config import VectorizeConfig
from oau_ai.db.models import JobStatus, ProcessingStage
from oau_ai.document_processing.extraction import ExtractedPage
from oau_ai.embeddings.vectorize import VectorizeService
from oau_ai.errors import ConfigurationError, Phase3Error, ProviderUnavailableError
from oau_ai.ingestion.service import IngestionService


def _actor(user_id="user-123", roles=None):
    return ActorContext(
        user_id=user_id,
        roles=roles or ["student"],
        department="CS",
        trace_id="trace-p1",
    )


def _make_service(tmp_path, db=None, vectorize=None):
    return IngestionService(
        db_session=db or AsyncMock(),
        vectorize_service=vectorize,
        storage_base_path=str(tmp_path / "store"),
    )


def _job_document_pair(job, document):
    """db.get is called for the job first, then the document."""
    calls = {"n": 0}

    async def _get(model, pk):
        calls["n"] += 1
        return job if calls["n"] == 1 else document

    return _get


def _job(**kwargs):
    job = MagicMock()
    job.id = kwargs.get("id", "job-1")
    job.document_id = kwargs.get("document_id", "doc-1")
    job.status = kwargs.get("status", JobStatus.PENDING)
    job.stage = kwargs.get("stage", ProcessingStage.EXTRACTION)
    job.attempts = kwargs.get("attempts", 0)
    job.max_attempts = kwargs.get("max_attempts", 3)
    job.error_message = None
    job.error_stage = None
    return job


def _document(**kwargs):
    document = MagicMock()
    document.id = kwargs.get("id", "doc-1")
    document.backend_thesis_id = kwargs.get("backend_thesis_id", "thesis-1")
    document.backend_user_id = kwargs.get("backend_user_id", "user-123")
    document.access_level = kwargs.get("access_level", "private")
    document.embedding_status = kwargs.get("embedding_status", "pending")
    document.object_key = kwargs.get("object_key", "/nonexistent/file.pdf")
    return document


@pytest.mark.asyncio
async def test_scanned_pdf_fails_instead_of_reporting_success(tmp_path):
    """A PDF with no extractable text must fail honestly, not report success."""
    job = _job()
    document = _document()
    db = AsyncMock()
    db.commit = AsyncMock()
    db.get = _job_document_pair(job, document)

    service = _make_service(tmp_path, db=db)
    service._extract_pages = AsyncMock(
        return_value=[
            ExtractedPage(page_number=1, text=None, is_scanned=True),
            ExtractedPage(page_number=2, text=None, is_scanned=True),
        ]
    )

    with pytest.raises(Exception) as exc_info:
        await service.process_job("job-1", _actor())

    assert job.status == JobStatus.FAILED
    assert job.stage == ProcessingStage.FAILED
    assert "no extractable text" in job.error_message.lower()
    assert "ocr" in job.error_message.lower()
    assert "no_extractable_text" in str(exc_info.value)


@pytest.mark.asyncio
async def test_document_that_chunks_to_nothing_fails(tmp_path):
    """Text extracted but no chunks produced → failure, not empty success."""
    job = _job()
    document = _document()
    db = AsyncMock()
    db.commit = AsyncMock()
    db.get = _job_document_pair(job, document)

    service = _make_service(tmp_path, db=db)
    service._extract_pages = AsyncMock(
        return_value=[ExtractedPage(page_number=1, text="some text", is_scanned=False)]
    )
    service._chunk_pages = AsyncMock(return_value=[])

    with pytest.raises(Exception):
        await service.process_job("job-1", _actor())

    assert job.status == JobStatus.FAILED
    assert "no_indexable_content" in job.error_message


@pytest.mark.asyncio
async def test_embeddings_producing_no_vectors_fails(tmp_path):
    job = _job()
    document = _document()
    db = AsyncMock()
    db.commit = AsyncMock()
    db.get = _job_document_pair(job, document)

    service = _make_service(tmp_path, db=db)
    service._extract_pages = AsyncMock(
        return_value=[ExtractedPage(page_number=1, text="text", is_scanned=False)]
    )
    service._chunk_pages = AsyncMock(return_value=[{"chunk_index": 0, "text": "text"}])
    service._embed_chunks = AsyncMock(return_value=[])

    with pytest.raises(Exception):
        await service.process_job("job-1", _actor())

    assert job.status == JobStatus.FAILED
    assert "embedding_produced_no_vectors" in job.error_message


@pytest.mark.asyncio
async def test_successful_pipeline_completes(tmp_path):
    job = _job()
    document = _document()
    db = AsyncMock()
    db.commit = AsyncMock()
    db.get = _job_document_pair(job, document)

    service = _make_service(tmp_path, db=db)
    service._extract_pages = AsyncMock(
        return_value=[ExtractedPage(page_number=1, text="text", is_scanned=False)]
    )
    service._chunk_pages = AsyncMock(return_value=[{"chunk_index": 0, "text": "text"}])
    service._embed_chunks = AsyncMock(
        return_value=[{"chunk_index": 0, "text": "text", "vector": [0.1]}]
    )
    service._upsert_to_vectorize = AsyncMock(return_value=None)

    result = await service.process_job("job-1", _actor())

    assert result.status == JobStatus.SUCCESS
    assert result.stage == ProcessingStage.COMPLETE
    assert document.embedding_status == "completed"


@pytest.mark.asyncio
async def test_partial_vectorize_confirmation_fails_ingestion(tmp_path):
    """Fewer confirmed vectors than submitted must not be treated as indexed."""
    vectorize = AsyncMock()
    vectorize.is_configured = MagicMock(return_value=True)
    vectorize.aupsert = AsyncMock(return_value={"success": True, "result": {"count": 1}})

    service = _make_service(tmp_path, db=AsyncMock(), vectorize=vectorize)
    document = _document()

    chunks = [
        {
            "chunk_index": i,
            "text": "t",
            "page_number": 1,
            "vector": [0.1, 0.2],
            "db_chunk": MagicMock(id=f"chunk-{i}", vectorize_point_id=None),
        }
        for i in range(3)
    ]

    with pytest.raises(ProviderUnavailableError):
        await service._upsert_to_vectorize(document, chunks)


def test_assert_upsert_confirmed_rules():
    assert IngestionService._assert_upsert_confirmed({"result": {"count": 2}}, 2) is None
    # No count reported: the 2xx response itself is the confirmation.
    assert IngestionService._assert_upsert_confirmed({"success": True}, 2) is None

    with pytest.raises(ProviderUnavailableError):
        IngestionService._assert_upsert_confirmed({"success": False, "errors": ["boom"]}, 2)

    with pytest.raises(ProviderUnavailableError):
        IngestionService._assert_upsert_confirmed({"result": {"count": 1}}, 2)


@pytest.mark.asyncio
async def test_failed_document_can_be_reingested(tmp_path):
    """A failed ingestion is retryable: derived data is purged and a new job queued."""
    existing = _document(embedding_status="failed")
    latest = _job(status=JobStatus.FAILED)

    doc_result = MagicMock()
    doc_result.scalar_one_or_none = MagicMock(return_value=existing)
    job_result = MagicMock()
    job_result.scalar_one_or_none = MagicMock(return_value=latest)

    db = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(side_effect=[doc_result, job_result])

    source = tmp_path / "upload.pdf"
    source.write_bytes(b"%PDF-1.4 content")

    service = _make_service(tmp_path, db=db)
    service._purge_derived_data = AsyncMock()

    document, job = await service.create_document_and_job(
        actor_context=_actor(),
        file_path=str(source),
        filename="thesis.pdf",
        backend_thesis_id="thesis-1",
        access_level="private",
    )

    service._purge_derived_data.assert_awaited_once()
    assert job.status == JobStatus.PENDING
    assert job.attempts == 0
    assert job.document_id == "doc-1"
    assert document.embedding_status == "pending"


@pytest.mark.asyncio
async def test_completed_document_cannot_be_reingested(tmp_path):
    """A successful document rejects re-ingestion so vectors are not duplicated."""
    existing = _document(embedding_status="completed")
    latest = _job(status=JobStatus.SUCCESS)

    doc_result = MagicMock()
    doc_result.scalar_one_or_none = MagicMock(return_value=existing)
    job_result = MagicMock()
    job_result.scalar_one_or_none = MagicMock(return_value=latest)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[doc_result, job_result])

    source = tmp_path / "upload.pdf"
    source.write_bytes(b"%PDF-1.4 content")

    service = _make_service(tmp_path, db=db)

    with pytest.raises(Phase3Error) as exc_info:
        await service.create_document_and_job(
            actor_context=_actor(),
            file_path=str(source),
            filename="thesis.pdf",
            backend_thesis_id="thesis-1",
        )

    assert "already exists" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_reingest_rejected_for_non_owner(tmp_path):
    """Only the owner or an admin may replace a failed document."""
    existing = _document(backend_user_id="someone-else", embedding_status="failed")
    latest = _job(status=JobStatus.FAILED)

    doc_result = MagicMock()
    doc_result.scalar_one_or_none = MagicMock(return_value=existing)
    job_result = MagicMock()
    job_result.scalar_one_or_none = MagicMock(return_value=latest)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[doc_result, job_result])

    source = tmp_path / "upload.pdf"
    source.write_bytes(b"%PDF-1.4 content")

    service = _make_service(tmp_path, db=db)

    with pytest.raises(Phase3Error) as exc_info:
        await service.create_document_and_job(
            actor_context=_actor(),
            file_path=str(source),
            filename="thesis.pdf",
            backend_thesis_id="thesis-1",
        )

    assert "access" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_delete_document_removes_vectors(tmp_path):
    """Deleting a document must also delete its Vectorize points."""
    document = _document(object_key=str(tmp_path / "gone.pdf"))

    doc_result = MagicMock()
    doc_result.scalar_one_or_none = MagicMock(return_value=document)
    chunk_result = MagicMock()
    chunk_result.scalars.return_value.all.return_value = ["p1", "p2"]

    db = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock(side_effect=[doc_result, chunk_result])

    vectorize = AsyncMock()
    service = _make_service(tmp_path, db=db, vectorize=vectorize)

    await service.delete_document("thesis-1", _actor())

    vectorize.adelete.assert_awaited_once_with(["p1", "p2"])


def _configured_service(transport: httpx.BaseTransport) -> VectorizeService:
    return VectorizeService(
        config=VectorizeConfig(
            api_token="token",
            account_id="acct-123",
            index_name="idx",
            dimensions=1024,
        ),
        transport=transport,
    )


@pytest.mark.asyncio
async def test_vectorize_adelete_posts_point_ids():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"success": True, "result": {"count": 2}})

    service = _configured_service(httpx.MockTransport(handler))
    result = await service.adelete(["p1", "p2"])

    assert seen["url"].endswith("/vectorize/v2/indexes/idx/delete")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_vectorize_adelete_requires_configuration():
    service = VectorizeService(
        config=VectorizeConfig(
            api_token=None, account_id=None, index_name="idx", dimensions=1024
        )
    )

    with pytest.raises(ConfigurationError):
        await service.adelete(["p1"])


@pytest.mark.asyncio
async def test_vectorize_adelete_noop_without_ids():
    service = VectorizeService(
        config=VectorizeConfig(
            api_token=None, account_id=None, index_name="idx", dimensions=1024
        )
    )

    assert await service.adelete([]) == {"deleted": 0}
