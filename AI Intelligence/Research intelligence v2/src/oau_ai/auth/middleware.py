"""Service-to-service authentication for the AI service.

The AI service is called by Django over an internal channel. Django issues
actor_context (user_id, roles, department) and trace_id. The AI service
verifies a shared internal service token and never accepts browser-supplied
identity. User JWTs are never forwarded to model providers.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..errors import ConfigurationError, Phase3Error


# Bearer scheme for the internal service token (Django -> AI service).
internal_scheme = HTTPBearer(auto_error=False)


def get_internal_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Header(None),
) -> Optional[str]:
    """Extract the internal service token from the Authorization header.

    Returns None if no header is present (caller must enforce presence).
    Does not validate the token itself — that is done by require_internal_auth.
    """
    if credentials is None:
        return None
    return credentials.credentials


def require_internal_auth(
    expected_token: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Header(None),
) -> str:
    """Require a valid internal service token.

    Fails closed when the token is missing, malformed, or incorrect.
    """
    if not expected_token:
        raise ConfigurationError(
            code="service_token_not_configured",
            message="Internal service token is not configured on the AI service.",
            component="auth",
        )
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing internal service token.",
        )
    token = credentials.credentials
    if token != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid internal service token.",
        )
    return token


class ActorContext:
    """Authoritative actor context issued by Django.

    Attributes:
        user_id: Authenticated user id from Django.
        roles: List of roles from Django.
        department: Department from Django.
        trace_id: UUIDv4 trace id for the request.
    """

    def __init__(
        self,
        user_id: str,
        roles: list,
        department: str,
        trace_id: Optional[str] = None,
    ):
        self.user_id = user_id
        self.roles = list(roles)
        self.department = department
        self.trace_id = trace_id

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "roles": self.roles,
            "department": self.department,
            "trace_id": self.trace_id,
        }
