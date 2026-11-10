"""AI Integration service — forwards authenticated Django requests to the V2 AI service.

Django is the identity/permission authority. This service:
1. Validates the authenticated Django user (JWT).
2. Generates a UUIDv4 trace_id per request.
3. Builds actor_context from the Django user (user_id, roles, department).
4. Forwards to V2 with internal service token + actor context headers.
5. Never forwards the user's JWT to V2 model providers.
6. Enforces thesis permissions before forwarding thesis-specific operations.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

import requests
from django.conf import settings
from django.db import connection

from accounts.models import User
from theses.models import Thesis

logger = logging.getLogger(__name__)


class AIServiceError(ValueError):
    """Failure returned by the V2 AI service.

    Subclasses ValueError so existing callers that catch ValueError keep
    working, while newer callers can map the upstream status and error code
    onto a correct HTTP response instead of always returning 502.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.detail = detail or message


def get_internal_service_token() -> str:
    """Return the configured internal service token for Django->V2 auth."""
    token = getattr(settings, "BACKEND_API_INTERNAL_TOKEN", "") or ""
    if not token:
        raise ValueError(
            "BACKEND_API_INTERNAL_TOKEN is not configured. "
            "Set it in backend/.env or environment variables."
        )
    return token


def get_ai_service_url() -> str:
    """Return the base URL of the V2 AI service."""
    url = (
        getattr(settings, "AI_SERVICE_URL", "")
        or ""
    ).strip().rstrip("/")
    if not url:
        raise ValueError(
            "AI_SERVICE_URL is not configured. "
            "Set it in backend/.env or environment variables."
        )
    return url


def build_actor_context(user: User, trace_id: Optional[str] = None) -> Dict[str, str]:
    """Build actor_context from an authenticated Django user.

    Django is the authority for identity. Roles and department come from
    the Django User model — never from browser-supplied claims.
    """
    if not trace_id:
        trace_id = str(uuid.uuid4())
    return {
        "user_id": str(user.id),
        "roles": user.role,
        "department": user.department or "",
        "trace_id": trace_id,
    }


def check_thesis_access(thesis_id: str, user: User) -> bool:
    """Check whether the user can view a thesis using existing Django logic.

    Reuses Thesis.can_view() which enforces:
    - public + published: anyone
    - owner: always
    - admin: always
    - approved AccessRequest: requester
    """
    try:
        thesis = Thesis.objects.get(id=thesis_id)
    except (Thesis.DoesNotExist, ValueError, TypeError):
        return False
    return thesis.can_view(user)


def resolve_document_to_thesis(document_id: str) -> Optional[str]:
    """Resolve a V2 document UUID to its Django Thesis primary key.

    Queries the shared ai_intelligence.ai_documents table to map a V2
    document UUID (AIDocument.id) to the Django Thesis primary key
    (AIDocument.backend_thesis_id).

    Returns the backend_thesis_id string if the document exists,
    None otherwise.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT backend_thesis_id FROM ai_intelligence.ai_documents WHERE id = %s",
            [document_id],
        )
        row = cursor.fetchone()
        return row[0] if row else None


def check_thesis_write_access(thesis_id: str, user: User) -> bool:
    """Write authorization for AI document operations.

    Only the thesis owner or an admin may ingest or delete AI data for a
    thesis. Public read visibility must never imply write permission.
    """
    try:
        thesis = Thesis.objects.get(id=thesis_id)
    except (Thesis.DoesNotExist, ValueError, TypeError):
        return False

    if not user or not user.is_authenticated:
        return False
    if user.role == "admin":
        return True
    return thesis.owner_id == user.id


def derive_access_level(thesis_id: str, user: User) -> Optional[str]:
    """Derive the AI document access level from the thesis record.

    Returns None when the caller may not write AI data for the thesis, so the
    view can answer 403. The client never chooses this value: a thesis that is
    not published is stored as private, because a draft must not become
    globally retrievable through the AI index just because the uploader asked
    for a broader level.
    """
    try:
        thesis = Thesis.objects.get(id=thesis_id)
    except (Thesis.DoesNotExist, ValueError, TypeError):
        return None

    if not user or not user.is_authenticated:
        return None
    if user.role != "admin" and thesis.owner_id != user.id:
        return None

    if thesis.status != Thesis.Status.PUBLISHED:
        return "private"

    return {
        Thesis.AccessPolicy.PUBLIC: "public",
        Thesis.AccessPolicy.RESTRICTED: "restricted",
        Thesis.AccessPolicy.PRIVATE: "private",
    }.get(thesis.access_policy, "private")


def forward_to_v2(
    method: str,
    path: str,
    actor_context: Dict[str, str],
    internal_token: str,
    data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Forward a request to the V2 AI service with server-to-service auth.

    Args:
        method: HTTP method (GET, POST, DELETE, etc.)
        path: V2 API path (e.g. "/api/v2/rag/ask")
        actor_context: Django-issued actor context (user_id, roles, department, trace_id)
        internal_token: Shared service token for Django->V2 auth
        data: JSON body for POST/PUT
        files: Files for multipart upload
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response from V2.

    Raises:
        ValueError: If V2 returns an error or is unreachable.
    """
    base_url = get_ai_service_url()
    target_url = f"{base_url}{path}"

    headers: Dict[str, str] = {
        "Authorization": f"Bearer {internal_token}",
        "X-User-Id": actor_context["user_id"],
        "X-Roles": actor_context["roles"],
        "X-Department": actor_context["department"],
        "X-Trace-Id": actor_context["trace_id"],
        "Accept": "application/json",
    }

    try:
        if files:
            response = requests.request(
                method=method,
                url=target_url,
                headers=headers,
                data=data,
                files=files,
                params=params,
                timeout=timeout,
            )
        else:
            response = requests.request(
                method=method,
                url=target_url,
                headers=headers,
                json=data,
                params=params,
                timeout=timeout,
            )
    except requests.exceptions.RequestException as exc:
        logger.error("V2 service unreachable: %s", exc)
        raise ValueError(f"AI service unavailable: {exc}")

    if not response.ok:
        detail = response.text[:500]
        code = None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            code = payload.get("code")
            detail = payload.get("message") or payload.get("detail") or detail
        logger.error(
            "V2 error %s %s code=%s: %s",
            response.status_code,
            target_url,
            code,
            detail,
        )
        raise AIServiceError(
            f"AI service error ({response.status_code}): {detail}",
            status_code=response.status_code,
            code=code,
            detail=detail,
        )

    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return {"detail": response.text}
