"""Tests for the LLM provider router — end-to-end routing behavior.

Covers: DeepSeek primary selection, Groq designated-tasks-only, no automatic
fallback on provider failure, and auth errors being non-retryable.
"""

import pytest

from oau_ai.config import ProviderConfig, get_settings, LLMSettings
from oau_ai.llm.base import ChatMessage, ChatRequest
from oau_ai.llm.router import (
    ProviderRouter,
    TaskDesignation,
    complete_with_deepseek,
    complete_with_groq_designated,
)
from oau_ai.errors import ConfigurationError, ProviderUnavailableError

import httpx


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


def test_settings_designate_deepseek_primary():
    """LLM settings designate DeepSeek as primary provider when enabled."""
    env = {
        "DEEPSEEK_API_KEY": "sk-test",
        "GROQ_API_KEY": "sk-groq-test",
        "LLM_PRIMARY_PROVIDER": "deepseek",
        "LLM_FALLBACK_ORDER": "deepseek",
    }
    settings = LLMSettings.from_env(env)
    order = settings.enabled_order()
    assert order == ("deepseek",)
    assert settings.primary_provider() == "deepseek"


def test_groq_configured_but_not_primary():
    """Groq may be configured but is not the primary provider."""
    env = {
        "DEEPSEEK_API_KEY": "sk-test",
        "GROQ_API_KEY": "sk-groq-test",
        "LLM_PRIMARY_PROVIDER": "deepseek",
    }
    settings = LLMSettings.from_env(env)
    order = settings.enabled_order()
    assert "deepseek" in order
    assert order[0] == "deepseek"
    if "groq" in order:
        assert order.index("groq") > 0


def test_deepseek_router_returns_response_on_success():
    """Router returns a ChatResponse when DeepSeek succeeds."""
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

    response = router.complete_deepseek(
        ChatRequest(
            messages=[ChatMessage(role="user", content="Primary reasoning")]
        )
    )
    assert response.provider == "deepseek"
    assert response.content == "ok"


def test_router_raises_on_deepseek_failure_no_groq_fallback():
    """Router raises ProviderUnavailableError when DeepSeek fails — no Groq fallback."""
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

    # DeepSeek always fails with 500.
    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg, "groq": groq_cfg},
            fallback_order=("deepseek",),
        ),
        transports={"deepseek": _transport(500, {"error": "internal"}), "groq": None},
    )

    with pytest.raises(ProviderUnavailableError):
        router.complete_deepseek(
            ChatRequest(
                messages=[ChatMessage(role="user", content="Hello")]
            )
        )


def test_groq_requires_explicit_designation():
    """Groq completion rejects missing/empty TaskDesignation."""
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
            providers={"groq": groq_cfg},
            fallback_order=("groq",),
        ),
        transports={"groq": _transport(200, _response_json())},
    )

    request = ChatRequest(
        messages=[ChatMessage(role="user", content="Task")]
    )

    with pytest.raises(ConfigurationError):
        router.complete_groq_designated(request, designation=None)

    with pytest.raises(ConfigurationError):
        router.complete_groq_designated(
            request, designation=TaskDesignation(task_type="", reason="")
        )


def test_groq_designated_task_succeeds():
    """Groq completes when explicitly designated with a valid TaskDesignation."""
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
            providers={"groq": groq_cfg},
            fallback_order=("groq",),
        ),
        transports={"groq": _transport(200, _response_json())},
    )

    request = ChatRequest(
        messages=[ChatMessage(role="user", content="Small task")]
    )
    designation = TaskDesignation(
        task_type="query_classification",
        reason="designated smaller task for Groq",
    )
    response = router.complete_groq_designated(request, designation=designation)
    assert response.provider == "groq"
    assert response.content == "ok"


def test_deepseek_auth_error_non_retryable():
    """DeepSeek 401 auth error is non-retryable and raised immediately.

    The health check (/models) must pass so the router reaches the actual
    completion call, which returns 401. No retry occurs for auth errors.
    """
    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="bad-key",
        max_retries=3,
        retry_backoff_seconds=0.1,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/models" in url:
            return httpx.Response(200, json={"data": []}, request=request)
        if "/chat/completions" in url:
            return httpx.Response(401, json={"error": "invalid key"}, request=request)
        return httpx.Response(404, request=request)

    router = ProviderRouter(
        settings=LLMSettings(
            providers={"deepseek": deepseek_cfg},
            fallback_order=("deepseek",),
        ),
        transports={"deepseek": httpx.MockTransport(handler)},
    )

    from oau_ai.llm.base import ProviderAuthError

    with pytest.raises(ProviderAuthError):
        router.complete_deepseek(
            ChatRequest(
                messages=[ChatMessage(role="user", content="Hello")]
            )
        )


def test_complete_with_deepseek_convenience():
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
            [{"role": "user", "content": "Generate answer"}],
            model="deepseek-chat",
        )
        assert response.provider == "deepseek"
        assert response.content == "ok"
    finally:
        router_mod.get_router = original


def test_describe_returns_redacted_config_no_secrets():
    """Router describe() returns redacted config — no API keys leaked."""
    deepseek_cfg = ProviderConfig(
        name="deepseek",
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="sk-secret",
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

    info = router.describe()
    assert info["primary_provider"] == "deepseek"
    for name, prov in info["providers"].items():
        assert "api_key" not in prov
        assert prov["api_key_set"] is True or prov["api_key_set"] is False
