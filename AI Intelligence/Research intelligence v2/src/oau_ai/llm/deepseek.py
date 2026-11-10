"""DeepSeek provider — designated primary reasoning/generation provider.

Makes genuine HTTP calls to the DeepSeek chat-completions API.
Mocked transports are injected only by unit tests.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from ..config import ProviderConfig
from .base import (
    ChatRequest,
    ChatResponse,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderHealth,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUpstreamError,
    Usage,
)

logger = logging.getLogger("oau_ai.llm.deepseek")


class DeepSeekProvider:
    name = "deepseek"

    def __init__(
        self,
        config: ProviderConfig,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.config = config
        self._transport = transport

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _payload(self, request: ChatRequest) -> dict:
        cfg = self.config
        payload = {
            "model": request.model or cfg.model,
            "messages": [
                {"role": m.role, "content": m.content} for m in request.messages
            ],
            "temperature": cfg.temperature
            if request.temperature is None
            else request.temperature,
            "max_tokens": cfg.max_tokens
            if request.max_tokens is None
            else request.max_tokens,
        }
        if request.json_mode and cfg.supports_response_format:
            payload["response_format"] = {"type": "json_object"}
        return payload

    @staticmethod
    def _parse(data: dict, model: str) -> ChatResponse:
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderMalformedResponseError(
                "deepseek", "unparsable chat-completion payload"
            )
        if not isinstance(content, str):
            raise ProviderMalformedResponseError(
                "deepseek", "non-string message content"
            )
        usage = None
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = Usage(
                raw_usage.get("prompt_tokens") or 0,
                raw_usage.get("completion_tokens") or 0,
                raw_usage.get("total_tokens") or 0,
            )
        return ChatResponse(
            provider="deepseek",
            model=data.get("model") or model,
            content=content,
            finish_reason=choice.get("finish_reason"),
            usage=usage,
            response_id=data.get("id"),
        )

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raw = resp.headers.get("retry-after")
            retry_after = None
            if raw and raw.replace(".", "", 1).isdigit():
                retry_after = float(raw)
            raise ProviderRateLimitError(
                "deepseek", "rate limited (HTTP 429)", retry_after
            )
        if resp.status_code in (401, 403):
            raise ProviderAuthError(
                "deepseek", f"authentication rejected (HTTP {resp.status_code})"
            )
        if resp.status_code in (408, 504):
            raise ProviderTimeoutError(
                "deepseek", f"upstream timeout (HTTP {resp.status_code})"
            )
        if 500 <= resp.status_code < 600:
            raise ProviderUpstreamError(
                "deepseek", f"upstream error (HTTP {resp.status_code})"
            )
        if resp.status_code >= 400:
            detail = resp.text.strip()[:500] or "empty response body"
            raise ProviderError(
                "deepseek",
                f"request rejected (HTTP {resp.status_code}): {detail}",
            )

    def _backoff(self, attempt: int, err: ProviderError) -> float:
        if isinstance(err, ProviderRateLimitError) and err.retry_after is not None:
            return min(err.retry_after, 30.0)
        return min(self.config.retry_backoff_seconds * (2 ** attempt), 30.0)

    def _client(self, timeout: float) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(transport=self._transport, timeout=timeout)
        return httpx.Client(timeout=timeout)

    def _aclient(self, timeout: float) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(transport=self._transport, timeout=timeout)
        return httpx.AsyncClient(timeout=timeout)

    def _post_sync(self, request: ChatRequest) -> ChatResponse:
        timeout = request.timeout_seconds or self.config.timeout_seconds
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        with self._client(timeout) as client:
            resp = client.post(
                url, headers=self._headers(), json=self._payload(request)
            )
        self._raise_for_status(resp)
        try:
            data = resp.json()
        except ValueError:
            raise ProviderMalformedResponseError(
                "deepseek", "non-JSON response body"
            )
        return self._parse(data, request.model or self.config.model)

    async def _post_async(self, request: ChatRequest) -> ChatResponse:
        timeout = request.timeout_seconds or self.config.timeout_seconds
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        async with self._aclient(timeout) as client:
            resp = await client.post(
                url, headers=self._headers(), json=self._payload(request)
            )
        self._raise_for_status(resp)
        try:
            data = resp.json()
        except ValueError:
            raise ProviderMalformedResponseError(
                "deepseek", "non-JSON response body"
            )
        return self._parse(data, request.model or self.config.model)

    def complete(self, request: ChatRequest) -> ChatResponse:
        attempts = max(1, self.config.max_retries)
        last: Optional[ProviderError] = None
        for attempt in range(attempts):
            try:
                started = time.perf_counter()
                result = self._post_sync(request)
                logger.info(
                    "llm.complete provider=deepseek model=%s latency_ms=%.1f",
                    result.model,
                    (time.perf_counter() - started) * 1000.0,
                )
                return result
            except ProviderError as exc:
                last = exc
                if not exc.retryable or attempt + 1 >= attempts:
                    break
                time.sleep(self._backoff(attempt, exc))
            except httpx.TimeoutException as exc:
                last = ProviderTimeoutError(
                    "deepseek", f"request timeout: {type(exc).__name__}"
                )
                if attempt + 1 >= attempts:
                    break
                time.sleep(self._backoff(attempt, last))
            except httpx.HTTPError as exc:
                last = ProviderConnectionError(
                    "deepseek", f"connection error: {type(exc).__name__}"
                )
                if attempt + 1 >= attempts:
                    break
                time.sleep(self._backoff(attempt, last))
        assert last is not None
        raise last

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        attempts = max(1, self.config.max_retries)
        last: Optional[ProviderError] = None
        for attempt in range(attempts):
            try:
                started = time.perf_counter()
                result = await self._post_async(request)
                logger.info(
                    "llm.acomplete provider=deepseek model=%s latency_ms=%.1f",
                    result.model,
                    (time.perf_counter() - started) * 1000.0,
                )
                return result
            except ProviderError as exc:
                last = exc
                if not exc.retryable or attempt + 1 >= attempts:
                    break
                await _async_sleep(self._backoff(attempt, exc))
            except httpx.TimeoutException as exc:
                last = ProviderTimeoutError(
                    "deepseek", f"request timeout: {type(exc).__name__}"
                )
                if attempt + 1 >= attempts:
                    break
                await _async_sleep(self._backoff(attempt, last))
            except httpx.HTTPError as exc:
                last = ProviderConnectionError(
                    "deepseek", f"connection error: {type(exc).__name__}"
                )
                if attempt + 1 >= attempts:
                    break
                await _async_sleep(self._backoff(attempt, last))
        assert last is not None
        raise last

    def health(self) -> ProviderHealth:
        timeout = min(self.config.timeout_seconds, 10.0)
        with self._client(timeout) as client:
            return self._health_probe(
                lambda: client.get(
                    self.config.base_url.rstrip("/") + "/models",
                    headers=self._headers(),
                )
            )

    async def ahealth(self) -> ProviderHealth:
        timeout = min(self.config.timeout_seconds, 10.0)
        async with self._aclient(timeout) as client:
            return await self._ahealth_probe(client)

    def _health_probe(self, client_get) -> ProviderHealth:
        started = time.perf_counter()
        try:
            resp = client_get()
            latency = (time.perf_counter() - started) * 1000.0
            if resp.status_code == 200:
                return ProviderHealth("deepseek", True, latency, None, time.time())
            return ProviderHealth(
                "deepseek",
                False,
                latency,
                f"models endpoint HTTP {resp.status_code}",
                time.time(),
            )
        except Exception as exc:
            return ProviderHealth(
                "deepseek",
                False,
                (time.perf_counter() - started) * 1000.0,
                type(exc).__name__,
                time.time(),
            )

    async def _ahealth_probe(self, client: httpx.AsyncClient) -> ProviderHealth:
        started = time.perf_counter()
        try:
            resp = await client.get(
                self.config.base_url.rstrip("/") + "/models",
                headers=self._headers(),
            )
            latency = (time.perf_counter() - started) * 1000.0
            if resp.status_code == 200:
                return ProviderHealth("deepseek", True, latency, None, time.time())
            return ProviderHealth(
                "deepseek",
                False,
                latency,
                f"models endpoint HTTP {resp.status_code}",
                time.time(),
            )
        except Exception as exc:
            return ProviderHealth(
                "deepseek",
                False,
                (time.perf_counter() - started) * 1000.0,
                type(exc).__name__,
                time.time(),
            )


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
