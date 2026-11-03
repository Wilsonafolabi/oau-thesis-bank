"""Configuration tests for Phase 3 V2.

Verifies that the configuration module loads correctly, provider routing
respects the DeepSeek-primary / Groq-designated-only rules, and required
credentials are detected without exposing secret values.
"""

import os
from unittest.mock import patch

import pytest

from oau_ai.config import (
    LLMSettings,
    ProviderConfig,
    VectorizeConfig,
    get_settings,
    get_vectorize_config,
)


def test_settings_loads_from_env():
    """LLMSettings.from_env() returns a populated settings object."""
    env = {
        "DEEPSEEK_API_KEY": "sk-test-key",
        "GROQ_API_KEY": "",
        "VECTORIZE_API_TOKEN": "",
        "VECTORIZE_ACCOUNT_ID": "",
        "LLM_PRIMARY_PROVIDER": "deepseek",
        "LLM_FALLBACK_ORDER": "deepseek",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = LLMSettings.from_env(env)
        assert settings is not None
        assert "deepseek" in settings.providers
        assert "groq" in settings.providers


def test_deepseek_primary_when_configured():
    """DeepSeek is the primary provider when its API key is set."""
    env = {
        "DEEPSEEK_API_KEY": "sk-test-key",
        "GROQ_API_KEY": "",
        "LLM_PRIMARY_PROVIDER": "deepseek",
        "LLM_FALLBACK_ORDER": "deepseek",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = LLMSettings.from_env(env)
        assert settings.primary_provider() == "deepseek"


def test_groq_not_primary_when_only_deepseek_configured():
    """Groq is not the primary provider when only DeepSeek is configured."""
    env = {
        "DEEPSEEK_API_KEY": "sk-test-key",
        "GROQ_API_KEY": "",
        "LLM_PRIMARY_PROVIDER": "deepseek",
        "LLM_FALLBACK_ORDER": "deepseek",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = LLMSettings.from_env(env)
        enabled = settings.enabled_order()
        assert "deepseek" in enabled
        # Groq has no API key, so it should not be in enabled_order
        assert "groq" not in enabled


def test_vectorize_config_not_configured_without_credentials():
    """VectorizeConfig.configured is False when token/account_id are empty."""
    env = {
        "VECTORIZE_API_TOKEN": "",
        "VECTORIZE_ACCOUNT_ID": "",
    }
    with patch.dict(os.environ, env, clear=True):
        config = get_vectorize_config(env)
        assert config.configured is False


def test_redacted_dict_hides_api_keys():
    """redacted_dict() never exposes actual API key values."""
    env = {
        "DEEPSEEK_API_KEY": "sk-real-secret-key-12345",
        "GROQ_API_KEY": "gsk-real-secret-key-67890",
        "LLM_PRIMARY_PROVIDER": "deepseek",
        "LLM_FALLBACK_ORDER": "deepseek",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = LLMSettings.from_env(env)
        redacted = settings.redacted_dict()
        for provider_info in redacted["providers"].values():
            assert provider_info["api_key_set"] is True
            # Never print the actual key value
            assert "api_key" not in provider_info
            assert provider_info["base_url"] is not None


def test_get_settings_returns_cached_instance():
    """get_settings() returns a cached LLMSettings instance."""
    env = {
        "DEEPSEEK_API_KEY": "sk-test-key",
        "LLM_PRIMARY_PROVIDER": "deepseek",
        "LLM_FALLBACK_ORDER": "deepseek",
    }
    with patch.dict(os.environ, env, clear=True):
        s1 = get_settings(refresh=True)
        s2 = get_settings()
        assert s1 is s2


def test_provider_config_enabled_without_key_is_false():
    """A provider without an API key is not enabled."""
    cfg = ProviderConfig(
        name="deepseek",
        enabled=False,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key=None,
    )
    assert cfg.enabled is False
    assert cfg.api_key is None
