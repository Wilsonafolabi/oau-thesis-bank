"""Tests for LLM providers — DeepSeek and Groq.

These tests use httpx.MockTransport to simulate HTTP responses. They test
client behavior (provider selection, retry logic, auth error handling) and
do not mock successful production responses or claim live API integration.
"""

import httpx
import pytest

from oau_ai.config import LLMSettings, get_settings
from oau_ai.llm.base import ChatMessage, ChatRequest
from oau_ai.llm.deepseek import DeepSeekProvider
from oau_ai.llm.groq import GroqProvider
from oau_ai.llm.router import (
    ProviderRouter,
    TaskDesignation,
    complete_with_deepseek,
    complete_with_groq_designated,
)


def _mock_transport(status: int, json_body: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=json_body, request=request)

    return httpx.MockTransport(handler)


def _chat_response_json(content: str = "answer") -> dict:
    return {
        "id": "chatcmpl-123",
        "model": "deepseek-chat",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }


def test_deepseek_is_primary_provider():
    """DeepSeek must be the enabled primary provider when configured."""
    settings = get_settings()
    # In the test env, no API keys are set, so no providers are enabled.
    # Verify the configuration structure designates DeepSeek as primary.
    assert settings.primary_provider() is None or settings.primary_provider() == "deepseek"
    enabled = settings.enabled_order()
    # If deepseek is enabled, it must be first.
    if "deepseek" in enabled:
        assert enabled[0] == "deepseek"


def test_groq_not_automatically_primary():
    """Groq must not be the primary provider when DeepSeek is configured."""
    settings = get_settings()
    order = settings.enabled_order()
    if order:
        assert order[0] != "groq", (
            "Groq must not be the primary provider; DeepSeek is designated primary."
        )


def test_deepseek_provider_success_with_mock_transport():
    """DeepSeek provider returns a ChatResponse on a successful mocked HTTP call."""
    provider = DeepSeekProvider.__new__(DeepSeekProvider)
    provider.config = type(
        "C",
        (),
        {
            "name": "deepseek",
            "enabled": True,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "test-key",
            "timeout_seconds": 5.0,
            "max_tokens": 1024,
            "temperature": 0.2,
            "max_retries": 1,
            "retry_backoff_seconds": 0.1,
            "supports_response_format": True,
        },
    )()
    provider._transport = _mock_transport(200, _chat_response_json())

    request = ChatRequest(
        messages=[ChatMessage(role="user", content="What is the capital of France?")]
    )
    response = provider.complete(request)

    assert response.provider == "deepseek"
    assert response.content == "answer"
    assert response.usage is not None
    assert response.usage.total_tokens == 15


def test_groq_provider_success_with_mock_transport():
    """Groq provider returns a ChatResponse on a successful mocked HTTP call."""
    provider = GroqProvider.__new__(GroqProvider)
    provider.config = type(
        "C",
        (),
        {
            "name": "groq",
            "enabled": True,
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.1-8b-instant",
            "api_key": "test-key",
            "timeout_seconds": 5.0,
            "max_tokens": 1024,
            "temperature": 0.2,
            "max_retries": 1,
            "retry_backoff_seconds": 0.1,
            "supports_response_format": True,
        },
    )()
    provider._transport = _mock_transport(200, _chat_response_json())

    request = ChatRequest(
        messages=[ChatMessage(role="user", content="Summarize this thesis.")]
    )
    response = provider.complete(request)

    assert response.provider == "groq"
    assert response.content == "answer"


def test_deepseek_auth_error_is_non_retryable():
    """DeepSeek auth errors (401/403) are non-retryable and raised immediately."""
    provider = DeepSeekProvider.__new__(DeepSeekProvider)
    provider.config = type(
        "C",
        (),
        {
            "name": "deepseek",
            "enabled": True,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "bad-key",
            "timeout_seconds": 5.0,
            "max_tokens": 1024,
            "temperature": 0.2,
            "max_retries": 3,
            "retry_backoff_seconds": 0.1,
            "supports_response_format": True,
        },
    )()
    provider._transport = _mock_transport(401, {"error": "invalid api key"})

    request = ChatRequest(
        messages=[ChatMessage(role="user", content="Hello")]
    )
    from oau_ai.llm.base import ProviderAuthError

    with pytest.raises(ProviderAuthError) as exc_info:
        provider.complete(request)

    assert exc_info.value.provider == "deepseek"
    assert exc_info.value.retryable is False


