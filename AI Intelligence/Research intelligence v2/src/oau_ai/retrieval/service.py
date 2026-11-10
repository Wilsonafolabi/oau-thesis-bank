"""Authorized retrieval boundary.

Enforces thesis access rules before returning chunk text or provenance.
The AI service never trusts browser-supplied user IDs, roles, or department
claims. Access is validated against the actor context issued by Django and
the access level stored on the document record.

Supports hybrid retrieval: dense vector search (Cloudflare Vectorize) fused
with lexical search (PostgreSQL full-text search) using Reciprocal Rank
Fusion (RRF).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.middleware import ActorContext
from ..db.models import AIDocument, AIChunk, AIPage
from ..db.session import get_session_factory as AsyncSessionLocal
from ..errors import Phase3Error, RetrievalError

logger = logging.getLogger("oau_ai.retrieval")

RRF_K = 60  # Reciprocal Rank Fusion constant


@dataclass
class AuthorizedChunk:
    """A chunk the caller is authorized to see."""

    chunk_id: str
    document_id: str
    backend_thesis_id: str
    text: str
    page_number: Optional[int]
    section: Optional[str]
    chunk_index: int
    access_level: str
    provenance: dict


@dataclass
class RetrievedChunk:
    """A chunk retrieved with scores and source attribution."""

    chunk_id: str
    document_id: str
    backend_thesis_id: str
    text: str
    page_number: Optional[int]
    section: Optional[str]
    chunk_index: int
    access_level: str
    provenance: dict
    dense_score: Optional[float] = None
    lexical_score: Optional[float] = None
    fused_score: Optional[float] = None
    retrieval_source: str = "hybrid"  # "dense", "lexical", "hybrid"


@dataclass
class DocumentAccess:
    """Document-level access information."""

    document_id: str
    backend_thesis_id: str
    access_level: str
    title: Optional[str]
    can_view: bool
    reason: Optional[str] = None


def rrf_fuse(
    ranked_lists: List[List[dict]], k: int = RRF_K
) -> List[tuple[str, float]]:
    """Fuse multiple ranked lists using Reciprocal Rank Fusion.

    Each item must include a ``chunk_id`` key. Returns a list of
    ``(chunk_id, fused_score)`` tuples sorted by descending score.

    Args:
        ranked_lists: List of ranked result lists, each containing dicts
            with a ``chunk_id`` key.
        k: RRF constant (default 60).

    Returns:
        Sorted list of (chunk_id, score) tuples.
    """
    scores: dict[str, float] = {}
    for ranked_list in ranked_lists:
        # A chunk appearing twice in the same ranked list must not receive a
        # double contribution, which would distort the fused ranking.
        seen_in_list: set[str] = set()
        for rank, item in enumerate(ranked_list):
            chunk_id = item.get("chunk_id") or item.get("id")
            if chunk_id is None or chunk_id in seen_in_list:
                continue
            seen_in_list.add(chunk_id)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _build_access_conditions(
    actor_context: ActorContext,
) -> object:
    """Build SQLAlchemy access conditions for the actor."""
    access_conditions = or_(
        AIDocument.access_level == "public",
        AIDocument.backend_user_id == actor_context.user_id,
    )
    if "admin" in actor_context.roles:
        access_conditions = or_(
            AIDocument.access_level.in_(["public", "restricted", "private"]),
            AIDocument.backend_user_id == actor_context.user_id,
        )
    return access_conditions


def _chunk_to_authorized(
    chunk: AIChunk,
    document: AIDocument,
    page: Optional[AIPage] = None,
) -> AuthorizedChunk:
    """Convert ORM rows to an AuthorizedChunk with provenance."""
    provenance = {
        "document_id": document.id,
        "source_file": (document.thesis_metadata or {}).get(
            "title", document.backend_thesis_id
        ),
        "access_classification": document.access_level,
        "created_at": document.created_at.isoformat()
        if document.created_at
        else None,
    }
    if page:
        provenance["page_number"] = page.page_number
        provenance["char_offset_start"] = page.char_offset_start
        provenance["char_offset_end"] = page.char_offset_end
        provenance["section"] = None
        provenance["is_scanned"] = page.is_scanned

    return AuthorizedChunk(
        chunk_id=chunk.id,
        document_id=document.id,
        backend_thesis_id=document.backend_thesis_id,
        text=chunk.text,
        page_number=page.page_number if page else None,
        section=None,
        chunk_index=chunk.chunk_index,
        access_level=document.access_level,
        provenance=provenance,
    )


class RetrievalService:
    """Retrieves authorized chunks and provenance for a given actor context."""

    def __init__(self, db_session: Optional[AsyncSession] = None) -> None:
        self.db = db_session

    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[AsyncSession, None]:
        if self.db is not None:
            yield self.db
        else:
            # AsyncSessionLocal is get_session_factory, which returns an
            # async_sessionmaker; call it twice to obtain a session.
            async with AsyncSessionLocal()() as session:
                yield session

    async def check_document_access(
        self,
        backend_thesis_id: str,
        actor_context: ActorContext,
    ) -> DocumentAccess:
        """Check whether the actor can view a document.

        Access rules (from Phase 2 Thesis.can_view):
        - Public + published: anyone can view
        - Owner: always can view
        - Admin: always can view
        - Otherwise: denied
        """
        async with self._get_session() as session:
            result = await session.execute(
                select(AIDocument).where(
                    AIDocument.backend_thesis_id == backend_thesis_id
                )
            )
            document = result.scalar_one_or_none()

        if not document:
            return DocumentAccess(
                document_id="",
                backend_thesis_id=backend_thesis_id,
                access_level="unknown",
                title=None,
                can_view=False,
                reason="Document not found.",
            )

        title = (document.thesis_metadata or {}).get("title")

        # Access classification evaluated before retrieval (§1.1 L8).
        if document.access_level == "public":
            can_view = True
            reason = None
        elif document.backend_user_id == actor_context.user_id:
            can_view = True
            reason = None
        elif "admin" in actor_context.roles:
            can_view = True
            reason = None
        else:
            can_view = False
            reason = (
                f"Access denied: document access_level={document.access_level}, "
                "you are not the owner or an admin."
            )

        return DocumentAccess(
            document_id=document.id,
            backend_thesis_id=document.backend_thesis_id,
            access_level=document.access_level,
            title=title,
            can_view=can_view,
            reason=reason,
        )

    async def get_authorized_chunks(
        self,
        actor_context: ActorContext,
        document_ids: Optional[List[str]] = None,
        limit: int = 10,
        access_levels: Optional[List[str]] = None,
    ) -> List[AuthorizedChunk]:
        """Retrieve chunks the actor is authorized to see.

        Enforces access at the document level before returning any chunk
        text or provenance. Never returns chunks from documents the actor
        cannot view.
        """
        async with self._get_session() as session:
            # Build base query: only documents the actor can access.
            access_conditions = or_(
                AIDocument.access_level == "public",
                AIDocument.backend_user_id == actor_context.user_id,
            )
            if "admin" in actor_context.roles:
                # Admins can see everything.
                access_conditions = or_(
                    AIDocument.access_level.in_(["public", "restricted", "private"]),
                    AIDocument.backend_user_id == actor_context.user_id,
                )

            query = (
                select(AIChunk, AIDocument)
                .join(AIDocument, AIChunk.document_id == AIDocument.id)
                .where(access_conditions)
            )

            if document_ids:
                query = query.where(AIDocument.id.in_(document_ids))

            if access_levels:
                query = query.where(AIDocument.access_level.in_(access_levels))

            query = query.limit(limit)

            result = await session.execute(query)
            rows = result.all()

        chunks: List[AuthorizedChunk] = []
        for chunk, document in rows:
            # Provenance from stored page-level data.
            provenance = {
                "document_id": document.id,
                "source_file": (document.thesis_metadata or {}).get(
                    "title", document.backend_thesis_id
                ),
                "access_classification": document.access_level,
                "created_at": document.created_at.isoformat()
                if document.created_at
                else None,
            }

            # Add page-level provenance if available.
            if chunk.page_id:
                async with self._get_session() as session:
                    page_result = await session.execute(
                        select(AIPage).where(AIPage.id == chunk.page_id)
                    )
                    page = page_result.scalar_one_or_none()
                if page:
                    provenance["page_number"] = page.page_number
                    provenance["char_offset_start"] = page.char_offset_start
                    provenance["char_offset_end"] = page.char_offset_end
                    provenance["section"] = None  # section stored on chunk
                    provenance["is_scanned"] = page.is_scanned

            chunks.append(
                AuthorizedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    backend_thesis_id=document.backend_thesis_id,
                    text=chunk.text,
                    page_number=page.page_number if chunk.page_id else None,
                    section=None,
                    chunk_index=chunk.chunk_index,
                    access_level=document.access_level,
                    provenance=provenance,
                )
            )

        return chunks

    async def resolve_authorized_chunks(
        self,
        chunk_ids: List[str],
        actor_context: ActorContext,
    ) -> tuple[dict, List[str]]:
        """Resolve chunk IDs to authorized chunks using one authoritative query.

        Vectorize metadata is only a hint, never an authority. This re-reads
        the database and applies document access conditions there, so a chunk
        is resolvable only when the row still exists AND the actor may see its
        document.

        Returns:
            (resolved_by_chunk_id, unresolved_chunk_ids). An unresolved ID may
            be a deleted chunk, a deleted document, or an access denial; callers
            must treat all three identically and never use them as evidence.
        """
        if not chunk_ids:
            return {}, []

        access_conditions = _build_access_conditions(actor_context)

        async with self._get_session() as session:
            result = await session.execute(
                select(AIChunk, AIDocument, AIPage)
                .join(AIDocument, AIChunk.document_id == AIDocument.id)
                .outerjoin(AIPage, AIChunk.page_id == AIPage.id)
                .where(AIChunk.id.in_(chunk_ids))
                .where(access_conditions)
            )
            rows = result.all()

        resolved: dict = {}
        for chunk, document, page in rows:
            resolved[chunk.id] = _chunk_to_authorized(chunk, document, page)

        unresolved = [chunk_id for chunk_id in chunk_ids if chunk_id not in resolved]
        return resolved, unresolved

    async def get_chunk_by_id(
        self,
        chunk_id: str,
        actor_context: ActorContext,
    ) -> Optional[AuthorizedChunk]:
        """Get a single chunk by ID, only if the actor can access its document."""
        async with self._get_session() as session:
            result = await session.execute(
                select(AIChunk, AIDocument)
                .join(AIDocument, AIChunk.document_id == AIDocument.id)
                .where(AIChunk.id == chunk_id)
            )
            row = result.first()

        if not row:
            return None

        chunk, document = row

        # Enforce access.
        access = await self.check_document_access(
            document.backend_thesis_id, actor_context
        )
        if not access.can_view:
            return None

        provenance = {
            "document_id": document.id,
            "source_file": (document.thesis_metadata or {}).get(
                "title", document.backend_thesis_id
            ),
            "access_classification": document.access_level,
        }

        return AuthorizedChunk(
            chunk_id=chunk.id,
            document_id=document.id,
            backend_thesis_id=document.backend_thesis_id,
            text=chunk.text,
            page_number=None,
            section=None,
            chunk_index=chunk.chunk_index,
            access_level=document.access_level,
            provenance=provenance,
        )

    async def verify_access_before_retrieval(
        self,
        actor_context: ActorContext,
        requested_document_ids: List[str],
    ) -> List[str]:
        """Verify the actor can access all requested documents.

        Returns the list of accessible document IDs. Raises Phase3Error if
        none are accessible.
        """
        accessible: List[str] = []
        for doc_id in requested_document_ids:
            # doc_id could be a backend_thesis_id or internal document ID.
            # Try both.
            access = await self.check_document_access(doc_id, actor_context)
            if not access.can_view:
                # Try as internal document ID.
                access2 = await self._check_internal_id(doc_id, actor_context)
                if access2 and access2.can_view:
                    accessible.append(access2.document_id)
                continue
            accessible.append(access.document_id or access.backend_thesis_id)

        if not accessible:
            raise Phase3Error(
                code="no_accessible_documents",
                message="You do not have access to any of the requested documents.",
                component="retrieval_service",
                trace_id=actor_context.trace_id,
                retryable=False,
            )

        return accessible

    async def _check_internal_id(
        self, internal_id: str, actor_context: ActorContext
    ) -> Optional[object]:
        """Check access by internal document ID."""
        from types import SimpleNamespace

        async with self._get_session() as session:
            result = await session.execute(
                select(AIDocument).where(AIDocument.id == internal_id)
            )
            document = result.scalar_one_or_none()

        if not document:
            return None

        if (
            document.access_level == "public"
            or document.backend_user_id == actor_context.user_id
            or "admin" in actor_context.roles
        ):
            return SimpleNamespace(
                can_view=True,
                document_id=document.id,
                reason=None,
            )
        return SimpleNamespace(can_view=False, document_id=document.id, reason="denied")

    async def lexical_search(
        self,
        actor_context: ActorContext,
        query: str,
        document_ids: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[RetrievedChunk]:
        """Lexical search using PostgreSQL full-text search.

        Searches chunk text with PostgreSQL's ``to_tsvector`` / ``plainto_tsquery``
        against the ``ai_chunks.text`` column. Access filtering is applied
        at the document level before any results are returned.

        Args:
            actor_context: Django-issued actor context.
            query: Natural language search query.
            document_ids: Optional list of internal document IDs to restrict search.
            limit: Maximum number of results.

        Returns:
            List of RetrievedChunk with lexical scores (RRF component).
        """
        if not query or not query.strip():
            return []

        access_conditions = _build_access_conditions(actor_context)

        async with self._get_session() as session:
            query_base = (
                select(AIChunk, AIDocument)
                .join(AIDocument, AIChunk.document_id == AIDocument.id)
                .where(access_conditions)
                .where(
                    func.to_tsvector("english", AIChunk.text).op("@@")(
                        func.plainto_tsquery("english", query.strip())
                    )
                )
            )

            if document_ids:
                query_base = query_base.where(AIDocument.id.in_(document_ids))

            query_base = query_base.limit(limit)

            result = await session.execute(query_base)
            rows = result.all()

        chunks: List[RetrievedChunk] = []
        for rank, (chunk, document) in enumerate(rows):
            page = None
            if chunk.page_id:
                async with self._get_session() as session:
                    page_result = await session.execute(
                        select(AIPage).where(AIPage.id == chunk.page_id)
                    )
                    page = page_result.scalar_one_or_none()

            authorized = _chunk_to_authorized(chunk, document, page)
            chunks.append(
                RetrievedChunk(
                    chunk_id=authorized.chunk_id,
                    document_id=authorized.document_id,
                    backend_thesis_id=authorized.backend_thesis_id,
                    text=authorized.text,
                    page_number=authorized.page_number,
                    section=authorized.section,
                    chunk_index=authorized.chunk_index,
                    access_level=authorized.access_level,
                    provenance=dict(authorized.provenance),
                    lexical_score=1.0 / (RRF_K + rank + 1),
                    retrieval_source="lexical",
                )
            )

        return chunks

    async def hybrid_retrieve(
        self,
        actor_context: ActorContext,
        query: str,
        query_vector: List[float],
        vectorize_results: List[dict],
        document_ids: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[RetrievedChunk]:
        """Hybrid retrieval: fuse dense Vectorize results with lexical search.

        Combines:
        1. Dense semantic results from Cloudflare Vectorize (already filtered
           by document access at the Vectorize metadata level).
        2. Lexical full-text search results from PostgreSQL.

        Rankings are fused using Reciprocal Rank Fusion (RRF). Results are
        deduplicated by chunk_id, with document-level access enforcement
        applied to both result sets before fusion.

        Args:
            actor_context: Django-issued actor context.
            query: Natural language question for lexical search.
            query_vector: Embedding vector for dense search (used for logging).
            vectorize_results: Raw Vectorize match results with metadata.
            document_ids: Optional list of internal document IDs to restrict search.
            top_k: Maximum number of fused results to return.

        Returns:
            List of RetrievedChunk sorted by fused score, access-enforced.
        """
        # Build dense result list from Vectorize matches. Access is enforced
        # later when chunks are fetched via get_authorized_chunks / get_chunk_by_id,
        # which re-verify document-level access before returning any text.
        dense_items: List[dict] = []
        scoped_document_ids = set(document_ids or [])
        for match in vectorize_results:
            metadata = match.get("metadata", {})
            document_id = metadata.get("document_id", "")
            if scoped_document_ids and document_id not in scoped_document_ids:
                continue
            chunk_id = metadata.get("chunk_id")
            score = match.get("score", 0.0)
            if chunk_id:
                dense_items.append(
                    {
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "score": score,
                        "retrieval_source": "dense",
                    }
                )

        # Build lexical result list (access-enforced by SQL query).
        lexical_results = await self.lexical_search(
            actor_context=actor_context,
            query=query,
            document_ids=document_ids,
            limit=top_k * 2,  # Fetch more for better fusion coverage
        )
        lexical_items: List[dict] = []
        for rc in lexical_results:
            lexical_items.append(
                {
                    "chunk_id": rc.chunk_id,
                    "document_id": rc.document_id,
                    "score": rc.lexical_score or 0.0,
                    "retrieval_source": "lexical",
                }
            )

        # Fuse with RRF.
        fused = rrf_fuse([dense_items, lexical_items], k=RRF_K)
        if not fused:
            return []

        # Re-read authoritative records for every fused candidate. Vectorize
        # metadata is not trusted: orphaned points, deleted documents and
        # documents the actor may not see all resolve to nothing and are
        # dropped before reranking or the LLM ever sees them.
        candidate_ids = [
            chunk_id for chunk_id, _ in fused[: max(top_k * 4, top_k)]
        ]
        resolved, unresolved = await self.resolve_authorized_chunks(
            candidate_ids, actor_context
        )
        if unresolved:
            logger.info(
                "retrieval.unresolved_results_pruned unresolved=%d candidates=%d",
                len(unresolved),
                len(candidate_ids),
            )

        dense_scores = {item["chunk_id"]: item["score"] for item in dense_items}
        lexical_by_id = {rc.chunk_id: rc for rc in lexical_results}

        final_chunks: List[RetrievedChunk] = []
        for chunk_id, fused_score in fused:
            if len(final_chunks) >= top_k:
                break

            authorized = resolved.get(chunk_id)
            if authorized is None:
                continue
            if (
                scoped_document_ids
                and authorized.document_id not in scoped_document_ids
            ):
                continue

            in_dense = chunk_id in dense_scores
            in_lexical = chunk_id in lexical_by_id
            if in_dense and in_lexical:
                source = "hybrid"
            elif in_dense:
                source = "dense"
            else:
                source = "lexical"

            final_chunks.append(
                RetrievedChunk(
                    chunk_id=authorized.chunk_id,
                    document_id=authorized.document_id,
                    backend_thesis_id=authorized.backend_thesis_id,
                    text=authorized.text,
                    page_number=authorized.page_number,
                    section=authorized.section,
                    chunk_index=authorized.chunk_index,
                    access_level=authorized.access_level,
                    provenance=dict(authorized.provenance),
                    dense_score=dense_scores.get(chunk_id),
                    lexical_score=(
                        lexical_by_id[chunk_id].lexical_score if in_lexical else None
                    ),
                    fused_score=fused_score,
                    retrieval_source=source,
                )
            )

        return final_chunks
