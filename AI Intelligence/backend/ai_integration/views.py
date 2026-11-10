"""AI Integration views — Django-mediated endpoints for the V2 AI service.

Django is the identity/permission authority. All endpoints:
1. Require JWT authentication (IsAuthenticated).
2. Generate a UUIDv4 trace_id per request.
3. Build actor_context from the authenticated Django user.
4. Forward to V2 with internal service token + actor context headers.
5. Enforce thesis permissions before forwarding thesis-specific operations.
6. Never forward the user's JWT to V2 model providers.
"""

from __future__ import annotations

import logging
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsActiveUser
from theses.models import Thesis

from .services import (
    build_actor_context,
    check_thesis_access,
    check_thesis_write_access,
    derive_access_level,
    forward_to_v2,
    get_internal_service_token,
    resolve_document_to_thesis,
)

logger = logging.getLogger(__name__)

# The AI service stores the successful terminal state as "success". The public
# API (and the frontend polling contract) uses "completed".
_JOB_STATUS_ALIASES = {"success": "completed"}
_TEMPORARY_PDF_PREFIX = "tmp-pdf-"


def _is_temporary_pdf_id(value):
    if not isinstance(value, str) or not value.startswith(_TEMPORARY_PDF_PREFIX):
        return False
    try:
        UUID(value[len(_TEMPORARY_PDF_PREFIX):])
        return True
    except ValueError:
        return False


def _map_v2_error(exc: Exception):
    """Map a V2 failure onto the closest Django response status.

    Prefers the structured status/code attached by forward_to_v2 and falls
    back to message inspection for plain ValueError callers.
    """
    code = getattr(exc, "code", None)
    upstream = getattr(exc, "status_code", None)
    text = str(exc).lower()

    if code == "access_denied" or "access" in text:
        http_status = status.HTTP_403_FORBIDDEN
    elif code == "document_already_exists":
        http_status = status.HTTP_409_CONFLICT
    elif code in ("job_not_found", "document_not_found") or "not found" in text:
        http_status = status.HTTP_404_NOT_FOUND
    elif code == "vectorize_not_configured" or "unavailable" in text:
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    elif upstream is not None and 400 <= upstream < 500:
        http_status = status.HTTP_400_BAD_REQUEST
    else:
        http_status = status.HTTP_502_BAD_GATEWAY

    body = {
        "error": "AI Service Error",
        "detail": getattr(exc, "detail", None) or str(exc),
    }
    if code:
        body["code"] = code
    return Response(body, status=http_status)


