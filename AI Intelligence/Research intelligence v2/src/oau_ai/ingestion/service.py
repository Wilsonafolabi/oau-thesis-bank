"""Ingestion service — orchestrates the document processing pipeline.

Pipeline: PDF upload → extraction → chunking → embedding → Vectorize upsert
→ job completion. Job states are persisted in PostgreSQL. Canonical chunk
text and provenance live in PostgreSQL; Vectorize stores only embeddings +
retrieval metadata.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.middleware import ActorContext
from ..config import get_settings
from ..db.models import (
    AIDocument,
    AIChunk,
    AIJob,
    AIPage,
    JobStatus,
    ProcessingStage,
)
from ..db.session import get_session_factory as AsyncSessionLocal
from ..document_processing.chunking import chunk_document_pages
from ..document_processing.extraction import (
    ExtractedPage,
    PDFExtractionError,
    extract_pdf_pages,
)
from ..embeddings.service import EmbeddingService
from ..embeddings.vectorize import VectorizeService
from ..errors import (
    ConfigurationError,
    Phase3Error,
    ProviderUnavailableError,
    RetrievalError,
)

logger = logging.getLogger("oau_ai.ingestion")


class IngestionService:
    """Orchestrates document ingestion from upload to Vectorize indexing."""

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_service: Optional[EmbeddingService] = None,
        vectorize_service: Optional[VectorizeService] = None,
        storage_base_path: Optional[str] = None,
    ) -> None:
        self.db = db_session
        self.embedding_service = embedding_service or EmbeddingService()
        self.vectorize_service = vectorize_service or VectorizeService()
        self.storage_base_path = Path(
            storage_base_path or os.getenv("STORAGE_BASE_PATH", "./storage/documents")
        )
        self.storage_base_path.mkdir(parents=True, exist_ok=True)

    async def create_document_and_job(
        self,
        actor_context: ActorContext,
        file_path: str,
        filename: str,
        backend_thesis_id: str,
        access_level: str = "private",
        thesis_metadata: Optional[dict] = None,
    ) -> tuple:
        """Create a document record and ingestion job. Returns (document, job)."""

        # Read file bytes and compute hash.
        file_bytes = Path(file_path).read_bytes()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        existing = (
            await self.db.execute(
                select(AIDocument).where(
                    AIDocument.backend_thesis_id == backend_thesis_id
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            latest_job = (
                await self.db.execute(
                    select(AIJob)
                    .where(AIJob.document_id == existing.id)
                    .order_by(AIJob.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            # A live or already-indexed document must not be re-ingested: that
            # would duplicate chunks and Vectorize points. Only a failed
            # ingestion may be retried, so users can recover from errors.
            if latest_job is None or latest_job.status != JobStatus.FAILED:
                raise Phase3Error(
                    code="document_already_exists",
                    message=(
                        f"Document {backend_thesis_id} already exists and is not "
                        "in a failed state, so it cannot be re-ingested."
                    ),
                    component="ingestion_service",
                    trace_id=actor_context.trace_id,
                )

            if (
                existing.backend_user_id != actor_context.user_id
                and "admin" not in actor_context.roles
            ):
                raise Phase3Error(
                    code="access_denied",
                    message="You do not have access to this document.",
                    component="ingestion_service",
                    trace_id=actor_context.trace_id,
                    retryable=False,
                )

            return await self._reingest_existing(
                document=existing,
                actor_context=actor_context,
                file_bytes=file_bytes,
                file_hash=file_hash,
                filename=filename,
                access_level=access_level,
                thesis_metadata=thesis_metadata,
            )

        # Save file to storage.
        document_id = str(uuid.uuid4())
        storage_dir = self.storage_base_path
        saved_path = storage_dir / f"{document_id}.pdf"
        saved_path.write_bytes(file_bytes)

        document = AIDocument(
            id=document_id,
            backend_thesis_id=backend_thesis_id,
            backend_user_id=actor_context.user_id,
            object_key=str(saved_path),
            file_hash=file_hash,
            access_level=access_level,
            embedding_status="pending",
            thesis_metadata={
                "title": filename,
                "uploaded_by": actor_context.user_id,
                "department": actor_context.department,
                "request_id": actor_context.trace_id,
                **(thesis_metadata or {}),
            },
        )
        self.db.add(document)

        job_id = str(uuid.uuid4())
        job = AIJob(
            id=job_id,
            document_id=document_id,
            job_type="document_ingestion",
            stage=ProcessingStage.EXTRACTION,
            status=JobStatus.PENDING,
            attempts=0,
            max_attempts=3,
        )
        self.db.add(job)

        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            saved_path.unlink(missing_ok=True)
            logger.exception("Could not persist document and job.")
            raise Phase3Error(
                code="document_persistence_failed",
                message="Document persistence is unavailable; no ingestion job was queued.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
                retryable=True,
            )

        return document, job

    async def _reingest_existing(
        self,
        document: AIDocument,
        actor_context: ActorContext,
        file_bytes: bytes,
        file_hash: str,
        filename: str,
        access_level: str,
        thesis_metadata: Optional[dict],
    ) -> tuple:
        """Replace a failed document's derived data and queue a fresh job.

        Existing chunks, pages, jobs and Vectorize points are purged first so
        a retry cannot leave duplicate vectors behind.
        """
        await self._purge_derived_data(document)

        saved_path = self.storage_base_path / f"{document.id}.pdf"
        saved_path.write_bytes(file_bytes)

        document.object_key = str(saved_path)
        document.file_hash = file_hash
        document.access_level = access_level
        document.backend_user_id = actor_context.user_id
        document.embedding_status = "pending"
        document.thesis_metadata = {
            "title": filename,
            "uploaded_by": actor_context.user_id,
            "department": actor_context.department,
            "request_id": actor_context.trace_id,
            "reingested": True,
            **(thesis_metadata or {}),
        }

        job = AIJob(
            id=str(uuid.uuid4()),
            document_id=document.id,
            job_type="document_ingestion",
            stage=ProcessingStage.EXTRACTION,
            status=JobStatus.PENDING,
            attempts=0,
            max_attempts=3,
        )
        self.db.add(job)

        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            logger.exception("Could not queue a retry for document %s.", document.id)
            raise Phase3Error(
                code="document_persistence_failed",
                message="Could not queue a re-ingestion job.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
                retryable=True,
            )

        return document, job

    async def _purge_derived_data(self, document: AIDocument) -> None:
        """Delete chunks, pages, jobs and Vectorize points for a document."""
        point_ids = await self._collect_point_ids(document.id)

        await self.db.execute(
            sa_delete(AIChunk).where(AIChunk.document_id == document.id)
        )
        await self.db.execute(
            sa_delete(AIPage).where(AIPage.document_id == document.id)
        )
        await self.db.execute(
            sa_delete(AIJob).where(AIJob.document_id == document.id)
        )
        await self.db.commit()

        await self._delete_vectors(point_ids)

    async def _collect_point_ids(self, document_id: str) -> List[str]:
        rows = await self.db.execute(
            select(AIChunk.vectorize_point_id).where(
                AIChunk.document_id == document_id,
                AIChunk.vectorize_point_id.isnot(None),
            )
        )
        return [point_id for point_id in rows.scalars().all() if point_id]

    async def _delete_vectors(self, point_ids: List[str]) -> None:
        """Remove vectors from the index, logging rather than failing callers.

        Database rows are already gone by the time this runs, so a transient
        Vectorize error degrades to orphaned points that retrieval can no
        longer resolve, not to leaked content.
        """
        if not point_ids:
            return
        try:
            await self.vectorize_service.adelete(point_ids)
        except Exception as exc:
            logger.warning(
                "Could not delete %d Vectorize point(s): %s", len(point_ids), exc
            )

    @staticmethod
    def _assert_upsert_confirmed(response: Any, expected: int) -> None:
        """Refuse to report success unless Vectorize confirms the upsert."""
        if not isinstance(response, dict):
            return
        if response.get("success") is False:
            raise ProviderUnavailableError(
                message=f"Vectorize rejected the upsert: {response.get('errors') or response}",
                component="ingestion_service",
            )
        result = response.get("result")
        result = result if isinstance(result, dict) else {}
        count = response.get("count", result.get("count"))
        if isinstance(count, int) and count < expected:
            raise ProviderUnavailableError(
                message=(
                    f"Vectorize confirmed only {count} of {expected} vectors; "
                    "the document is not fully indexed."
                ),
                component="ingestion_service",
            )

    async def process_job(
        self,
        job_id: str,
        actor_context: ActorContext,
    ) -> AIJob:
        """Process a pending ingestion job through the full pipeline.

        Stages: extraction → chunking → embedding → vectorize → complete.
        On failure, job status is set to FAILED with error details.
        Never marks a job SUCCESS unless all stages completed.
        """
        job = await self.db.get(AIJob, job_id)
        if not job:
            raise Phase3Error(
                code="job_not_found",
                message=f"Ingestion job {job_id} not found.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
            )

        document = await self.db.get(AIDocument, job.document_id)
        if not document:
            raise Phase3Error(
                code="document_not_found",
                message=f"Document {job.document_id} not found.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
            )

        # Verify access — only the document owner or admin can process.
        if (
            document.backend_user_id != actor_context.user_id
            and "admin" not in actor_context.roles
        ):
            raise Phase3Error(
                code="access_denied",
                message="You do not have access to this document.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
                retryable=False,
            )

        job.attempts += 1
        job.status = JobStatus.PROCESSING
        await self.db.commit()

        try:
            # Stage 1: Extraction
            job.stage = ProcessingStage.EXTRACTION
            await self.db.commit()
            pages = await self._extract_pages(document)

            if not any(page.text for page in pages):
                raise RetrievalError(
                    code="no_extractable_text",
                    message=(
                        f"No extractable text in {len(pages)} page(s). The PDF is "
                        "empty or scanned; OCR is not implemented, so it cannot "
                        "be indexed."
                    ),
                    component="ingestion_service",
                )

            # Stage 2: Chunking
            job.stage = ProcessingStage.CHUNKING
            await self.db.commit()
            chunks = await self._chunk_pages(document, pages)

            if not chunks:
                raise RetrievalError(
                    code="no_indexable_content",
                    message=(
                        "The document produced no text chunks, so there is "
                        "nothing to index."
                    ),
                    component="ingestion_service",
                )

            # Stage 3: Embedding
            job.stage = ProcessingStage.EMBEDDING
            await self.db.commit()
            embedded_chunks = await self._embed_chunks(document, chunks)

            if not embedded_chunks:
                raise RetrievalError(
                    code="embedding_produced_no_vectors",
                    message=(
                        "Embedding produced no vectors for this document, so "
                        "nothing can be indexed."
                    ),
                    component="ingestion_service",
                )

            # Stage 4: Vectorize upsert
            job.stage = ProcessingStage.VECTORIZE
            await self.db.commit()
            await self._upsert_to_vectorize(document, embedded_chunks)

            # Stage 5: Complete
            document.embedding_status = "completed"
            job.stage = ProcessingStage.COMPLETE
            job.status = JobStatus.SUCCESS
            await self.db.commit()

            logger.info(
                "Ingestion job %s completed: document=%s pages=%d chunks=%d",
                job_id,
                document.id,
                len(pages),
                len(embedded_chunks),
            )
            return job

        except Exception as exc:
            # Never mark SUCCESS on failure.
            document.embedding_status = "failed"
            job.error_stage = job.stage.value
            job.stage = ProcessingStage.FAILED
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            await self.db.commit()
            logger.exception(
                "Ingestion job %s failed at stage %s: %s",
                job_id,
                job.stage.value,
                exc,
            )
            raise

    async def _extract_pages(
        self, document: AIDocument
    ) -> List[ExtractedPage]:
        """Extract text from the stored PDF."""
        file_path = Path(document.object_key)
        if not file_path.exists():
            raise RetrievalError(
                code="source_file_missing",
                message=f"Source PDF not found: {document.object_key}",
                component="ingestion_service",
            )

        try:
            # pypdf is CPU-bound and synchronous; keep it off the event loop.
            pages = await asyncio.to_thread(extract_pdf_pages, str(file_path))
        except PDFExtractionError as exc:
            raise RetrievalError(
                code="pdf_extraction_failed",
                message=str(exc),
                component="ingestion_service",
            ) from exc

        # Persist pages.
        for page in pages:
            db_page = AIPage(
                document_id=document.id,
                page_number=page.page_number,
                is_scanned=page.is_scanned,
                text_content=page.text,
                char_offset_start=page.char_offset_start,
                char_offset_end=page.char_offset_end,
            )
            self.db.add(db_page)

        await self.db.commit()
        logger.info(
            "Extracted %d pages for document %s", len(pages), document.id
        )
        return pages

    async def _chunk_pages(
        self, document: AIDocument, pages: List[ExtractedPage]
    ) -> List[dict]:
        """Chunk all pages and persist chunk records."""
        import os

        chunk_size = int(os.environ.get("CHUNK_TOKEN_SIZE", "512"))
        overlap = int(os.environ.get("CHUNK_TOKEN_OVERLAP", "50"))

        pages_text = {
            p.page_number: p.text for p in pages if p.text
        }

        chunk_data_list = chunk_document_pages(
            pages_text=pages_text,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        persisted_chunks: List[dict] = []
        for chunk_data in chunk_data_list:
            # Find the page record for this chunk.
            page = await self.db.execute(
                select(AIPage).where(
                    AIPage.document_id == document.id,
                    AIPage.page_number == chunk_data.page_number,
                )
            )
            db_page = page.scalar_one_or_none()

            db_chunk = AIChunk(
                document_id=document.id,
                page_id=db_page.id if db_page else None,
                chunk_index=chunk_data.chunk_index,
                text=chunk_data.text,
                token_count=chunk_data.token_count,
                is_embedded=False,
            )
            self.db.add(db_chunk)

            persisted_chunks.append(
                {
                    "chunk_index": chunk_data.chunk_index,
                    "text": chunk_data.text,
                    "page_number": chunk_data.page_number,
                    "char_offset_start": chunk_data.char_offset_start,
                    "char_offset_end": chunk_data.char_offset_end,
                    "db_chunk": db_chunk,
                }
            )

        await self.db.commit()
        logger.info(
            "Created %d chunks for document %s",
            len(persisted_chunks),
            document.id,
        )
        return persisted_chunks

    async def _embed_chunks(
        self, document: AIDocument, chunks: List[dict]
    ) -> List[dict]:
        """Generate embeddings for all chunks and update chunk records."""
        if not chunks:
            return []

        texts = [c["text"] for c in chunks]
        # Embedding inference is synchronous; run it in a worker thread.
        results = await asyncio.to_thread(
            self.embedding_service.embed_texts, texts
        )

        embedded_chunks: List[dict] = []
        for chunk_info, embedding_result in zip(chunks, results):
            db_chunk: AIChunk = chunk_info["db_chunk"]
            db_chunk.embedding_model = embedding_result.model_name
            db_chunk.embedding_version = embedding_result.model_version
            db_chunk.is_embedded = True
            embedded_chunks.append(
                {
                    **chunk_info,
                    "vector": embedding_result.vector,
                    "model_name": embedding_result.model_name,
                    "model_version": embedding_result.model_version,
                }
            )

        await self.db.commit()
        logger.info(
            "Embedded %d chunks for document %s",
            len(embedded_chunks),
            document.id,
        )
        return embedded_chunks

    async def _upsert_to_vectorize(
        self, document: AIDocument, embedded_chunks: List[dict]
    ) -> None:
        """Upsert embedded chunks to Cloudflare Vectorize."""
        if not embedded_chunks:
            return

        if not self.vectorize_service.is_configured():
            raise ConfigurationError(
                code="vectorize_not_configured",
                message=(
                    "Cloudflare Vectorize is not configured. Cannot complete "
                    "ingestion without vector index."
                ),
                component="ingestion_service",
            )

        vectors = []
        for chunk_info in embedded_chunks:
            db_chunk: AIChunk = chunk_info["db_chunk"]
            point_id = str(uuid.uuid4())
            db_chunk.vectorize_point_id = point_id

            vectors.append(
                {
                    "id": point_id,
                    "values": chunk_info["vector"],
                    "metadata": {
                        "document_id": document.id,
                        "backend_thesis_id": document.backend_thesis_id,
                        "chunk_id": db_chunk.id,
                        "page_number": chunk_info["page_number"],
                        "chunk_index": chunk_info["chunk_index"],
                        "access_level": document.access_level,
                        "backend_user_id": document.backend_user_id,
                    },
                }
            )

        response = await self.vectorize_service.aupsert(vectors)
        self._assert_upsert_confirmed(response, expected=len(vectors))
        await self.db.commit()
        logger.info(
            "Upserted %d vectors to Vectorize for document %s",
            len(vectors),
            document.id,
        )

    async def get_job_status(
        self, job_id: str, actor_context: ActorContext
    ) -> AIJob:
        """Get job status with access control."""
        job = await self.db.get(AIJob, job_id)
        if not job:
            raise Phase3Error(
                code="job_not_found",
                message=f"Ingestion job {job_id} not found.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
            )

        document = await self.db.get(AIDocument, job.document_id)
        if not document:
            raise Phase3Error(
                code="document_not_found",
                message=f"Document {job.document_id} not found.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
            )

        if (
            document.backend_user_id != actor_context.user_id
            and "admin" not in actor_context.roles
        ):
            raise Phase3Error(
                code="access_denied",
                message="You do not have access to this job.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
                retryable=False,
            )

        return job

    async def delete_document(
        self,
        backend_thesis_id: str,
        actor_context: ActorContext,
    ) -> None:
        """Delete a document and all its pages, chunks, and jobs.

        Cascade cleanup removes derived data. Vectorize point IDs are
        recorded but Vectorize deletion is best-effort (Vectorize API
        delete by filter is called if configured).
        """
        document = await self.db.execute(
            select(AIDocument).where(
                AIDocument.backend_thesis_id == backend_thesis_id
            )
        )
        document = document.scalar_one_or_none()
        if not document:
            raise Phase3Error(
                code="document_not_found",
                message=f"Document {backend_thesis_id} not found.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
            )

        if (
            document.backend_user_id != actor_context.user_id
            and "admin" not in actor_context.roles
        ):
            raise Phase3Error(
                code="access_denied",
                message="You do not have access to this document.",
                component="ingestion_service",
                trace_id=actor_context.trace_id,
                retryable=False,
            )

        # Collect Vectorize point ids before the rows cascade away.
        point_ids = await self._collect_point_ids(document.id)

        # Delete source file.
        file_path = Path(document.object_key)
        if file_path.exists():
            file_path.unlink(missing_ok=True)

        # Delete from database (cascades to pages, chunks, jobs).
        await self.db.delete(document)
        await self.db.commit()

        await self._delete_vectors(point_ids)

        logger.info(
            "Deleted document %s, %d vector point(s) and all derived data",
            backend_thesis_id,
            len(point_ids),
        )
