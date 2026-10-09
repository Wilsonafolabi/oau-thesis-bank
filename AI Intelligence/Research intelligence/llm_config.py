"""Shared production LLM configuration.

All provider settings come from environment variables (see .env.example).
Secrets are never logged; use LLMSettings.redacted_dict() for diagnostics.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

KNOWN_PROVIDERS = ("groq", "lmstudio", "deepseek")
DEFAULT_ORDER = ("groq", "lmstudio", "deepseek")


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    enabled: bool
    base_url: str
    model: str
    api_key: Optional[str] = None
    timeout_seconds: float = 60.0
    max_tokens: int = 1024
    temperature: float = 0.2
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5
    supports_response_format: bool = True

    @property
    def chat_completions_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    @property
    def models_url(self) -> str:
        return self.base_url.rstrip("/") + "/models"


@dataclass(frozen=True)
class LLMSettings:
    providers: Dict[str, ProviderConfig]
    fallback_order: Tuple[str, ...]
    health_ttl_seconds: float = 30.0

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "LLMSettings":
        e = dict(os.environ if env is None else env)
        timeout = _float(e, "LLM_TIMEOUT_SECONDS", 60.0)
        max_tokens = _int(e, "LLM_MAX_TOKENS", 1024)
        temperature = _float(e, "LLM_TEMPERATURE", 0.2)
        max_retries = _int(e, "LLM_MAX_RETRIES", 3)
        backoff = _float(e, "LLM_RETRY_BACKOFF_SECONDS", 1.5)
        health_ttl = _float(e, "LLM_HEALTH_TTL_SECONDS", 30.0)

        groq_key = e.get("GROQ_API_KEY") or None
        deepseek_key = e.get("DEEPSEEK_API_KEY") or None

        lm_base = (e.get("LMSTUDIO_BASE_URL") or e.get("LM_STUDIO_URL") or "http://127.0.0.1:1234/v1").rstrip("/")
        if lm_base.endswith("/chat/completions"):
            lm_base = lm_base[: -len("/chat/completions")]
        if e.get("LMSTUDIO_ENABLED") is not None and e.get("LMSTUDIO_ENABLED") != "":
            lm_enabled = _bool(e, "LMSTUDIO_ENABLED", True)
        else:
            lm_enabled = _bool(e, "USE_LOCAL_LLM", True)
        lm_model = e.get("LMSTUDIO_MODEL") or e.get("LOCAL_MODEL") or "qwen2.5-vl-7b-instruct"

        providers = {
            "groq": ProviderConfig("groq", bool(groq_key),
                                   e.get("GROQ_BASE_URL") or "https://api.groq.com/openai/v1",
                                   e.get("GROQ_MODEL") or "llama-3.3-70b-versatile",
                                   groq_key, timeout, max_tokens, temperature, max_retries, backoff, True),
            "lmstudio": ProviderConfig("lmstudio", lm_enabled, lm_base, lm_model, None,
                                       timeout, max_tokens, temperature, max_retries, backoff, False),
            "deepseek": ProviderConfig("deepseek", bool(deepseek_key),
                                       e.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1",
                                       e.get("DEEPSEEK_MODEL") or "deepseek-chat",
                                       deepseek_key, timeout, max_tokens, temperature, max_retries, backoff, True),
        }

        raw_order = (e.get("LLM_FALLBACK_ORDER") or ",".join(DEFAULT_ORDER)).split(",")
        order = [p.strip().lower() for p in raw_order if p.strip().lower() in KNOWN_PROVIDERS]
        for p in DEFAULT_ORDER:
            if p not in order:
                order.append(p)
        primary = (e.get("LLM_PRIMARY_PROVIDER") or "").strip().lower()
        if primary in order:
            order.remove(primary)
            order.insert(0, primary)
        return cls(providers=providers, fallback_order=tuple(order), health_ttl_seconds=health_ttl)

    def enabled_order(self) -> Tuple[str, ...]:
        return tuple(n for n in self.fallback_order if self.providers[n].enabled)

    def redacted_dict(self) -> Dict:
        out = {
            "fallback_order": list(self.fallback_order),
            "health_ttl_seconds": self.health_ttl_seconds,
            "providers": {},
        }
        for name, p in self.providers.items():
            out["providers"][name] = {
                "enabled": p.enabled,
                "base_url": p.base_url,
                "model": p.model,
                "timeout_seconds": p.timeout_seconds,
                "max_tokens": p.max_tokens,
                "temperature": p.temperature,
                "max_retries": p.max_retries,
                "api_key_set": bool(p.api_key),
            }
        return out


_settings_cache: Optional[LLMSettings] = None


def get_settings(refresh: bool = False) -> LLMSettings:
    global _settings_cache
    if _settings_cache is None or refresh:
        _settings_cache = LLMSettings.from_env()
    return _settings_cache
