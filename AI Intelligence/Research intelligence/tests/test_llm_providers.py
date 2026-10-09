import json

import httpx
import pytest

from llm_config import LLMSettings
from llm_providers import (
    ChatMessage, ChatRequest, LLMMalformedResponseError, LLMServiceUnavailableError,
    ProviderRouter,
)


def make_settings(**overrides):
    env = {
        "GROQ_API_KEY": "gsk_test_secret",
        "LMSTUDIO_ENABLED": "false",
        "LLM_MAX_RETRIES": "2",
        "LLM_RETRY_BACKOFF_SECONDS": "0.01",
        "LLM_TIMEOUT_SECONDS": "5",
    }
    env.update(overrides)
    return LLMSettings.from_env(env)


def completion_body(content="ok", model="test-model"):
    return {
        "id": "chatcmpl-1",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def provider_transport(chat_script):
    state = {"calls": []}

    def handler(request):
        if request.url.path.endswith("/models"):
            item = chat_script.get("models", httpx.Response(200, json={"data": [{"id": "m"}]}))
        else:
            state["calls"].append(request)
            idx = len(state["calls"]) - 1
            script = chat_script.get("chat", [httpx.Response(200, json=completion_body())])
            item = script[idx] if idx < len(script) else script[-1]
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.MockTransport(handler), state


def make_router(settings, transports):
    return ProviderRouter(settings=settings, transports=transports)


def req():
    return ChatRequest(messages=[ChatMessage("user", "hello")])


def test_provider_selection_and_order():
    settings = make_settings(LLM_FALLBACK_ORDER="lmstudio,groq", LMSTUDIO_ENABLED="true")
    assert settings.enabled_order() == ("lmstudio", "groq")


def test_primary_provider_moves_front():
    settings = make_settings(LLM_PRIMARY_PROVIDER="lmstudio", LMSTUDIO_ENABLED="true")
    assert settings.enabled_order()[0] == "lmstudio"


def test_missing_credentials_disable_provider():
    settings = make_settings(GROQ_API_KEY="", LMSTUDIO_ENABLED="true")
    assert "groq" not in settings.enabled_order()
    assert "lmstudio" in settings.enabled_order()


def test_deepseek_optional_disabled_without_key_and_enabled_with_key():
    assert "deepseek" not in make_settings().enabled_order()
    assert "deepseek" in make_settings(DEEPSEEK_API_KEY="sk-ds-test").enabled_order()


def test_settings_load_without_any_credentials():
    settings = LLMSettings.from_env({})
    assert settings.enabled_order() == ("lmstudio",)
    router = ProviderRouter(settings=settings)
    assert router.describe()["enabled_order"] == ["lmstudio"]


def test_redacted_settings_hide_secrets():
    redacted = json.dumps(make_settings().redacted_dict())
    assert "gsk_test_secret" not in redacted
    assert make_settings().redacted_dict()["providers"]["groq"]["api_key_set"] is True


def test_timeout_falls_back_to_next_provider():
    settings = make_settings(LMSTUDIO_ENABLED="true")
    groq_t, groq_state = provider_transport({"chat": [httpx.ConnectTimeout("timed out")]})
    lm_t, _ = provider_transport({"chat": [httpx.Response(200, json=completion_body("local answer"))]})
    router = make_router(settings, {"groq": groq_t, "lmstudio": lm_t})
    resp = router.complete(req())
    assert resp.provider == "lmstudio"
    assert len(groq_state["calls"]) == 2  # bounded retries honoured


def test_rate_limit_retry_then_success():
    settings = make_settings()
    groq_t, groq_state = provider_transport({"chat": [
        httpx.Response(429, headers={"retry-after": "0"}),
        httpx.Response(200, json=completion_body("groq answer")),
    ]})
    router = make_router(settings, {"groq": groq_t})
    resp = router.complete(req())
    assert resp.provider == "groq"
    assert resp.content == "groq answer"
    assert len(groq_state["calls"]) == 2


def test_rate_limit_exhausted_falls_back():
    settings = make_settings(LMSTUDIO_ENABLED="true")
    groq_t, _ = provider_transport({"chat": [httpx.Response(429, headers={"retry-after": "0"})]})
    lm_t, _ = provider_transport({"chat": [httpx.Response(200, json=completion_body("local"))]})
    router = make_router(settings, {"groq": groq_t, "lmstudio": lm_t})
    assert router.complete(req()).provider == "lmstudio"


def test_malformed_response_falls_back_without_retry():
    settings = make_settings(LMSTUDIO_ENABLED="true")
    groq_t, groq_state = provider_transport({"chat": [httpx.Response(200, json={"choices": []})]})
    lm_t, _ = provider_transport({"chat": [httpx.Response(200, json=completion_body("local"))]})
    router = make_router(settings, {"groq": groq_t, "lmstudio": lm_t})
    resp = router.complete(req())
    assert resp.provider == "lmstudio"
    assert len(groq_state["calls"]) == 1


def test_malformed_response_raises_on_single_provider():
    settings = make_settings()
    groq_t, _ = provider_transport({"chat": [httpx.Response(200, json={"nope": True})]})
    router = make_router(settings, {"groq": groq_t})
    with pytest.raises(LLMServiceUnavailableError):
        router.complete(req())


def test_auth_error_not_retried():
    settings = make_settings(LMSTUDIO_ENABLED="true")
    groq_t, groq_state = provider_transport({"chat": [httpx.Response(401)]})
    lm_t, _ = provider_transport({"chat": [httpx.Response(200, json=completion_body("local"))]})
    router = make_router(settings, {"groq": groq_t, "lmstudio": lm_t})
    assert router.complete(req()).provider == "lmstudio"
    assert len(groq_state["calls"]) == 1


def test_fallback_order_respected_across_three_providers():
    settings = make_settings(DEEPSEEK_API_KEY="sk-ds-test", LMSTUDIO_ENABLED="true")
    groq_t, _ = provider_transport({"chat": [httpx.Response(500)]})
    lm_t, _ = provider_transport({"models": httpx.ConnectError("refused"),
                                  "chat": [httpx.Response(200, json=completion_body())]})
    ds_t, _ = provider_transport({"chat": [httpx.Response(200, json=completion_body("deepseek"))]})
    router = make_router(settings, {"groq": groq_t, "lmstudio": lm_t, "deepseek": ds_t})
    resp = router.complete(req())
    assert resp.provider == "deepseek"
    assert router._health["lmstudio"].healthy is False


def test_lmstudio_not_assumed_available():
    settings = make_settings(GROQ_API_KEY="", LMSTUDIO_ENABLED="true")
    lm_t, _ = provider_transport({"models": httpx.ConnectError("refused")})
    router = make_router(settings, {"lmstudio": lm_t})
    with pytest.raises(LLMServiceUnavailableError):
        router.complete(req())
    assert router._health["lmstudio"].healthy is False


def test_all_providers_fail_raises_controlled_error_without_leaking_keys():
    settings = make_settings(LMSTUDIO_ENABLED="true")
    groq_t, _ = provider_transport({"chat": [httpx.Response(500)]})
    lm_t, _ = provider_transport({"chat": [httpx.Response(500)]})
    router = make_router(settings, {"groq": groq_t, "lmstudio": lm_t})
    with pytest.raises(LLMServiceUnavailableError) as excinfo:
        router.complete(req())
    message = str(excinfo.value)
    assert "groq" in message and "lmstudio" in message
    assert "gsk_test_secret" not in message


async def test_acomplete_returns_typed_response():
    settings = make_settings()
    groq_t, _ = provider_transport({"chat": [httpx.Response(200, json=completion_body("hello"))]})
    router = make_router(settings, {"groq": groq_t})
    resp = await router.acomplete(req())
    assert resp.provider == "groq"
    assert resp.content == "hello"
    assert resp.usage.total_tokens == 2
    assert resp.finish_reason == "stop"
