"""FastAPI router for Phase 3 V2 endpoints.

Endpoints:
- POST   /api/v2/documents/upload   - Upload PDF and start ingestion
- GET    /api/v2/documents/jobs/{job_id} - Get job status
- DELETE /api/v2/documents/{backend_thesis_id} - Delete document
- POST   /api/v2/rag/ask            - Grounded RAG question
- POST   /api/v2/research-gaps/ask  - Research gap detection

Authentication: Service-to-service token from Django (Bearer).
Actor context: Django-issued headers (x-user-id, x-roles, x-department, x-trace-id).
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from fastapi.responses import JSONResponse

from ..api.dependencies import get_actor_context, get_internal_service_token, get_trace_id
from ..agent.graph import run_agent
from ..auth.middleware import ActorContext
from ..db.models import AIDocument, AIJob, AIPage, JobStatus, WorkingMemoryExchange
from ..db.session import get_session_factory

def AsyncSessionLocal():
    return get_session_factory()()
from ..errors import Phase3Error, ProviderUnavailableError
from ..embeddings.service import EmbeddingService
from ..embeddings.vectorize import VectorizeService
from ..ingestion.service import IngestionService
from ..llm.base import ChatMessage, ChatRequest
from ..llm.router import TaskDesignation, complete_with_groq_designated, get_router
from ..memory.service import MemoryService
from ..rag.service import RAGService
from ..research_gap.service import ResearchGapService
from ..retrieval.service import RetrievalService
from ..recommendations.service import RecommendationService
from ..similarity.service import PlagiarismAssessmentService, SimilarityService
from ..ai_writing.service import AITextDetectionService, get_detection_service
from ..topics.service import TopicService
from .schemas import (
    AgentAskRequest,
    AgentAskResponse,
    AssistantChatRequest,
    AssistantChatResponse,
    DocumentPageText,
    DocumentTextResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
    EntityExtractRequest,
    EntityExtractResponse,
    EntityListResponse,
    EntityRelationshipCreateRequest,
    EntityRelationshipCreateResponse,
    EntityRelationshipListResponse,
    EntityRelationshipSchema,
    EntitySchema,
    ErrorResponse,
    JobStatusResponse,
    MemoryCreateRequest,
    MemoryEntrySchema,
    MemoryPreferencesSchema,
    MemoryRetrievalRequest,
    MemoryResponse,
    MemoryRetrievalResponse,
    MemoryUpdateRequest,
    RAGRequest,
    RAGResponse,
    ResearchGapRequest,
    ResearchGapResponse,
    ThesisSummaryCreateRequest,
    ThesisSummarySchema,
    WorkingMemoryContextResponse,
    WorkingMemoryCreateRequest,
    WorkingMemoryCreateResponse,
    WorkingMemoryExchangeSchema,
    TopicAnalysisRequest,
    TopicAnalysisResponse,
    TopicCountSchema,
    TrendPointSchema,
    RecommendationRequest,
    RecommendationResponseSchema,
    RecommendationSchema,
    RecommendationEvidenceSchema,
    SimilarityCheckRequest,
    SimilarityResponseSchema,
    SimilarityMatchSchema,
    PlagiarismAssessRequest,
    PlagiarismResponseSchema,
    PlagiarismPassageSchema,
    AIWritingDetectRequest,
    AIWritingResponseSchema,
    AIWritingSegmentSchema,
    ThesisQARequest,
    ThesisQAResponseSchema,
    ThesisQACitationSchema,
)
from ..telemetry.core import TelemetryEvent, telemetry_context

logger = logging.getLogger("oau_ai.api")

router = APIRouter(prefix="/api/v2", tags=["Phase 3 V2"])


def _phase3_error_response(error: Phase3Error) -> JSONResponse:
    return JSONResponse(
        status_code=400 if not error.retryable else 503,
        content=error.to_dict(),
    )


def _thesis_summary_schema(summary) -> ThesisSummarySchema:
    return ThesisSummarySchema(
        document_id=summary.document_id,
        backend_thesis_id=summary.backend_thesis_id,
        user_id=summary.user_id,
        title=summary.title,
        abstract_summary=summary.abstract_summary,
        research_questions=summary.research_questions or [],
        objectives=summary.objectives or [],
        methodology=summary.methodology,
        findings=summary.findings or [],
        limitations=summary.limitations or [],
        key_entities=summary.key_entities or [],
        confidence=summary.confidence,
        missing_sections=summary.missing_sections,
    )


@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=202,
    summary="Upload a thesis PDF and start ingestion",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    backend_thesis_id: str = Form(...),
    backend_user_id: str = Form(...),
    access_level: str = Form(default="private"),
    thesis_metadata: Optional[str] = Form(default=None),
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Upload a PDF thesis file and queue it for ingestion.

    The file is stored locally, a document record and ingestion job are
    created in PostgreSQL, and the ingestion pipeline runs in the
    background. Canonical text and provenance are stored in PostgreSQL;
    embeddings are upserted to Cloudflare Vectorize.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")

    # Validate access_level.
    if access_level not in {"public", "restricted", "private"}:
        raise HTTPException(status_code=400, detail="Invalid access level.")

    # Save uploaded file to a temp location for the ingestion service.
    suffix = ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    metadata = None
    if thesis_metadata:
        import json

        try:
            metadata = json.loads(thesis_metadata)
        except json.JSONDecodeError:
            metadata = {"raw": thesis_metadata}

    async with AsyncSessionLocal() as db:
        service = IngestionService(db_session=db)
        try:
            document, job = await service.create_document_and_job(
                actor_context=actor,
                file_path=tmp_path,
                filename=file.filename,
                backend_thesis_id=backend_thesis_id,
                access_level=access_level,
                thesis_metadata=metadata,
            )
        except Phase3Error as exc:
            # Clean up temp file on failure.
            Path(tmp_path).unlink(missing_ok=True)
            return _phase3_error_response(exc)

    # Schedule background ingestion.
    background_tasks.add_task(
        _run_ingestion_background,
        job.id,
        actor.user_id,
        actor.roles,
        actor.department,
        trace_id,
        tmp_path,
    )

    return DocumentUploadResponse(
        document_id=document.id,
        job_id=job.id,
        status=job.status.value,
        message="Document uploaded and ingestion job queued.",
    )


async def _run_ingestion_background(
    job_id: str,
    user_id: str,
    roles: List[str],
    department: str,
    trace_id: str,
    tmp_path: str,
):
    """Background task: run the ingestion pipeline."""
    import os

    from ..ingestion.service import IngestionService
    from ..auth.middleware import ActorContext

    actor = ActorContext(
        user_id=user_id,
        roles=roles,
        department=department,
        trace_id=trace_id,
    )

    async with AsyncSessionLocal() as db:
        service = IngestionService(db_session=db)
        try:
            await service.process_job(job_id, actor)
        except Exception:
            logger.exception("Ingestion job %s failed in background.", job_id)
        finally:
            # Clean up temp file.
            Path(tmp_path).unlink(missing_ok=True)


@router.get(
    "/documents/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get ingestion job status",
)
async def get_job_status(
    job_id: str,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Get the status of an ingestion job.

    Only the document owner or an admin can view the job status.
    """
    async with AsyncSessionLocal() as db:
        service = IngestionService(db_session=db)
        try:
            job = await service.get_job_status(job_id, actor)
        except Phase3Error as exc:
            return _phase3_error_response(exc)

        document = await db.get(AIDocument, job.document_id)
        result = None
        if job.status.value == "success" and document:
            result = {
                "document_id": document.id,
                "backend_thesis_id": document.backend_thesis_id,
                "embedding_status": document.embedding_status,
            }

        # Capture all ORM values while the session is open to avoid
        # accessing detached objects after the context closes.
        job_id = job.id
        status = job.status.value
        stage = job.stage.value
        message = job.error_message or f"Ingestion {job.status.value}."
        error_message = job.error_message
        error_stage = job.error_stage
        attempts = job.attempts
        max_attempts = job.max_attempts

    return JobStatusResponse(
        job_id=job_id,
        status=status,
        stage=stage,
        message=message,
        result=result,
        error_message=error_message,
        error_stage=error_stage,
        attempts=attempts,
        max_attempts=max_attempts,
    )


