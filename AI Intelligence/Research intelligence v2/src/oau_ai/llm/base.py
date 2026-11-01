"""Base types for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatRequest:
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout_seconds: Optional[float] = None
    json_mode: bool = False


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ChatResponse:
    provider: str
    model: str
    content: str
    finish_reason: Optional[str] = None
    usage: Optional[Usage] = None
    response_id: Optional[str] = None


@dataclass(frozen=True)
class ProviderHealth:
    name: str
    healthy: bool
    latency_ms: float = 0.0
    last_error: Optional[str] = None
    checked_at: float = 0.0


class ProviderError(Exception):
    """Base provider error with retryability."""

    retryable = False

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class ProviderTimeoutError(ProviderError):
    retryable = True


class ProviderConnectionError(ProviderError):
    retryable = True


class ProviderRateLimitError(ProviderError):
    retryable = True

    def __init__(self, provider: str, message: str, retry_after: Optional[float] = None):
        super().__init__(provider, message)
        self.retry_after = retry_after


class ProviderUpstreamError(ProviderError):
    retryable = True


class ProviderAuthError(ProviderError):
    retryable = False


class ProviderMalformedResponseError(ProviderError):
    retryable = False


class ProviderServiceUnavailableError(Exception):
    """All providers failed or the required provider is unavailable.

    No silent fallback occurs. Callers must surface this as a structured error.
    """

    def __init__(self, failures: list):
        self.failures = list(failures)
        super().__init__(
            "All LLM providers failed: "
            + "; ".join(f"{n}: {m}" for n, m in self.failures)
        )


@dataclass(frozen=True)
class TaskDesignation:
    """Marks a task as explicitly designated for Groq (smaller task).

    Groq is NOT a fallback. It is used only when a task is explicitly
    designated for it by the caller.
    """

    task_type: str
    reason: str