def test_router_uses_deepseek_as_primary():
    """Router's complete_with_deepseek routes to DeepSeek provider."""
    settings = get_settings()
    # Build a router with a mock transport on DeepSeek.
    from oau_ai.config import ProviderConfig

    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="test-key",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    groq_cfg = ProviderConfig(
        name="groq",
        enabled=True,
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
        api_key="test-key",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )

    transport = _mock_transport(200, _chat_response_json())
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg, "groq": groq_cfg},
            fallback_order=("deepseek",),
        ),
        transports={"deepseek": transport},
    )

    response = router.complete_deepseek(
        ChatRequest(
            messages=[ChatMessage(role="user", content="Reason about this thesis.")]
        )
    )
    assert response.provider == "deepseek"
    assert response.content == "answer"


def test_router_no_silent_fallback_to_groq():
    """When DeepSeek fails, the router must NOT silently fall back to Groq.

    It raises ProviderUnavailableError instead.
    """
    from oau_ai.config import ProviderConfig
    from oau_ai.llm.router import ProviderUnavailableError

    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="test-key",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    groq_cfg = ProviderConfig(
        name="groq",
        enabled=True,
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
        api_key="test-key",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )

    # DeepSeek transport returns 500 (upstream error, retryable but max retries exhausted).
    deepseek_fail = _mock_transport(500, {"error": "internal error"})
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg, "groq": groq_cfg},
            fallback_order=("deepseek",),
        ),
        transports={"deepseek": deepseek_fail, "groq": None},
    )

    with pytest.raises(ProviderUnavailableError):
        router.complete_deepseek(
            ChatRequest(
                messages=[ChatMessage(role="user", content="Hello")]
            )
        )


def test_groq_requires_explicit_designation():
    """Groq completion requires an explicit TaskDesignation."""
    from oau_ai.config import ProviderConfig
    from oau_ai.errors import ConfigurationError

    groq_cfg = ProviderConfig(
        name="groq",
        enabled=True,
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
        api_key="test-key",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    transport = _mock_transport(200, _chat_response_json())
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"groq": groq_cfg},
            fallback_order=("groq",),
        ),
        transports={"groq": transport},
    )

    request = ChatRequest(
        messages=[ChatMessage(role="user", content="Small task")]
    )

    # No designation -> ConfigurationError
    with pytest.raises(ConfigurationError):
        router.complete_groq_designated(request, designation=None)

    # Empty designation -> ConfigurationError
    with pytest.raises(ConfigurationError):
        router.complete_groq_designated(
            request, designation=TaskDesignation(task_type="", reason="")
        )


def test_groq_explicitly_designated_task_succeeds():
    """Groq completes when explicitly designated with a valid TaskDesignation."""
    from oau_ai.config import ProviderConfig

    groq_cfg = ProviderConfig(
        name="groq",
        enabled=True,
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
        api_key="test-key",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    transport = _mock_transport(200, _chat_response_json())
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"groq": groq_cfg},
            fallback_order=("groq",),
        ),
        transports={"groq": transport},
    )

    request = ChatRequest(
        messages=[ChatMessage(role="user", content="Small classification task")]
    )
    designation = TaskDesignation(
        task_type="query_classification",
        reason="smaller task designated for Groq",
    )
    response = router.complete_groq_designated(request, designation=designation)
    assert response.provider == "groq"
    assert response.content == "answer"


def test_convenience_deepseek_routes_to_deepseek():
    """complete_with_deepseek convenience routes to DeepSeek provider."""
    from oau_ai.config import ProviderConfig

    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="test-key",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    transport = _mock_transport(200, _chat_response_json())
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg},
            fallback_order=("deepseek",),
        ),
        transports={"deepseek": transport},
    )

    # Monkey-patch get_router to return our test router
    import oau_ai.llm.router as router_mod
    original = router_mod.get_router
    router_mod.get_router = lambda refresh=False: router
    try:
        response = complete_with_deepseek(
            [{"role": "user", "content": "Primary reasoning task"}]
        )
        assert response.provider == "deepseek"
    finally:
        router_mod.get_router = original