@router.delete(
    "/documents/{backend_thesis_id}",
    summary="Delete a thesis document and all derived data",
)
async def delete_document(
    backend_thesis_id: str,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Delete a document, its pages, chunks, jobs, and source file.

    Cascade cleanup removes all derived data. Vectorize point IDs are
    recorded; Vectorize deletion is best-effort.
    """
    async with AsyncSessionLocal() as db:
        service = IngestionService(db_session=db)
        try:
            await service.delete_document(backend_thesis_id, actor)
        except Phase3Error as exc:
            return _phase3_error_response(exc)

    return {"detail": f"Document {backend_thesis_id} deleted."}


@router.delete(
    "/documents/cleanup-temporary",
    summary="Clean up expired temporary documents",
)
async def cleanup_temporary_documents(
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Delete expired temporary documents identified by the ``tmp-pdf-`` prefix.

    Only removes documents that:
    - Have ``backend_thesis_id`` starting with ``tmp-pdf-`` (temporary uploads only;
      permanent repository theses are never affected).
    - Were created more than 24 hours ago.
    - Have no active ingestion job (job is success/failed, or no job exists).

    Admin-only. Idempotent: safe to run on a schedule (e.g. daily cron).
    """
    if "admin" not in actor.roles:
        raise HTTPException(status_code=403, detail="Admin access required.")

    cutoff = datetime.utcnow() - timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AIDocument).where(
                AIDocument.backend_thesis_id.like("tmp-pdf-%"),
                AIDocument.created_at < cutoff,
            )
        )
        documents = result.scalars().all()

        cleaned = 0
        skipped = 0
        errors: list[str] = []

        for document in documents:
            # Skip documents with an active (non-terminal) ingestion job.
            job_result = await db.execute(
                select(AIJob)
                .where(AIJob.document_id == document.id)
                .order_by(AIJob.created_at.desc())
                .limit(1)
            )
            latest_job = job_result.scalar_one_or_none()

            if latest_job and latest_job.status not in (
                JobStatus.SUCCESS,
                JobStatus.FAILED,
            ):
                skipped += 1
                logger.info(
                    "cleanup_temporary.skip document_id=%s backend_thesis_id=%s "
                    "reason=job_active status=%s",
                    document.id,
                    document.backend_thesis_id,
                    latest_job.status.value,
                )
                continue

            try:
                service = IngestionService(db_session=db)
                await service.delete_document(document.backend_thesis_id, actor)
                cleaned += 1
                logger.info(
                    "cleanup_temporary.deleted document_id=%s backend_thesis_id=%s",
                    document.id,
                    document.backend_thesis_id,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
                logger.warning(
                    "cleanup_temporary.error document_id=%s backend_thesis_id=%s error=%s",
                    document.id,
                    document.backend_thesis_id,
                    exc,
                )

        return {
            "cleaned": cleaned,
            "skipped": skipped,
            "errors": len(errors),
            "error_details": errors[:10],
        }


@router.get(
    "/documents/{internal_document_id}/text",
    response_model=DocumentTextResponse,
    summary="Get extracted document text with page mappings",
)
async def get_document_text(
    internal_document_id: str,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Return extracted page-level text for an ingested document.

    Access is restricted to the document owner or an admin. Used by the
    temporary PDF similarity check flow to retrieve extracted text without
    exposing it to unauthorised callers.
    """
    async with AsyncSessionLocal() as db:
        document = await db.get(AIDocument, internal_document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")

        # Access control: only the document owner or an admin may read the text.
        if (
            document.backend_user_id != actor.user_id
            and "admin" not in actor.roles
        ):
            raise HTTPException(status_code=403, detail="Access denied.")

        result = await db.execute(
            select(AIPage)
            .where(AIPage.document_id == internal_document_id)
            .order_by(AIPage.page_number)
        )
        pages = result.scalars().all()

        if not pages:
            raise HTTPException(
                status_code=404,
                detail="No extracted pages found for this document.",
            )

        total_characters = sum(len(page.text_content or "") for page in pages)

        return DocumentTextResponse(
            document_id=document.id,
            backend_thesis_id=document.backend_thesis_id,
            pages=[
                DocumentPageText(
                    page_number=page.page_number,
                    text=page.text_content,
                    char_offset_start=page.char_offset_start,
                    char_offset_end=page.char_offset_end,
                    is_scanned=page.is_scanned,
                )
                for page in pages
            ],
            total_characters=total_characters,
            total_pages=len(pages),
        )


@router.post(
    "/rag/ask",
    response_model=RAGResponse,
    summary="Ask a grounded research question",
)
async def ask_rag_question(
    request: RAGRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Ask a grounded research question using authorized retrieval + DeepSeek.

    1. JEV classifies the question (security gate).
    2. Document access is enforced before retrieval.
    3. Vectorize semantic retrieval finds relevant chunks.
    4. Chunk text + provenance are fetched from PostgreSQL.
    5. DeepSeek generates an answer using only retrieved evidence.
    6. Citations are validated against actual evidence.
    7. Structured abstention if evidence is insufficient.

    Groq is never used as a fallback when DeepSeek fails.
    """
    with telemetry_context(
        component="rag_api",
        event_type="api_request",
        trace_id=trace_id,
        model_provider="deepseek",
        llm_tier=1,
    ):
        # Use RAG service.
        async with AsyncSessionLocal() as db:
            retrieval_service = RetrievalService(db_session=db)
            rag_service = RAGService(
                db_session=db,
                retrieval_service=retrieval_service,
            )

            try:
                result = await rag_service.ask(
                    question=request.question,
                    actor_context=actor,
                    document_ids=request.document_ids,
                    top_k=request.top_k,
                    request_id=trace_id,
                )
            except ProviderUnavailableError as exc:
                # DeepSeek failed — no fallback. Return structured error.
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "provider_unavailable",
                        "message": exc.message,
                        "component": exc.component,
                        "retryable": exc.retryable,
                        "trace_id": exc.trace_id,
                    },
                )
            except Phase3Error as exc:
                return _phase3_error_response(exc)

        return RAGResponse(
            answer=result.answer,
            citations=[
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "backend_thesis_id": c.backend_thesis_id,
                    "text_snippet": c.text_snippet,
                    "page_number": c.page_number,
                    "section": c.section,
                    "relevance_score": c.relevance_score,
                }
                for c in result.citations
            ],
            confidence=result.confidence,
            decision_engine=result.decision_engine,
            llm_tier=result.llm_tier,
            trace_id=result.trace_id,
            request_id=result.request_id,
            insufficient_evidence=result.insufficient_evidence,
            message=result.message,
            abstention_reason=result.abstention_reason,
        )


