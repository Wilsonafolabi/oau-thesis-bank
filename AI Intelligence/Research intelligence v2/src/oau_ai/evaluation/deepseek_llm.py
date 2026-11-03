"""DeepSeek LLM wrapper for RAGAS evaluation.

Wraps the DeepSeek chat completions API as a LangChain-compatible LLM
for use with RAGAS evaluation. Configuration is read from environment
variables. No network requests are made during initialization; the API
key is only required when :meth:`_call` or :meth:`_acall` is invoked.

The evaluator is configured independently from the answer-generation
client: it creates its own LLM client instance, though it may share the
same ``DEEPSEEK_API_KEY`` environment variable.

Environment variables:
    DEEPSEEK_API_KEY: DeepSeek API key (required at call time, not at
        initialization).
    DEEPSEEK_BASE_URL: DeepSeek API base URL (default:
        https://api.deepseek.com/v1).
    DEEPSEEK_MODEL: DeepSeek model name (default: deepseek-chat).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models import LLM


class DeepSeekLLM(LLM):
    """DeepSeek chat completions LLM for RAGAS evaluation.

    Configuration is read from environment variables. No API calls are
    made during initialization. The API key is only required when
    :meth:`_call` or :meth:`_acall` is invoked.
    """

    model_name: str = "deepseek-chat"
    api_key: Optional[str] = None
    base_url: str = "https://api.deepseek.com/v1"
    temperature: float = 0.2
    max_tokens: int = 1024
    timeout: float = 60.0

    @property
    def _llm_type(self) -> str:
        return "deepseek"

    def _call(
        self,
        prompt: str,
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        import httpx

        api_key = self.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is not set. Set it to use DeepSeek "
                "as the RAGAS evaluation LLM."
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stop:
            payload["stop"] = stop

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def _acall(
        self,
        prompt: str,
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        import httpx

        api_key = self.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is not set. Set it to use DeepSeek "
                "as the RAGAS evaluation LLM."
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stop:
            payload["stop"] = stop

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


def create_deepseek_llm(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
) -> DeepSeekLLM:
    """Create a DeepSeekLLM instance from environment variables.

    Args:
        model_name: Override the model name. Defaults to
            ``DEEPSEEK_MODEL`` env var or ``deepseek-chat``.
        api_key: Override the API key. Defaults to ``DEEPSEEK_API_KEY``
            env var.
        base_url: Override the base URL. Defaults to
            ``DEEPSEEK_BASE_URL`` env var or
            ``https://api.deepseek.com/v1``.
        temperature: Override temperature. Defaults to ``DEEPSEEK_TEMPERATURE``
            env var or ``0.2``.
        max_tokens: Override max tokens. Defaults to
            ``DEEPSEEK_MAX_TOKENS`` env var or ``1024``.
        timeout: Override timeout in seconds. Defaults to
            ``DEEPSEEK_TIMEOUT`` env var or ``60.0``.

    Returns:
        A configured :class:`DeepSeekLLM` instance. No network request is
        made during construction; the API key is only required when the
        LLM is called.
    """
    return DeepSeekLLM(
        model_name=model_name or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
        base_url=base_url
        or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        temperature=temperature
        if temperature is not None
        else float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2")),
        max_tokens=max_tokens
        if max_tokens is not None
        else int(os.getenv("DEEPSEEK_MAX_TOKENS", "1024")),
        timeout=timeout
        if timeout is not None
        else float(os.getenv("DEEPSEEK_TIMEOUT", "60.0")),
    )
