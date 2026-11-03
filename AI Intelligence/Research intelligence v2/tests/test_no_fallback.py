"""Tests for DeepSeek failure without automatic provider switching."""

import httpx
import pytest

from oau_ai.config import LLMSettings, ProviderConfig
from oau_ai.llm.base import ChatMessage, ChatRequest
from oau_ai.llm.router import (
    ProviderRouter,
    TaskDesignation,
    complete_with_deepseek,
)
from oau_ai.errors import ProviderUnavailableError


def _transport(status: int, json_body: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=json_body, request=request)

    return httpx.MockTransport(handler)


def _response_json(content: str = "ok") -> dict:
    return {
        "id": "chatcmpl-test",
        "model": "test-model",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }


def test_deepseek_failure_no_groq_fallback():
    """When DeepSeek fails, no automatic fallback to Groq occurs."""
    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="sk-test",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    groq_cfg = ProviderConfig(
        name="groq",
        enabled=True,
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
        api_key="sk-groq-test",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )

    # DeepSeek always fails with 500
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg, "groq": groq_cfg},
            fallback_order=("deepseek",),
        ),
        transports={
            "deepseek": _transport(500, {"error": "internal"}),
            "groq": None,
        },
    )

    with pytest.raises(ProviderUnavailableError):
        router.complete_deepseek(
            ChatRequest(
                messages=[ChatMessage(role="user", content="Hello")]
            )
        )


def test_deepseek_unavailable_returns_structured_error():
    """DeepSeek unavailable returns ProviderUnavailableError with trace_id."""
    from oau_ai.errors import Phase3Error

    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=False,  # Not enabled because no API key
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key=None,
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg},
            fallback_order=("deepseek",),
        ),
        transports={},
    )

    # DeepSeek not enabled -> provider not available
    with pytest.raises(ProviderUnavailableError):
        router.complete_deepseek(
            ChatRequest(
                messages=[ChatMessage(role="user", content="Hello")]
            )
        )


def test_groq_requires_explicit_designation_even_when_deepseek_fails():
    """Even when DeepSeek fails, Groq still requires explicit designation."""
    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="sk-test",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    groq_cfg = ProviderConfig(
        name="groq",
        enabled=True,
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
        api_key="sk-groq-test",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )

    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg, "groq": groq_cfg},
            fallback_order=("deepseek",),
        ),
        transports={
            "deepseek": _transport(500, {"error": "internal"}),
            "groq": _transport(200, _response_json()),
        },
    )

    # DeepSeek fails
    with pytest.raises(ProviderUnavailableError):
        router.complete_deepseek(
            ChatRequest(
                messages=[ChatMessage(role="user", content="Hello")]
            )
        )

    # Groq still requires designation - cannot be used as fallback
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="Fallback attempt")]
    )
    from oau_ai.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        router.complete_groq_designated(request, designation=None)

    # But with explicit designation, Groq works
    designation = TaskDesignation(
        task_type="query_classification",
        reason="explicitly designated smaller task",
    )
    response = router.complete_groq_designated(request, designation=designation)
    assert response.provider == "groq"
    assert response.content == "ok"


def test_complete_with_deepseek_routes_to_deepseek():
    """complete_with_deepseek convenience routes to DeepSeek provider."""
    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="sk-test",
        max_retries=1,
        retry_backoff_seconds=0.1,
    )
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg},
            fallback_order=("deepseek",),
        ),
        transports={"deepseek": _transport(200, _response_json())},
    )

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