@router.post(
    "/research-gaps/ask",
    response_model=ResearchGapResponse,
    summary="Detect research gaps from thesis evidence",
)
async def ask_research_gaps(
    request: ResearchGapRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Detect research gaps from retrieved thesis evidence.

    1. JEV classifies the gap analysis request (security gate).
    2. Document access is enforced before retrieval.
    3. Vectorize semantic retrieval finds relevant thesis chunks.
    4. Chunk text + provenance are fetched from PostgreSQL.
    5. DeepSeek analyzes gaps using only retrieved evidence.
    6. Citations are validated against actual evidence.
    7. Structured abstention if evidence is insufficient.

    Groq is never used as a fallback when DeepSeek fails.
    """
    with telemetry_context(
        component="research_gap_api",
        event_type="api_request",
        trace_id=trace_id,
        model_provider="deepseek",
        llm_tier=1,
    ):
        # Use research gap service.
        async with AsyncSessionLocal() as db:
            retrieval_service = RetrievalService(db_session=db)
            gap_service = ResearchGapService(
                db_session=db,
                retrieval_service=retrieval_service,
            )

            try:
                result = await gap_service.detect_gaps(
                    research_question=request.research_question,
                    actor_context=actor,
                    document_ids=request.document_ids,
                    top_k=request.top_k,
                    request_id=trace_id,
                )
            except ProviderUnavailableError as exc:
                # DeepSeek failed — no fallback. Return structured error.
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "provider_unavailable",
                        "message": exc.message,
                        "component": exc.component,
                        "retryable": exc.retryable,
                        "trace_id": exc.trace_id,
                    },
                )
            except Phase3Error as exc:
                return _phase3_error_response(exc)

        return ResearchGapResponse(
            gaps=[
                {
                    "gap_type": g.gap_type,
                    "description": g.description,
                    "supporting_evidence": g.supporting_evidence,
                    "source_thesis_references": g.source_thesis_references,
                    "page_numbers": g.page_numbers,
                    "chunk_citations": [
                        {
                            "chunk_id": c.chunk_id,
                            "document_id": c.document_id,
                            "backend_thesis_id": c.backend_thesis_id,
                            "text_snippet": c.text_snippet,
                            "page_number": c.page_number,
                            "section": c.section,
                            "relevance_score": c.relevance_score,
                        }
                        for c in g.chunk_citations
                    ],
                    "source_origin": g.source_origin,
                    "explanation": g.explanation,
                    "suggested_research_direction": g.suggested_research_direction,
                    "confidence": g.confidence,
                }
                for g in result.gaps
            ],
            insufficient_evidence=result.insufficient_evidence,
            confidence=result.confidence,
            decision_engine=result.decision_engine,
            llm_tier=result.llm_tier,
            trace_id=result.trace_id,
            request_id=result.request_id,
            message=result.message,
        )


@router.post(
    "/memory/retrieve",
    response_model=MemoryRetrievalResponse,
    summary="Retrieve relevant memories for a researcher",
)
async def retrieve_memories(
    request: MemoryRetrievalRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Retrieve memories relevant to a query for the authenticated researcher.

    1. JEV classifies the request (security gate).
    2. Semantic search via Vectorize (user_id-isolated) + keyword fallback.
    3. Returns memory entries ranked by relevance.
    """
    with telemetry_context(
        component="memory_api",
        event_type="memory_retrieve",
        trace_id=trace_id,
        model_provider="deepseek",
        llm_tier=1,
    ):
        async with AsyncSessionLocal() as db:
            memory_service = MemoryService(db_session=db)

            try:
                result = await memory_service.retrieve_relevant_memories(
                    user_id=actor.user_id,
                    query=request.query,
                    top_k=request.top_k,
                    memory_types=request.memory_types,
                    trace_id=trace_id,
                )
            except ProviderUnavailableError as exc:
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "provider_unavailable",
                        "message": exc.message,
                        "component": exc.component,
                        "retryable": exc.retryable,
                        "trace_id": exc.trace_id,
                    },
                )
            except Phase3Error as exc:
                return _phase3_error_response(exc)

        return MemoryRetrievalResponse(
            entries=[
                {
                    "id": e.id,
                    "user_id": e.user_id,
                    "memory_type": e.memory_type,
                    "source": e.source,
                    "key": e.key,
                    "value": e.value,
                    "confidence": e.confidence,
                    "is_archived": e.is_archived,
                    "source_document_id": e.source_document_id,
                    "source_chunk_id": e.source_chunk_id,
                    "provenance": e.provenance,
                    "created_at": e.created_at,
                    "updated_at": e.updated_at,
                }
                for e in result.entries
            ],
            total_found=result.total_found,
            query=result.query,
        )


