"""FastAPI dependencies for V2 endpoints.

- Service-to-service authentication (internal token from Django)
- Actor context extraction (issued by Django, never from browser)
- Trace ID propagation
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException

from ..auth.middleware import ActorContext, require_internal_auth
from ..config import get_settings
from ..errors import ConfigurationError


def get_internal_service_token(
    authorization: Optional[str] = Header(None),
) -> str:
    """Extract and validate the internal service token from Django.

    The AI service is called by Django over an internal channel. Django
    presents a shared service token. The AI service validates it and
    never accepts browser-supplied identity.
    """
    settings = get_settings()
    # The internal token is configured via BACKEND_API_INTERNAL_TOKEN.
    import os

    expected_token = os.getenv("BACKEND_API_INTERNAL_TOKEN", "")
    if not expected_token:
        raise ConfigurationError(
            code="service_token_not_configured",
            message=(
                "BACKEND_API_INTERNAL_TOKEN is not configured on the AI service. "
                "Service-to-service authentication cannot be established."
            ),
            component="api",
        )

    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="Missing internal service token.",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Use Bearer <token>.",
        )

    if token != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid internal service token.",
        )

    return token


def get_actor_context(
    x_user_id: Optional[str] = Header(None),
    x_roles: Optional[str] = Header(None),
    x_department: Optional[str] = Header(None),
    x_trace_id: Optional[str] = Header(None),
) -> ActorContext:
    """Extract actor context from headers issued by Django.

    These headers are set by Django when it forwards the request to the AI
    service. The AI service does NOT verify them against a browser — it
    trusts Django as the identity authority (service-to-service auth above
    ensures only Django can call this endpoint).

    Browser-supplied user IDs, roles, or department claims are never used.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="Missing x-user-id header (issued by Django).",
        )

    roles = [r.strip() for r in (x_roles or "").split(",") if r.strip()]
    if not roles:
        roles = ["student"]

    return ActorContext(
        user_id=x_user_id,
        roles=roles,
        department=x_department or "",
        trace_id=x_trace_id,
    )


def get_trace_id(
    x_trace_id: Optional[str] = Header(None),
) -> str:
    """Extract or generate a trace ID."""
    import uuid

    return x_trace_id or str(uuid.uuid4())
