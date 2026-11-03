"""Shared production configuration for Phase 3 V2.

Environment variables already set by the process take precedence over values
stored in the project's .env file. Secrets are never included in diagnostic
output and are never stored in source code.
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from dotenv import load_dotenv

KNOWN_PROVIDERS = ("deepseek", "groq")
DEFAULT_ORDER = ("deepseek",)

# Load the project-root .env. Existing process environment variables
# are preserved because override=False.
# Project root is two levels up from this file (src/oau_ai/config.py).
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _normalise_base_url(value: str, default: str) -> str:
    url = (value or default).strip().rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url


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
class VectorizeConfig:
    api_token: Optional[str]
    account_id: Optional[str]
    index_name: str
    dimensions: int

    @property
    def configured(self) -> bool:
        return bool(self.api_token and self.account_id)

    @property
    def index_url(self) -> str:
        return (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/vectorize/v2/indexes/{self.index_name}"
        )


@dataclass(frozen=True)
class LLMSettings:
    providers: Dict[str, ProviderConfig]
    fallback_order: Tuple[str, ...]
    health_ttl_seconds: float = 30.0

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
    ) -> "LLMSettings":
        e = dict(os.environ if env is None else env)

        timeout = max(1.0, _float(e, "LLM_TIMEOUT_SECONDS", 60.0))
        max_tokens = max(1, _int(e, "LLM_MAX_TOKENS", 1024))
        temperature = _float(e, "LLM_TEMPERATURE", 0.2)
        max_retries = max(1, _int(e, "LLM_MAX_RETRIES", 3))
        backoff = max(0.0, _float(e, "LLM_RETRY_BACKOFF_SECONDS", 1.5))
        health_ttl = max(0.0, _float(e, "LLM_HEALTH_TTL_SECONDS", 30.0))

        deepseek_key = (e.get("DEEPSEEK_API_KEY") or "").strip() or None
        groq_key = (e.get("GROQ_API_KEY") or "").strip() or None

        deepseek_base = _normalise_base_url(
            e.get("DEEPSEEK_BASE_URL", ""),
            "https://api.deepseek.com/v1",
        )
        groq_base = _normalise_base_url(
            e.get("GROQ_BASE_URL", ""),
            "https://api.groq.com/openai/v1",
        )

        providers = {
            "deepseek": ProviderConfig(
                name="deepseek",
                enabled=bool(deepseek_key),
                base_url=deepseek_base,
                model=(e.get("DEEPSEEK_MODEL") or "deepseek-chat").strip(),
                api_key=deepseek_key,
                timeout_seconds=timeout,
                max_tokens=max_tokens,
                temperature=temperature,
                max_retries=max_retries,
                retry_backoff_seconds=backoff,
                supports_response_format=True,
            ),
            "groq": ProviderConfig(
                name="groq",
                enabled=bool(groq_key),
                base_url=groq_base,
                model=(e.get("GROQ_MODEL") or "llama-3.1-8b-instant").strip(),
                api_key=groq_key,
                timeout_seconds=timeout,
                max_tokens=max_tokens,
                temperature=temperature,
                max_retries=max_retries,
                retry_backoff_seconds=backoff,
                supports_response_format=True,
            ),
        }

        raw_order = (
            e.get("LLM_FALLBACK_ORDER") or ",".join(DEFAULT_ORDER)
        ).split(",")

        order = []
        for item in raw_order:
            name = item.strip().lower()
            if name in KNOWN_PROVIDERS and name not in order:
                order.append(name)

        for name in DEFAULT_ORDER:
            if name not in order:
                order.append(name)

        primary = (e.get("LLM_PRIMARY_PROVIDER") or "").strip().lower()

        if primary in order:
            order.remove(primary)
            order.insert(0, primary)

        vectorize = VectorizeConfig(
            api_token=(e.get("VECTORIZE_API_TOKEN") or "").strip() or None,
            account_id=(e.get("VECTORIZE_ACCOUNT_ID") or "").strip() or None,
            index_name=(e.get("VECTORIZE_INDEX_NAME") or "oau-thesis-chunks").strip(),
            dimensions=max(1, _int(e, "VECTORIZE_DIMENSIONS", 1024)),
        )

        return cls(
            providers=providers,
            fallback_order=tuple(order),
            health_ttl_seconds=health_ttl,
        )

    def enabled_order(self) -> Tuple[str, ...]:
        return tuple(
            name
            for name in self.fallback_order
            if name in self.providers and self.providers[name].enabled
        )

    def primary_provider(self) -> Optional[str]:
        order = self.enabled_order()
        return order[0] if order else None

    def redacted_dict(self) -> Dict:
        return {
            "fallback_order": list(self.fallback_order),
            "enabled_order": list(self.enabled_order()),
            "primary_provider": self.primary_provider(),
            "health_ttl_seconds": self.health_ttl_seconds,
            "providers": {
                name: {
                    "enabled": provider.enabled,
                    "base_url": provider.base_url,
                    "model": provider.model,
                    "timeout_seconds": provider.timeout_seconds,
                    "max_tokens": provider.max_tokens,
                    "temperature": provider.temperature,
                    "max_retries": provider.max_retries,
                    "api_key_set": bool(provider.api_key),
                }
                for name, provider in self.providers.items()
            },
        }


_settings_cache: Optional[LLMSettings] = None


def get_settings(refresh: bool = False) -> LLMSettings:
    global _settings_cache
    if _settings_cache is None or refresh:
        _settings_cache = LLMSettings.from_env()
    return _settings_cache


def get_vectorize_config(
    env: Optional[Mapping[str, str]] = None,
) -> VectorizeConfig:
    e = dict(os.environ if env is None else env)
    return VectorizeConfig(
        api_token=(e.get("VECTORIZE_API_TOKEN") or "").strip() or None,
        account_id=(e.get("VECTORIZE_ACCOUNT_ID") or "").strip() or None,
        index_name=(e.get("VECTORIZE_INDEX_NAME") or "oau-thesis-chunks").strip(),
        dimensions=max(1, _int(e, "VECTORIZE_DIMENSIONS", 1024)),
    )