@router.get(
    "/memory/",
    response_model=MemoryResponse,
    summary="List researcher memories",
)
async def list_memories(
    memory_type: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 50,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """List all memories for the authenticated researcher."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        entries = await memory_service.list_memories(
            user_id=actor.user_id,
            memory_type=memory_type,
            include_archived=include_archived,
            limit=limit,
        )

    return MemoryResponse(
        entries=[
            {
                "id": e.id,
                "user_id": e.user_id,
                "memory_type": e.memory_type,
                "source": e.source,
                "key": e.key,
                "value": e.value,
                "confidence": e.confidence,
                "is_archived": e.is_archived,
                "source_document_id": e.source_document_id,
                "source_chunk_id": e.source_chunk_id,
                "provenance": e.provenance,
                "created_at": e.created_at,
                "updated_at": e.updated_at,
            }
            for e in entries
        ],
        total=len(entries),
    )


@router.post(
    "/memory/",
    response_model=MemoryEntrySchema,
    summary="Create or update a researcher memory",
)
async def create_or_update_memory(
    request: MemoryCreateRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Create or update a researcher memory entry.

    If a memory with the same key exists, it is updated (confidence averaged).
    """
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        memory_id = await memory_service.upsert_profile_memory(
            user_id=actor.user_id,
            key=request.key,
            value=request.value,
            confidence=request.confidence,
            source=request.source,
            trace_id=trace_id,
        )
        entry = await memory_service.get_memory(memory_id, actor.user_id)

    if not entry:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to create memory entry"},
        )

    return MemoryEntrySchema(
        id=entry.id,
        user_id=entry.user_id,
        memory_type=entry.memory_type,
        source=entry.source,
        key=entry.key,
        value=entry.value,
        confidence=entry.confidence,
        is_archived=entry.is_archived,
        source_document_id=entry.source_document_id,
        source_chunk_id=entry.source_chunk_id,
        provenance=entry.provenance,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.post(
    "/memory/working",
    response_model=WorkingMemoryCreateResponse,
    summary="Add a working memory exchange",
)
async def add_working_memory_exchange(
    request: WorkingMemoryCreateRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Append an exchange to the researcher's rolling working memory."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        exchange_id = await memory_service.add_working_memory_exchange(
            user_id=actor.user_id,
            exchange_type=request.exchange_type,
            content=request.content,
            unresolved_questions=request.unresolved_questions,
            decisions=request.decisions,
            current_tasks=request.current_tasks,
            trace_id=trace_id,
        )

    return WorkingMemoryCreateResponse(exchange_id=exchange_id, user_id=actor.user_id)


@router.get(
    "/memory/working/context",
    response_model=WorkingMemoryContextResponse,
    summary="Get working memory context for LLM injection",
)
async def get_working_memory_context(
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Return the researcher's working memory as a prompt-context string."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        context = await memory_service.get_working_memory_context(user_id=actor.user_id)

    return WorkingMemoryContextResponse(user_id=actor.user_id, context=context)


@router.post(
    "/memory/entities/extract",
    response_model=EntityExtractResponse,
    summary="Extract research entities from text",
)
async def extract_entities_endpoint(
    request: EntityExtractRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Extract and persist research entities (topics, researchers, etc.)."""
    with telemetry_context(
        component="memory_api",
        event_type="entity_extract",
        trace_id=trace_id,
        model_provider="deepseek",
        llm_tier=1,
    ):
        async with AsyncSessionLocal() as db:
            memory_service = MemoryService(db_session=db)
            entities = await memory_service.extract_entities(
                user_id=actor.user_id,
                text=request.text,
                trace_id=trace_id,
            )

    return EntityExtractResponse(entities=entities, total=len(entities))


@router.get(
    "/memory/entities",
    response_model=EntityListResponse,
    summary="List extracted research entities",
)
async def list_entities_endpoint(
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """List research entities for the authenticated researcher."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        entities = await memory_service.list_entities(user_id=actor.user_id)

    return EntityListResponse(
        entities=[
            EntitySchema(
                id=e.id,
                user_id=e.user_id,
                entity_type=e.entity_type,
                entity_name=e.entity_name,
                normalized_name=e.normalized_name,
                description=e.description,
                confidence=e.confidence,
                occurrence_count=e.occurrence_count,
            )
            for e in entities
        ],
        total=len(entities),
    )


@router.post(
    "/memory/relationships",
    response_model=EntityRelationshipCreateResponse,
    summary="Add an entity relationship",
)
async def add_entity_relationship_endpoint(
    request: EntityRelationshipCreateRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Record a relationship between two research entities."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        relationship_id = await memory_service.add_entity_relationship(
            user_id=actor.user_id,
            source_entity_id=request.source_entity_id,
            target_entity_id=request.target_entity_id,
            relationship_type=request.relationship_type,
            confidence=request.confidence,
            provenance={"trace_id": trace_id},
        )

    return EntityRelationshipCreateResponse(relationship_id=relationship_id)


@router.get(
    "/memory/relationships",
    response_model=EntityRelationshipListResponse,
    summary="List entity relationships",
)
async def list_relationships_endpoint(
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """List entity relationships for the authenticated researcher."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        relationships = await memory_service.list_relationships(user_id=actor.user_id)

    return EntityRelationshipListResponse(
        relationships=[
            EntityRelationshipSchema(
                id=r.id,
                user_id=r.user_id,
                source_entity_id=r.source_entity_id,
                target_entity_id=r.target_entity_id,
                relationship_type=r.relationship_type,
                confidence=r.confidence,
            )
            for r in relationships
        ],
        total=len(relationships),
    )


@router.get(
    "/memory/{memory_id}",
    response_model=MemoryEntrySchema,
    summary="Get a specific memory entry",
)
async def get_memory(
    memory_id: str,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Get a specific memory entry by ID, scoped to the owner."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        entry = await memory_service.get_memory(memory_id, actor.user_id)

    if not entry:
        return JSONResponse(
            status_code=404,
            content={"error": "Memory not found"},
        )

    return MemoryEntrySchema(
        id=entry.id,
        user_id=entry.user_id,
        memory_type=entry.memory_type,
        source=entry.source,
        key=entry.key,
        value=entry.value,
        confidence=entry.confidence,
        is_archived=entry.is_archived,
        source_document_id=entry.source_document_id,
        source_chunk_id=entry.source_chunk_id,
        provenance=entry.provenance,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.put(
    "/memory/{memory_id}",
    response_model=MemoryEntrySchema,
    summary="Update or correct a memory entry",
)
async def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Update or correct a memory entry (correction lifecycle)."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        entry = await memory_service.update_memory(
            memory_id=memory_id,
            user_id=actor.user_id,
            value=request.value,
            confidence=request.confidence,
            trace_id=trace_id,
        )

    if not entry:
        return JSONResponse(
            status_code=404,
            content={"error": "Memory not found"},
        )

    return MemoryEntrySchema(
        id=entry.id,
        user_id=entry.user_id,
        memory_type=entry.memory_type,
        source=entry.source,
        key=entry.key,
        value=entry.value,
        confidence=entry.confidence,
        is_archived=entry.is_archived,
        source_document_id=entry.source_document_id,
        source_chunk_id=entry.source_chunk_id,
        provenance=entry.provenance,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.delete(
    "/memory/{memory_id}",
    summary="Delete (archive) a memory entry",
)
async def delete_memory(
    memory_id: str,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Soft-delete (archive) a memory entry."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        success = await memory_service.delete_memory(memory_id, actor.user_id)

    if not success:
        return JSONResponse(
            status_code=404,
            content={"error": "Memory not found"},
        )

    return {"detail": f"Memory {memory_id} archived."}


@router.post(
    "/memory/thesis-summaries",
    response_model=ThesisSummarySchema,
    summary="Create or update a thesis summary",
)
async def create_thesis_summary(
    request: ThesisSummaryCreateRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Create, generate or update a structured thesis summary.

    ``generate=true`` summarises the thesis from its own extracted chunks and
    ignores every content field in the request. Otherwise the caller-supplied
    structure is stored, but only for a document the actor may access.
    """
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)

        if request.generate:
            try:
                summary = await memory_service.generate_thesis_summary(
                    actor_context=actor,
                    backend_thesis_id=request.backend_thesis_id,
                )
            except Phase3Error as exc:
                return _phase3_error_response(exc)
            return _thesis_summary_schema(summary)

        # Summary records embed thesis content, so the document must be
        # accessible before one can be written.
        retrieval = RetrievalService(db_session=db)
        access = await retrieval.check_document_access(
            request.backend_thesis_id, actor
        )
        if not access.can_view or not access.document_id:
            return JSONResponse(
                status_code=403,
                content={
                    "code": "access_denied",
                    "message": "You do not have access to this thesis.",
                },
            )

        await memory_service.create_thesis_summary(
            document_id=access.document_id,
            backend_thesis_id=request.backend_thesis_id,
            user_id=actor.user_id,
            title=request.title,
            abstract_summary=request.abstract_summary,
            research_questions=request.research_questions,
            objectives=request.objectives,
            methodology=request.methodology,
            findings=request.findings,
            limitations=request.limitations,
            key_entities=request.key_entities,
            confidence=request.confidence,
        )

        summary = await memory_service.get_thesis_summary(
            backend_thesis_id=request.backend_thesis_id,
            user_id=actor.user_id,
        )

    if not summary:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to create thesis summary"},
        )

    return _thesis_summary_schema(summary)


@router.get(
    "/memory/thesis-summaries/{backend_thesis_id}",
    response_model=ThesisSummarySchema,
    summary="Get a thesis summary",
)
async def get_thesis_summary(
    backend_thesis_id: str,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Get a thesis summary by backend thesis ID."""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db_session=db)
        summary = await memory_service.get_thesis_summary(
            backend_thesis_id=backend_thesis_id,
            user_id=actor.user_id,
        )

    if not summary:
        return JSONResponse(
            status_code=404,
            content={"error": "Thesis summary not found"},
        )

    return _thesis_summary_schema(summary)


@router.post(
    "/thesis-qa/ask",
    response_model=ThesisQAResponseSchema,
    summary="Ask a question about a thesis (or across public theses)",
)
async def ask_thesis_qa(
    request: ThesisQARequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Answer a question grounded in thesis text.

    Scope ``this_thesis`` restricts retrieval to the named thesis only.
    Scope ``public_theses`` retrieves across all publicly accessible theses.
    Answers cite actual retrieved passages with page numbers where available.
    """
    from ..rag.service import RAGService

    async with AsyncSessionLocal() as db:
        # Resolve the internal document ID(s) for the requested thesis.
        if request.scope == "this_thesis":
            doc_result = await db.execute(
                select(AIDocument).where(
                    AIDocument.backend_thesis_id == request.backend_thesis_id
                )
            )
            document = doc_result.scalar_one_or_none()
            if not document:
                raise HTTPException(
                    status_code=404, detail="Thesis not found."
                )
            # Verify access to the thesis.
            retrieval = RetrievalService(db_session=db)
            access = await retrieval.check_document_access(
                request.backend_thesis_id, actor
            )
            if not access.can_view:
                raise HTTPException(status_code=403, detail=access.reason or "Access denied.")
            document_ids = [document.id]
        else:
            # public_theses: only documents with access_level == "public".
            document_ids = None

        rag_service = RAGService(
            db_session=db,
            retrieval_service=RetrievalService(db_session=db),
        )
        try:
            rag_result = await rag_service.ask(
                question=request.question,
                actor_context=actor,
                document_ids=document_ids,
                top_k=request.top_k,
                request_id=trace_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Thesis Q&A generation failed.")
            raise HTTPException(
                status_code=502,
                detail=f"Q&A generation failed: {exc}",
            )

    return ThesisQAResponseSchema(
        answer=rag_result.answer,
        citations=[
            ThesisQACitationSchema(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                backend_thesis_id=c.backend_thesis_id,
                text_snippet=c.text_snippet,
                page_number=c.page_number,
                section=c.section,
                relevance_score=c.relevance_score,
            )
            for c in rag_result.citations
        ],
        confidence=rag_result.confidence,
        insufficient_evidence=rag_result.insufficient_evidence,
        message=rag_result.message,
        trace_id=rag_result.trace_id,
    )


@router.get(
    "/memory/working",
    response_model=List[WorkingMemoryExchangeSchema],
    summary="Get working memory exchanges",
)
async def get_working_memory(
    limit: int = 20,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Get working memory exchanges for the authenticated researcher."""
    session = AsyncSessionLocal()
    try:
        from sqlalchemy import desc

        result = await session.execute(
            select(WorkingMemoryExchange)
            .where(WorkingMemoryExchange.user_id == actor.user_id)
            .order_by(desc(WorkingMemoryExchange.created_at))
            .limit(limit)
        )
        exchanges = result.scalars().all()
        return [
            WorkingMemoryExchangeSchema(
                id=ex.id,
                user_id=ex.user_id,
                exchange_type=ex.exchange_type,
                content=ex.content,
                summary=ex.summary,
                unresolved_questions=ex.unresolved_questions or [],
                decisions=ex.decisions or [],
                current_tasks=ex.current_tasks or [],
                is_summarized=ex.is_summarized,
                created_at=ex.created_at.isoformat() if ex.created_at else "",
            )
            for ex in exchanges
        ]
    finally:
        await session.close()


@router.get(
    "/memory/preferences",
    response_model=MemoryPreferencesSchema,
    summary="Get memory preferences",
)
async def get_memory_preferences(
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Get memory preferences for the authenticated researcher."""
    return MemoryPreferencesSchema(
        user_id=actor.user_id,
    )


@router.get(
    "/health",
    summary="Health check",
)
async def health_check(trace_id: str = Depends(get_trace_id)):
    """Health check endpoint.

    Reports whether the AI service can reach its dependencies (database,
    Vectorize, LLM providers) without exposing credentials, and echoes the
    propagated trace_id so callers can verify request correlation.
    """
    import os

    from ..config import get_settings, get_vectorize_config
    from ..db.session import get_database_url

    settings = get_settings()
    vectorize = get_vectorize_config()

    try:
        get_database_url()
        database_configured = True
    except RuntimeError:
        database_configured = False

    return {
        "status": "ok",
        "service": "oau-thesis-bank-ai-v2",
        "primary_provider": settings.primary_provider(),
        "enabled_providers": list(settings.enabled_order()),
        "vectorize_configured": vectorize.configured,
        "database_configured": database_configured,
        "trace_id": trace_id,
    }


@router.post(
    "/agent/ask",
    response_model=AgentAskResponse,
    summary="Run the Research Intelligence Agent",
)
async def ask_agent(
    request: AgentAskRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Run the bounded research-intelligence agent (plan/verify/retrieve/answer).

    Retrieval is scoped to documents the actor can access. JEV's decision and
    verification responsibilities are preserved inside the agent's verify node.
    """
    with telemetry_context(
        component="agent_api",
        event_type="api_request",
        trace_id=trace_id,
        model_provider="deepseek",
        llm_tier=1,
    ):
        try:
            state = await run_agent(
                question=request.question,
                actor_context=actor,
                trace_id=trace_id,
                max_iterations=request.max_iterations,
            )
        except Phase3Error as exc:
            return _phase3_error_response(exc)

    return AgentAskResponse(
        answer=state.final_answer,
        citations=state.citations,
        confidence=state.confidence,
        insufficient_evidence=state.insufficient_evidence,
        status=state.status,
        iteration_count=state.iteration_count,
        error=state.error,
    )


async def _assistant_blocked_by_safety(actor: ActorContext, question: str) -> bool:
    """Best-effort JEV input safety for the general-knowledge assistant.

    Blocks only genuine guardrail/JEV blocks (e.g. prompt injection). The
    LLM-fallback path also reports BLOCK, but only because it cannot trust a
    low-confidence classification (it rejects "nice" too); the provider's own
    safety handles content, so fallback blocks are ignored here.
    """
    try:
        from ..jev.router import TypedDecisionRouter
        from ..jev.schemas import RoutingDecision, TaskType

        router = TypedDecisionRouter()
        decision = await router.route(
            task_type=TaskType.QUERY_CLASSIFICATION,
            state={"query": question},
            user_id=actor.user_id,
            require_evidence=False,
        )
        return (
            decision.decision == RoutingDecision.BLOCK
            and decision.engine_used in ("guardrails", "jev")
        )
    except Exception:  # noqa: BLE001
        logger.warning("Assistant safety check failed; proceeding (best-effort).")
        return False


@router.post(
    "/assistant/chat",
    response_model=AssistantChatResponse,
    summary="General-knowledge assistant chat",
)
async def assistant_chat(
    request: AssistantChatRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """General-knowledge chat (not grounded in the thesis corpus).

    For cited, thesis-grounded answers use ``/api/v2/rag/ask``. DeepSeek is the
    default provider; Groq is available only when explicitly selected.
    """
    provider = (request.provider or "deepseek").lower()
    if provider not in {"deepseek", "groq"}:
        raise HTTPException(status_code=400, detail="provider must be 'deepseek' or 'groq'.")

    last_user = next(
        (m for m in reversed(request.messages) if m.role == "user"),
        request.messages[-1],
    )

    with telemetry_context(
        component="assistant_api",
        event_type="api_request",
        trace_id=trace_id,
        model_provider=provider,
        llm_tier=1 if provider == "deepseek" else 2,
    ):
        if await _assistant_blocked_by_safety(actor, last_user.content):
            return AssistantChatResponse(
                answer="I can't help with that request.",
                provider=provider,
                mode="general",
                message="blocked_by_safety",
            )

        system_prompt = (
            "You are a helpful general-knowledge research assistant for the OAU Thesis Bank. "
            "Answer clearly and concisely in plain text. "
            "Do NOT use Markdown formatting: no asterisks (**), no hash headings (##), "
            "no bullet dashes, and no tables. Use short plain paragraphs. "
            "If you are not certain, say so. "
            "This is general knowledge and is NOT a citation from the thesis corpus."
        )
        messages = [ChatMessage(role="system", content=system_prompt)]
        for m in request.messages:
            role = m.role if m.role in ("user", "assistant") else "user"
            messages.append(ChatMessage(role=role, content=m.content))
        chat_request = ChatRequest(messages=messages, max_tokens=1024, temperature=0.4)

        try:
            llm_router = get_router()
            if provider == "groq":
                response = await llm_router.acomplete_groq_designated(
                    chat_request,
                    TaskDesignation(
                        task_type="general_assistant",
                        reason="user-selected general chat",
                    ),
                )
            else:
                response = await llm_router.acomplete_deepseek(chat_request)
        except ProviderUnavailableError as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "code": "provider_unavailable",
                    "message": exc.message,
                    "component": exc.component,
                    "retryable": exc.retryable,
                    "trace_id": exc.trace_id,
                },
            )

    return AssistantChatResponse(
        answer=response.content or "",
        provider=provider,
        mode="general",
    )


# ---------------------------------------------------------------------------
# P4 — topic discovery and research recommendations
# ---------------------------------------------------------------------------


@router.post(
    "/topics/analyze",
    response_model=TopicAnalysisResponse,
    summary="Aggregate repository topics, departments, faculties and years",
)
async def analyze_topics(
    request: TopicAnalysisRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Deterministic topic aggregation over documents the actor may access.

    No model calls: counts are computed from stored metadata, so the result is
    reproducible and cannot leak a document the actor is not authorised to see.
    """
    async with AsyncSessionLocal() as db:
        service = TopicService(db_session=db)
        analysis = await service.analyze(
            actor,
            max_documents=request.max_documents,
            max_topics=request.max_topics,
        )

    return TopicAnalysisResponse(
        total_documents=analysis.total_documents,
        analysed_documents=analysis.analysed_documents,
        topics=[
            TopicCountSchema(
                name=topic.name,
                document_count=topic.document_count,
                thesis_ids=topic.thesis_ids,
            )
            for topic in analysis.topics
        ],
        departments=[
            TopicCountSchema(
                name=entry.name,
                document_count=entry.document_count,
                thesis_ids=entry.thesis_ids,
            )
            for entry in analysis.departments
        ],
        faculties=[
            TopicCountSchema(
                name=entry.name,
                document_count=entry.document_count,
                thesis_ids=entry.thesis_ids,
            )
            for entry in analysis.faculties
        ],
        years=[
            TrendPointSchema(year=point.year, document_count=point.document_count)
            for point in analysis.years
        ],
        limitations=analysis.limitations,
    )


@router.post(
    "/recommendations",
    response_model=RecommendationResponseSchema,
    summary="Recommend existing theses relevant to the caller's research context",
)
async def recommendations(
    request: RecommendationRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Evidence-backed recommendations; abstains when nothing supports them."""
    async with AsyncSessionLocal() as db:
        service = RecommendationService(db_session=db)
        result = await service.recommend(
            actor,
            query=request.query,
            seed_thesis_id=request.seed_thesis_id,
            top_k=request.top_k,
        )

    return RecommendationResponseSchema(
        context_source=result.context_source,
        query=result.query,
        recommendations=[
            RecommendationSchema(
                recommendation_type=item.recommendation_type,
                title=item.title,
                backend_thesis_id=item.backend_thesis_id,
                explanation=item.explanation,
                evidence=[
                    RecommendationEvidenceSchema(
                        chunk_id=ref.chunk_id,
                        document_id=ref.document_id,
                        backend_thesis_id=ref.backend_thesis_id,
                        text_snippet=ref.text_snippet,
                        page_number=ref.page_number,
                    )
                    for ref in item.evidence
                ],
                evidence_strength=item.evidence_strength,
                limitations=item.limitations,
            )
            for item in result.recommendations
        ],
        insufficient_evidence=result.insufficient_evidence,
        message=result.message,
        limitations=result.limitations,
    )


# ---------------------------------------------------------------------------
# P5 — similarity, plagiarism assessment, AI-writing detection
# ---------------------------------------------------------------------------


def _match_schema(match) -> SimilarityMatchSchema:
    return SimilarityMatchSchema(
        match_type=match.match_type,
        score=match.score,
        document_id=match.document_id,
        backend_thesis_id=match.backend_thesis_id,
        title=match.title,
        chunk_id=match.chunk_id,
        page_number=match.page_number,
        source_excerpt=match.source_excerpt,
        submitted_excerpt=match.submitted_excerpt,
    )


@router.post(
    "/similarity/check",
    response_model=SimilarityResponseSchema,
    summary="Compare submitted text against authorised repository documents",
)
async def check_similarity(
    request: SimilarityCheckRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Lexical (and optional semantic) overlap against accessible documents."""
    if not request.text or not request.text.strip():
        return _phase3_error_response(
            Phase3Error(
                code="empty_text",
                message="No text was supplied for comparison.",
                component="similarity_api",
                retryable=False,
            )
        )

    async with AsyncSessionLocal() as db:
        service = SimilarityService(
            db_session=db,
            embedding_service=EmbeddingService(),
            vectorize_service=VectorizeService(),
            enable_semantic=request.enable_semantic,
        )
        try:
            result = await service.compare_text(
                actor,
                request.text,
                min_score=request.min_score,
                max_matches=request.max_matches,
                exclude_document_ids=request.exclude_document_ids,
            )
        except Phase3Error as exc:
            return _phase3_error_response(exc)

    return SimilarityResponseSchema(
        input_mode=result.input_mode,
        passages_scanned=result.passages_scanned,
        chunks_scanned=result.chunks_scanned,
        matches=[_match_schema(m) for m in result.matches],
        exact_matches=[_match_schema(m) for m in result.exact_matches],
        semantic_matches=[_match_schema(m) for m in result.semantic_matches],
        limitations=result.limitations,
    )


@router.post(
    "/plagiarism/assess",
    response_model=PlagiarismResponseSchema,
    summary="Assess overlap for attribution, not for a plagiarism verdict",
)
async def assess_plagiarism(
    request: PlagiarismAssessRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Return review_required / attribution_present / no_significant_overlap."""
    if not request.text or not request.text.strip():
        return _phase3_error_response(
            Phase3Error(
                code="empty_text",
                message="No text was supplied for assessment.",
                component="plagiarism_api",
                retryable=False,
            )
        )

    async with AsyncSessionLocal() as db:
        similarity = SimilarityService(
            db_session=db,
            embedding_service=EmbeddingService(),
            vectorize_service=VectorizeService(),
        )
        service = PlagiarismAssessmentService(similarity_service=similarity)
        try:
            assessment = await service.assess(
                actor,
                request.text,
                min_score=request.min_score,
                exclude_document_ids=request.exclude_document_ids,
            )
        except Phase3Error as exc:
            return _phase3_error_response(exc)

    return PlagiarismResponseSchema(
        status=assessment.status,
        passages=[
            PlagiarismPassageSchema(
                assessment=item.assessment,
                reason=item.reason,
                quoted=item.quoted,
                cited=item.cited,
                submitted_excerpt=item.submitted_excerpt,
                matches=[_match_schema(m) for m in item.matches],
            )
            for item in assessment.passages
        ],
        matched_source_count=assessment.matched_source_count,
        limitations=assessment.limitations,
        disclaimer=assessment.disclaimer,
    )


@router.post(
    "/ai-writing/detect",
    response_model=AIWritingResponseSchema,
    summary="AI-writing detection (returns 'unavailable' unless a real model is present)",
)
async def detect_ai_writing(
    request: AIWritingDetectRequest,
    _token: str = Depends(get_internal_service_token),
    actor: ActorContext = Depends(get_actor_context),
    trace_id: str = Depends(get_trace_id),
):
    """Run segmented detection, or report why detection could not run.

    A 503 is returned when the detector itself is unavailable, so a caller can
    never mistake a missing capability for a successful analysis.
    """
    service = get_detection_service()
    result = service.detect(request.text)

    payload = AIWritingResponseSchema(
        status=result.status,
        assessment=result.assessment,
        ai_probability=result.ai_probability,
        confidence=result.confidence,
        segments=[
            AIWritingSegmentSchema(
                text=segment.text,
                start_char=segment.start_char,
                end_char=segment.end_char,
                ai_probability=segment.ai_probability,
                band=segment.band,
            )
            for segment in result.segments
        ],
        model_id=result.model_id,
        model_version=result.model_version,
        calibration=result.calibration,
        limitations=result.limitations,
        blocker=result.blocker,
        disclaimer=result.disclaimer,
    )

    if result.status == "unavailable":
        # Django maps `message`/`code` through to the client, so the caller can
        # tell "detector missing" apart from any other 503 and show the reason.
        body = payload.model_dump()
        body["code"] = "detector_unavailable"
        body["message"] = result.blocker or "AI-writing detector is unavailable."
        return JSONResponse(status_code=503, content=body)
    return payload
