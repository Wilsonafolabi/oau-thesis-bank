"""Phase 3 error contract — Phase3Error (§3 of the frozen contract).

All AI-service errors must conform to Phase3Error. The retryable flag
indicates whether an operation can be safely retried. No silent failures.
"""

from __future__ import annotations

from typing import Optional


class Phase3Error(Exception):
    """Structured error for all Phase 3 components.

    Attributes:
        code: Machine-readable error code.
        message: Human-readable error message.
        component: Component that originated the error.
        retryable: Whether the operation can be safely retried.
        trace_id: UUIDv4 trace identifier for the request.
    """

    def __init__(
        self,
        code: str,
        message: str,
        component: str,
        retryable: bool = False,
        trace_id: Optional[str] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.component = component
        self.retryable = retryable
        self.trace_id = trace_id
        super().__init__(f"[{component}] {code}: {message}")

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "component": self.component,
            "retryable": self.retryable,
            "trace_id": self.trace_id,
        }


class ProviderError(Phase3Error):
    """Error originating from an LLM provider call."""


class ProviderUnavailableError(Phase3Error):
    """All providers failed or the required provider is unavailable.

    Raised when no provider can serve a request. No silent fallback occurs.
    """

    def __init__(self, message: str, component: str, trace_id: Optional[str] = None):
        super().__init__(
            code="provider_unavailable",
            message=message,
            component=component,
            retryable=True,
            trace_id=trace_id,
        )


class ProviderAuthError(Phase3Error):
    """Provider authentication failed (401/403). Non-retryable."""

    def __init__(
        self, provider: str, message: str, trace_id: Optional[str] = None
    ):
        super().__init__(
            code="provider_auth_error",
            message=message,
            component=provider,
            retryable=False,
            trace_id=trace_id,
        )


class RetrievalError(Phase3Error):
    """Error retrieving authorized thesis content."""


class GuardrailError(Phase3Error):
    """Error from input/output guardrails or JEV decision layer."""


class ConfigurationError(Phase3Error):
    """Missing or invalid configuration."""