class AIHealthView(APIView):
    """Health check — proxies to V2 AI service health endpoint."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        try:
            internal_token = get_internal_service_token()
            actor_context = build_actor_context(request.user)
            result = forward_to_v2(
                method="GET",
                path="/api/v2/health",
                actor_context=actor_context,
                internal_token=internal_token,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response(
                {"error": "AI Service Unavailable", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class AIDocumentUploadView(APIView):
    """Upload a thesis PDF and start ingestion.

    Body (multipart/form-data):
        file: PDF file
        backend_thesis_id: ID of the thesis in the Django backend
        backend_user_id: ID of the user uploading
        access_level: public | restricted | private
        thesis_metadata: JSON string (optional)
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        thesis_id = request.data.get("backend_thesis_id")
        if not thesis_id:
            return Response(
                {"error": "Validation Error", "detail": "backend_thesis_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Temporary analysis uploads have no Django thesis record. Keep them
        # private and let V2 enforce ownership from the authenticated actor.
        # Permanent thesis uploads still derive scope from the thesis record.
        if _is_temporary_pdf_id(thesis_id):
            access_level = "private"
        else:
            access_level = derive_access_level(thesis_id, request.user)
            if access_level is None:
                return Response(
                    {
                        "error": "Access Denied",
                        "detail": "You do not have permission to upload for this thesis.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        actor_context = build_actor_context(request.user)

        # Build multipart data for V2.
        # Never trust a client-supplied user id or access level.
        data = {
            "backend_user_id": str(request.user.id),
            "access_level": access_level,
            "backend_thesis_id": thesis_id,
        }
        if "thesis_metadata" in request.data:
            data["thesis_metadata"] = request.data["thesis_metadata"]

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                {"error": "Validation Error", "detail": "file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/documents/upload",
                actor_context=actor_context,
                internal_token=internal_token,
                data=data,
                files={"file": (uploaded_file.name, uploaded_file.read(), uploaded_file.content_type)},
                timeout=120,
            )
            job_id = result.get("job_id")
            if job_id and not _is_temporary_pdf_id(thesis_id):
                thesis = Thesis.objects.get(pk=thesis_id)
                thesis.ai_job_id = str(job_id)
                thesis.processing_status = Thesis.ProcessingStatus.QUEUED
                thesis.save(
                    update_fields=["ai_job_id", "processing_status", "updated_at"]
                )
            return Response(result, status=status.HTTP_202_ACCEPTED)
        except ValueError as exc:
            return _map_v2_error(exc)


class AIJobStatusView(APIView):
    """Get ingestion job status.

    Only the document owner or an admin can view the job status.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, job_id):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="GET",
                path=f"/api/v2/documents/jobs/{job_id}",
                actor_context=actor_context,
                internal_token=internal_token,
            )
            if isinstance(result, dict):
                raw_status = result.get("status")
                if isinstance(raw_status, str):
                    result["status"] = _JOB_STATUS_ALIASES.get(raw_status, raw_status)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class AIDocumentDeleteView(APIView):
    """Delete a thesis document and all derived data.

    Only the document owner or an admin can delete.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def delete(self, request, backend_thesis_id):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # backend_thesis_id from the URL is actually a V2 document UUID
        # (AIDocument.id), not a Django Thesis PK. Resolve it to the Django
        # Thesis PK for the access check. If it doesn't resolve as a V2 UUID,
        # treat it as a Django Thesis PK directly (backward compat).
        thesis_id = resolve_document_to_thesis(backend_thesis_id)
        if thesis_id is None:
            thesis_id = backend_thesis_id
        # Temporary documents have no Django Thesis row. V2 checks their
        # backend_user_id against this authenticated actor before deletion.
        if not _is_temporary_pdf_id(thesis_id) and not check_thesis_write_access(thesis_id, request.user):
            return Response(
                {
                    "error": "Access Denied",
                    "detail": "You do not have permission to delete this thesis.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="DELETE",
                path=f"/api/v2/documents/{backend_thesis_id}",
                actor_context=actor_context,
                internal_token=internal_token,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class AIDocumentTextView(APIView):
    """Retrieve extracted text for an ingested document.

    Used by the temporary PDF similarity check flow. Access is restricted to
    the document owner or an admin by the V2 service; Django forwards the
    authenticated actor context.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, internal_document_id):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        actor_context = build_actor_context(request.user)
        try:
            result = forward_to_v2(
                method="GET",
                path=f"/api/v2/documents/{internal_document_id}/text",
                actor_context=actor_context,
                internal_token=internal_token,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class DocumentCleanupView(APIView):
    """Clean up expired temporary documents (tmp-pdf- prefix).

    Admin-only endpoint that deletes temporary PDF documents older than 24
    hours that are in a terminal state. Used by scheduled cleanup jobs.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def delete(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        actor_context = build_actor_context(request.user)
        try:
            result = forward_to_v2(
                method="DELETE",
                path="/api/v2/documents/cleanup-temporary",
                actor_context=actor_context,
                internal_token=internal_token,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class AIRAGAskView(APIView):
    """Ask a grounded research question.

    Body (JSON):
        question: str
        document_ids: list[str] (optional)
        top_k: int (optional, default 5)
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        question = request.data.get("question")
        if not question:
            return Response(
                {"error": "Validation Error", "detail": "question is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document_ids = request.data.get("document_ids")
        if document_ids:
            # Enforce access to each requested document.
            for doc_id in document_ids:
                # Resolve V2 document UUID to Django Thesis PK before
                # checking access. V2 document IDs are UUIDs; Thesis PKs
                # are integers. The mapping lives in ai_documents.
                thesis_id = resolve_document_to_thesis(doc_id)
                if thesis_id is None:
                    return Response(
                        {
                            "error": "Access Denied",
                            "detail": f"Unknown document {doc_id}.",
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if not check_thesis_access(thesis_id, request.user):
                    return Response(
                        {
                            "error": "Access Denied",
                            "detail": f"You do not have access to document {doc_id}.",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

        actor_context = build_actor_context(request.user)

        payload = {"question": question}
        if document_ids:
            payload["document_ids"] = document_ids
        if "top_k" in request.data:
            payload["top_k"] = request.data["top_k"]

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/rag/ask",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "unavailable" in str(exc).lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )


class AIResearchGapView(APIView):
    """Detect research gaps from thesis evidence.

    Body (JSON):
        research_question: str
        document_ids: list[str] (optional)
        top_k: int (optional, default 10)
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        research_question = request.data.get("research_question")
        if not research_question:
            return Response(
                {"error": "Validation Error", "detail": "research_question is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document_ids = request.data.get("document_ids")
        if document_ids:
            # Enforce access to each requested document.
            for doc_id in document_ids:
                # Resolve V2 document UUID to Django Thesis PK before
                # checking access. V2 document IDs are UUIDs; Thesis PKs
                # are integers. The mapping lives in ai_documents.
                thesis_id = resolve_document_to_thesis(doc_id)
                if thesis_id is None:
                    return Response(
                        {
                            "error": "Access Denied",
                            "detail": f"Unknown document {doc_id}.",
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if not check_thesis_access(thesis_id, request.user):
                    return Response(
                        {
                            "error": "Access Denied",
                            "detail": f"You do not have access to document {doc_id}.",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

        actor_context = build_actor_context(request.user)

        payload = {"research_question": research_question}
        if document_ids:
            payload["document_ids"] = document_ids
        if "top_k" in request.data:
            payload["top_k"] = request.data["top_k"]

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/research-gaps/ask",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "unavailable" in str(exc).lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )


class AITopicAnalysisView(APIView):
    """Aggregate repository topics, departments, faculties and years.

    Deterministic metadata aggregation — no model call is forwarded.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        payload = {}
        for field in ("max_documents", "max_topics"):
            if field in request.data:
                payload[field] = request.data[field]

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/topics/analyze",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=60,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class AIRecommendationView(APIView):
    """Recommend existing theses relevant to the caller's research context.

    The actor is always taken from authentication; a client-supplied user id
    is never forwarded.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        seed_thesis_id = request.data.get("seed_thesis_id")
        if seed_thesis_id and not check_thesis_access(seed_thesis_id, request.user):
            return Response(
                {
                    "error": "Access Denied",
                    "detail": "You do not have access to the seed thesis.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = {}
        for field in ("query", "seed_thesis_id", "top_k"):
            if field in request.data:
                payload[field] = request.data[field]

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/recommendations",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class AISimilarityCheckView(APIView):
    """Compare submitted text against documents the caller may access."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        text = request.data.get("text")
        if not text or not str(text).strip():
            return Response(
                {"error": "Validation Error", "detail": "text is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = {"text": text}
        for field in ("min_score", "max_matches", "exclude_document_ids", "enable_semantic"):
            if field in request.data:
                payload[field] = request.data[field]

        actor_context = build_actor_context(request.user)
        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/similarity/check",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class AIPlagiarismAssessView(APIView):
    """Assess overlap for attribution. Never returns a plagiarism verdict."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        text = request.data.get("text")
        if not text or not str(text).strip():
            return Response(
                {"error": "Validation Error", "detail": "text is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = {"text": text}
        for field in ("min_score", "exclude_document_ids"):
            if field in request.data:
                payload[field] = request.data[field]

        actor_context = build_actor_context(request.user)
        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/plagiarism/assess",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class AIWritingDetectView(APIView):
    """AI-writing detection. Reports unavailability instead of guessing."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        text = request.data.get("text")
        if not text or not str(text).strip():
            return Response(
                {"error": "Validation Error", "detail": "text is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actor_context = build_actor_context(request.user)
        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/ai-writing/detect",
                actor_context=actor_context,
                internal_token=internal_token,
                data={"text": text},
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return _map_v2_error(exc)


class AIMemoryRetrieveView(APIView):
    """Retrieve relevant memories for a researcher.

    Body (JSON):
        query: str
        top_k: int (optional, default 10)
        memory_types: list[str] (optional)
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        query = request.data.get("query")
        if not query:
            return Response(
                {"error": "Validation Error", "detail": "query is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actor_context = build_actor_context(request.user)

        payload = {"query": query}
        if "top_k" in request.data:
            payload["top_k"] = request.data["top_k"]
        if "memory_types" in request.data:
            payload["memory_types"] = request.data["memory_types"]

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/memory/retrieve",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "unavailable" in str(exc).lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )


class AIMemoryListView(APIView):
    """List researcher memories."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        actor_context = build_actor_context(request.user)

        params = {}
        if request.query_params.get("memory_type"):
            params["memory_type"] = request.query_params.get("memory_type")
        if request.query_params.get("include_archived"):
            params["include_archived"] = request.query_params.get("include_archived")
        if request.query_params.get("limit"):
            params["limit"] = request.query_params.get("limit")

        try:
            result = forward_to_v2(
                method="GET",
                path="/api/v2/memory/",
                actor_context=actor_context,
                internal_token=internal_token,
                params=params,
                timeout=60,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "unavailable" in str(exc).lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )


def _create_memory_response(request):
    """Shared create-memory handler for GET+POST on /memory/."""
    try:
        internal_token = get_internal_service_token()
    except ValueError as exc:
        return Response(
            {"error": "Configuration Error", "detail": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    key = request.data.get("key")
    value = request.data.get("value")
    if not key or not value:
        return Response(
            {"error": "Validation Error", "detail": "key and value are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    actor_context = build_actor_context(request.user)

    payload = {"key": key, "value": value}
    if "memory_type" in request.data:
        payload["memory_type"] = request.data["memory_type"]
    if "source" in request.data:
        payload["source"] = request.data["source"]
    if "confidence" in request.data:
        payload["confidence"] = request.data["confidence"]

    try:
        result = forward_to_v2(
            method="POST",
            path="/api/v2/memory/",
            actor_context=actor_context,
            internal_token=internal_token,
            data=payload,
            timeout=60,
        )
        return Response(result, status=status.HTTP_200_OK)
    except ValueError as exc:
        status_code = status.HTTP_502_BAD_GATEWAY
        if "unavailable" in str(exc).lower():
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(
            {"error": "AI Service Error", "detail": str(exc)},
            status=status_code,
        )


class AIMemoryCreateView(APIView):
    """Create or update a researcher memory.

    Body (JSON):
        key: str
        value: str
        memory_type: str (optional, default "profile")
        source: str (optional, default "system_inferred")
        confidence: float (optional, default 0.5)
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        return _create_memory_response(request)


class AIMemoryListCreateView(AIMemoryListView):
    """GET: list memories. POST: create/update a memory (single URL)."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        return _create_memory_response(request)


class AIMemoryDetailView(APIView):
    """Get, update, or delete a specific memory entry."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, memory_id):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="GET",
                path=f"/api/v2/memory/{memory_id}",
                actor_context=actor_context,
                internal_token=internal_token,
                timeout=60,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "not found" in str(exc).lower():
                status_code = status.HTTP_404_NOT_FOUND
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )

    def put(self, request, memory_id):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        actor_context = build_actor_context(request.user)

        payload = {}
        if "value" in request.data:
            payload["value"] = request.data["value"]
        if "confidence" in request.data:
            payload["confidence"] = request.data["confidence"]

        try:
            result = forward_to_v2(
                method="PUT",
                path=f"/api/v2/memory/{memory_id}",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=60,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "not found" in str(exc).lower():
                status_code = status.HTTP_404_NOT_FOUND
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )

    def delete(self, request, memory_id):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="DELETE",
                path=f"/api/v2/memory/{memory_id}",
                actor_context=actor_context,
                internal_token=internal_token,
                timeout=60,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "not found" in str(exc).lower():
                status_code = status.HTTP_404_NOT_FOUND
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )


class AIMemoryThesisSummaryView(APIView):
    """Create or retrieve a thesis summary.

    POST Body (JSON):
        backend_thesis_id: str
        title: str (optional)
        abstract_summary: str (optional)
        research_questions: list[str] (optional)
        objectives: list[str] (optional)
        methodology: str (optional)
        findings: list[str] (optional)
        limitations: list[str] (optional)
        key_entities: list[str] (optional)
        confidence: float (optional)
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        backend_thesis_id = request.data.get("backend_thesis_id")
        if not backend_thesis_id:
            return Response(
                {"error": "Validation Error", "detail": "backend_thesis_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Enforce thesis access
        if not check_thesis_access(backend_thesis_id, request.user):
            return Response(
                {
                    "error": "Access Denied",
                    "detail": f"You do not have access to thesis {backend_thesis_id}.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        actor_context = build_actor_context(request.user)

        payload = {"backend_thesis_id": backend_thesis_id}
        if request.data.get("generate"):
            # Generation mode: the AI service derives every section from the
            # thesis's own text, so client-supplied content is dropped.
            payload["generate"] = True
        else:
            for field in ("title", "abstract_summary", "methodology"):
                if field in request.data:
                    payload[field] = request.data[field]
            for field in (
                "research_questions",
                "objectives",
                "findings",
                "limitations",
                "key_entities",
            ):
                if field in request.data:
                    payload[field] = request.data[field]
            if "confidence" in request.data:
                payload["confidence"] = request.data["confidence"]

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/memory/thesis-summaries",
                actor_context=actor_context,
                internal_token=internal_token,
                data=payload,
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "unavailable" in str(exc).lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )

    def get(self, request, backend_thesis_id):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Enforce thesis access
        if not check_thesis_access(backend_thesis_id, request.user):
            return Response(
                {
                    "error": "Access Denied",
                    "detail": f"You do not have access to thesis {backend_thesis_id}.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="GET",
                path=f"/api/v2/memory/thesis-summaries/{backend_thesis_id}",
                actor_context=actor_context,
                internal_token=internal_token,
                timeout=60,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "not found" in str(exc).lower():
                status_code = status.HTTP_404_NOT_FOUND
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )


class AIMemoryPreferencesView(APIView):
    """Get memory preferences for a researcher."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="GET",
                path="/api/v2/memory/preferences",
                actor_context=actor_context,
                internal_token=internal_token,
                timeout=60,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "unavailable" in str(exc).lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )


class AIThesisQAView(APIView):
    """Ask a question about a thesis (or across public theses).

    Proxied to V2 /api/v2/thesis-qa/ask.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        backend_thesis_id = request.data.get("backend_thesis_id")
        question = request.data.get("question")
        scope = request.data.get("scope", "this_thesis")
        top_k = request.data.get("top_k", 5)

        if not backend_thesis_id:
            return Response(
                {"error": "Validation Error", "detail": "backend_thesis_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not question or not str(question).strip():
            return Response(
                {"error": "Validation Error", "detail": "question is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actor_context = build_actor_context(request.user)

        # Enforce thesis access before forwarding to V2.
        # backend_thesis_id is the Django Thesis primary key (integer), not a
        # V2 document UUID. Authorize it directly against the Django thesis
        # record; do not run it through the document-UUID resolver.
        if not check_thesis_access(backend_thesis_id, request.user):
            return Response(
                {
                    "error": "Access Denied",
                    "detail": f"You do not have access to thesis {backend_thesis_id}.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/thesis-qa/ask",
                actor_context=actor_context,
                internal_token=internal_token,
                data={
                    "backend_thesis_id": backend_thesis_id,
                    "question": question,
                    "scope": scope,
                    "top_k": top_k,
                },
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "unavailable" in str(exc).lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )


class AIAssistantChatView(APIView):
    """General-knowledge assistant chat (proxied to V2 /api/v2/assistant/chat).

    Body (JSON):
        messages: [{role: user|assistant, content: str}, ...]
        provider: "deepseek" | "groq" (optional, default deepseek)
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            return Response(
                {"error": "Configuration Error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        messages = request.data.get("messages")
        if not isinstance(messages, list) or not messages:
            return Response(
                {"error": "Validation Error", "detail": "messages is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for msg in messages:
            if not isinstance(msg, dict) or not msg.get("content"):
                return Response(
                    {"error": "Validation Error", "detail": "Each message needs content."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        provider = str(request.data.get("provider", "deepseek")).lower()
        if provider not in {"deepseek", "groq"}:
            return Response(
                {"error": "Validation Error", "detail": "provider must be deepseek or groq."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actor_context = build_actor_context(request.user)

        try:
            result = forward_to_v2(
                method="POST",
                path="/api/v2/assistant/chat",
                actor_context=actor_context,
                internal_token=internal_token,
                data={"messages": messages, "provider": provider},
                timeout=120,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            status_code = status.HTTP_502_BAD_GATEWAY
            if "unavailable" in str(exc).lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {"error": "AI Service Error", "detail": str(exc)},
                status=status_code,
            )
