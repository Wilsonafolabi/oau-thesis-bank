"""LLM provider router — DeepSeek primary, Groq designated-tasks-only.

Routing rules (V2 contract §1.5 amended):
- DeepSeek is the designated primary reasoning/generation provider.
- Groq is reserved for explicitly designated smaller tasks only. It is not a
  fallback for DeepSeek and must not silently take over primary-model tasks.
- No automatic provider fallback. Provider failure returns a structured error;
  it never silently switches to another model.

The router is provider-scoped: a caller explicitly selects DeepSeek for
reasoning/generation, or explicitly designates Groq for a smaller task.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional

import httpx

from ..config import LLMSettings, ProviderConfig, get_settings
from ..errors import (
    ConfigurationError,
    Phase3Error,
    ProviderAuthError,
    ProviderUnavailableError,
)
from .base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ProviderAuthError as BaseProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderHealth,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderServiceUnavailableError,
    ProviderTimeoutError,
    ProviderUpstreamError,
    TaskDesignation,
)
from .deepseek import DeepSeekProvider
from .groq import GroqProvider

logger = logging.getLogger("oau_ai.llm.router")

_PROVIDER_CLASSES = {
    "deepseek": DeepSeekProvider,
    "groq": GroqProvider,
}


class ProviderRouter:
    """Provider-scoped LLM router with bounded retries and no cross-provider fallback.

    Attributes:
        settings: LLM configuration.
        providers: Instantiated provider objects keyed by name.
    """

    def __init__(
        self,
        settings: Optional[LLMSettings] = None,
        transports: Optional[Dict[str, httpx.BaseTransport]] = None,
    ) -> None:
        self.settings = settings or get_settings()
        transports = transports or {}
        self.providers: Dict[str, object] = {}
        for name, cfg in self.settings.providers.items():
            cls = _PROVIDER_CLASSES[name]
            self.providers[name] = cls(cfg, transport=transports.get(name))
        self._health: Dict[str, ProviderHealth] = {}

    def _provider_for_name(self, name: str) -> object:
        if name not in self.providers:
            raise ConfigurationError(
                code="unknown_provider",
                message=f"Provider '{name}' is not configured.",
                component="llm_router",
            )
        return self.providers[name]

    def complete_deepseek(self, request: ChatRequest) -> ChatResponse:
        """Complete a request using DeepSeek (primary reasoning/generation).

        Raises ProviderUnavailableError if DeepSeek is not configured or
        unhealthy. No fallback to Groq occurs.
        """
        return self._complete_named("deepseek", request, tier=1)

    def complete_groq_designated(
        self, request: ChatRequest, designation: TaskDesignation
    ) -> ChatResponse:
        """Complete a request using Groq for an explicitly designated smaller task.

        The caller must supply a TaskDesignation justifying Groq use. Groq is
        never selected automatically as a fallback.
        """
        if not designation or not designation.task_type:
            raise ConfigurationError(
                code="groq_designation_required",
                message=(
                    "Groq is reserved for explicitly designated smaller tasks. "
                    "Provide a TaskDesignation with task_type and reason."
                ),
                component="llm_router",
            )
        return self._complete_named("groq", request, tier=2, designation=designation)

    def _complete_named(
        self,
        name: str,
        request: ChatRequest,
        tier: int,
        designation: Optional[TaskDesignation] = None,
    ) -> ChatResponse:
        provider = self._provider_for_name(name)
        healthy, err = self._health_ok(name)
        if not healthy:
            raise ProviderUnavailableError(
                message=f"Provider '{name}' is unhealthy: {err}",
                component="llm_router",
            )
        try:
            result = provider.complete(request)
            logger.info(
                "llm.provider_selected provider=%s tier=%s model=%s",
                name,
                tier,
                result.model,
            )
            return result
        except BaseProviderAuthError:
            # Authentication errors are non-retryable; propagate directly
            # without wrapping or fallback.
            raise
        except ProviderError as exc:
            logger.warning(
                "llm.provider_failed provider=%s tier=%s error=%s",
                name,
                tier,
                exc,
            )
            raise ProviderUnavailableError(
                message=f"Provider '{name}' failed: {exc}",
                component="llm_router",
            ) from exc

    async def acomplete_deepseek(self, request: ChatRequest) -> ChatResponse:
        return await self._acomplete_named("deepseek", request, tier=1)

    async def acomplete_groq_designated(
        self, request: ChatRequest, designation: TaskDesignation
    ) -> ChatResponse:
        if not designation or not designation.task_type:
            raise ConfigurationError(
                code="groq_designation_required",
                message=(
                    "Groq is reserved for explicitly designated smaller tasks. "
                    "Provide a TaskDesignation with task_type and reason."
                ),
                component="llm_router",
            )
        return await self._acomplete_named("groq", request, tier=2, designation=designation)

    async def _acomplete_named(
        self,
        name: str,
        request: ChatRequest,
        tier: int,
        designation: Optional[TaskDesignation] = None,
    ) -> ChatResponse:
        provider = self._provider_for_name(name)
        healthy, err = await self._ahealth_ok(name)
        if not healthy:
            raise ProviderUnavailableError(
                message=f"Provider '{name}' is unhealthy: {err}",
                component="llm_router",
            )
        try:
            result = await provider.acomplete(request)
            logger.info(
                "llm.provider_selected provider=%s tier=%s model=%s",
                name,
                tier,
                result.model,
            )
            return result
        except BaseProviderAuthError:
            # Authentication errors are non-retryable; propagate directly
            # without wrapping or fallback.
            raise
        except ProviderError as exc:
            logger.warning(
                "llm.provider_failed provider=%s tier=%s error=%s",
                name,
                tier,
                exc,
            )
            raise ProviderUnavailableError(
                message=f"Provider '{name}' failed: {exc}",
                component="llm_router",
            ) from exc

    def _health_ok(self, name: str):
        cached = self._health.get(name)
        if cached is not None and (
            time.time() - cached.checked_at
        ) < self.settings.health_ttl_seconds:
            return cached.healthy, cached.last_error
        provider = self.providers[name]
        probe = provider.health()
        self._health[name] = probe
        return probe.healthy, probe.last_error

    async def _ahealth_ok(self, name: str):
        cached = self._health.get(name)
        if cached is not None and (
            time.time() - cached.checked_at
        ) < self.settings.health_ttl_seconds:
            return cached.healthy, cached.last_error
        provider = self.providers[name]
        probe = await provider.ahealth()
        self._health[name] = probe
        return probe.healthy, probe.last_error

    def health_status(self, refresh: bool = False) -> Dict[str, ProviderHealth]:
        if refresh:
            self._health.clear()
        out: Dict[str, ProviderHealth] = {}
        for name in self.settings.enabled_order():
            self._health_ok(name)
            out[name] = self._health[name]
        return out

    def describe(self) -> Dict:
        info = self.settings.redacted_dict()
        info["enabled_order"] = list(self.settings.enabled_order())
        info["primary_provider"] = self.settings.primary_provider()
        return info


_router_cache: Optional[ProviderRouter] = None


def get_router(refresh: bool = False) -> ProviderRouter:
    global _router_cache
    if _router_cache is None or refresh:
        _router_cache = ProviderRouter(settings=get_settings(refresh=refresh))
    return _router_cache


def complete_with_deepseek(
    messages: list, **kwargs
) -> ChatResponse:
    """Convenience: complete using DeepSeek as primary provider.

    Args:
        messages: List of dicts with 'role' and 'content'.
        **kwargs: Passed through to ChatRequest.
    """
    chat_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
    request = ChatRequest(messages=chat_messages, **kwargs)
    return get_router().complete_deepseek(request)


def complete_with_groq_designated(
    messages: list, designation: TaskDesignation, **kwargs
) -> ChatResponse:
    """Convenience: complete using Groq for an explicitly designated task.

    Args:
        messages: List of dicts with 'role' and 'content'.
        designation: Required TaskDesignation justifying Groq use.
        **kwargs: Passed through to ChatRequest.
    """
    chat_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
    request = ChatRequest(messages=chat_messages, **kwargs)
    return get_router().complete_groq_designated(request, designation)
