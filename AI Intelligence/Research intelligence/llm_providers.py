"""Vendor-neutral LLM provider routing layer.

Typed request/response interface over OpenAI-compatible chat-completions APIs
(Groq, LM Studio, optional DeepSeek). Production code makes genuine HTTP calls;
mocked transports are injected only by unit tests.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

from llm_config import LLMSettings, ProviderConfig, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatRequest:
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout_seconds: Optional[float] = None
    json_mode: bool = False


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ChatResponse:
    provider: str
    model: str
    content: str
    finish_reason: Optional[str] = None
    usage: Optional[Usage] = None
    response_id: Optional[str] = None


@dataclass
class ProviderHealth:
    name: str
    healthy: bool
    latency_ms: float = 0.0
    last_error: Optional[str] = None
    checked_at: float = 0.0


class LLMProviderError(Exception):
    retryable = False

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class LLMTimeoutError(LLMProviderError):
    retryable = True


class LLMConnectionError(LLMProviderError):
    retryable = True


class LLMRateLimitError(LLMProviderError):
    retryable = True

    def __init__(self, provider: str, message: str, retry_after: Optional[float] = None):
        super().__init__(provider, message)
        self.retry_after = retry_after


class LLMUpstreamError(LLMProviderError):
    retryable = True


class LLMAuthError(LLMProviderError):
    retryable = False


class LLMMalformedResponseError(LLMProviderError):
    retryable = False


class LLMServiceUnavailableError(Exception):
    def __init__(self, failures: List):
        self.failures = list(failures)
        super().__init__("All LLM providers failed: " + "; ".join(f"{n}: {m}" for n, m in self.failures))


class BaseProvider:
    name = "base"

    def __init__(self, config: ProviderConfig, transport: Optional[httpx.BaseTransport] = None):
        self.config = config
        self._transport = transport

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _payload(self, request: ChatRequest) -> Dict:
        cfg = self.config
        payload = {
            "model": request.model or cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": cfg.temperature if request.temperature is None else request.temperature,
            "max_tokens": cfg.max_tokens if request.max_tokens is None else request.max_tokens,
        }
        if request.json_mode and cfg.supports_response_format:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _parse(self, data: Dict, model: str) -> ChatResponse:
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMMalformedResponseError(self.name, "unparsable chat-completion payload") from None
        if not isinstance(content, str):
            raise LLMMalformedResponseError(self.name, "non-string message content") from None
        usage = None
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = Usage(raw_usage.get("prompt_tokens") or 0,
                          raw_usage.get("completion_tokens") or 0,
                          raw_usage.get("total_tokens") or 0)
        return ChatResponse(provider=self.name, model=data.get("model") or model, content=content,
                            finish_reason=choice.get("finish_reason"), usage=usage, response_id=data.get("id"))

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raw = resp.headers.get("retry-after")
            retry_after = None
            if raw and raw.replace(".", "", 1).isdigit():
                retry_after = float(raw)
            raise LLMRateLimitError(self.name, "rate limited (HTTP 429)", retry_after)
        if resp.status_code in (401, 403):
            raise LLMAuthError(self.name, f"authentication rejected (HTTP {resp.status_code})")
        if resp.status_code in (408, 504):
            raise LLMTimeoutError(self.name, f"upstream timeout (HTTP {resp.status_code})")
        if 500 <= resp.status_code < 600:
            raise LLMUpstreamError(self.name, f"upstream error (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise LLMProviderError(self.name, f"request rejected (HTTP {resp.status_code})")

    def _backoff(self, attempt: int, err: LLMProviderError) -> float:
        if isinstance(err, LLMRateLimitError) and err.retry_after is not None:
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
        with self._client(timeout) as client:
            resp = client.post(self.config.chat_completions_url, headers=self._headers(), json=self._payload(request))
        self._raise_for_status(resp)
        try:
            data = resp.json()
        except ValueError:
            raise LLMMalformedResponseError(self.name, "non-JSON response body") from None
        return self._parse(data, request.model or self.config.model)

    async def _post_async(self, request: ChatRequest) -> ChatResponse:
        timeout = request.timeout_seconds or self.config.timeout_seconds
        async with self._aclient(timeout) as client:
            resp = await client.post(self.config.chat_completions_url, headers=self._headers(), json=self._payload(request))
        self._raise_for_status(resp)
        try:
            data = resp.json()
        except ValueError:
            raise LLMMalformedResponseError(self.name, "non-JSON response body") from None
        return self._parse(data, request.model or self.config.model)

    def complete(self, request: ChatRequest) -> ChatResponse:
        attempts = max(1, self.config.max_retries)
        last: Optional[LLMProviderError] = None
        for attempt in range(attempts):
            try:
                started = time.perf_counter()
                result = self._post_sync(request)
                logger.info("llm.complete provider=%s model=%s latency_ms=%.1f prompt_chars=%d",
                            self.name, result.model, (time.perf_counter() - started) * 1000.0,
                            sum(len(m.content) for m in request.messages))
                return result
            except LLMProviderError as exc:
                last = exc
                if not exc.retryable or attempt + 1 >= attempts:
                    break
                time.sleep(self._backoff(attempt, exc))
            except httpx.TimeoutException as exc:
                last = LLMTimeoutError(self.name, f"request timeout: {type(exc).__name__}")
                if attempt + 1 >= attempts:
                    break
                time.sleep(self._backoff(attempt, last))
            except httpx.HTTPError as exc:
                last = LLMConnectionError(self.name, f"connection error: {type(exc).__name__}")
                if attempt + 1 >= attempts:
                    break
                time.sleep(self._backoff(attempt, last))
        assert last is not None
        raise last

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        attempts = max(1, self.config.max_retries)
        last: Optional[LLMProviderError] = None
        for attempt in range(attempts):
            try:
                started = time.perf_counter()
                result = await self._post_async(request)
                logger.info("llm.acomplete provider=%s model=%s latency_ms=%.1f prompt_chars=%d",
                            self.name, result.model, (time.perf_counter() - started) * 1000.0,
                            sum(len(m.content) for m in request.messages))
                return result
            except LLMProviderError as exc:
                last = exc
                if not exc.retryable or attempt + 1 >= attempts:
                    break
                await asyncio.sleep(self._backoff(attempt, exc))
            except httpx.TimeoutException as exc:
                last = LLMTimeoutError(self.name, f"request timeout: {type(exc).__name__}")
                if attempt + 1 >= attempts:
                    break
                await asyncio.sleep(self._backoff(attempt, last))
            except httpx.HTTPError as exc:
                last = LLMConnectionError(self.name, f"connection error: {type(exc).__name__}")
                if attempt + 1 >= attempts:
                    break
                await asyncio.sleep(self._backoff(attempt, last))
        assert last is not None
        raise last

    def _health_probe(self, client_get) -> ProviderHealth:
        started = time.perf_counter()
        try:
            resp = client_get()
            latency = (time.perf_counter() - started) * 1000.0
            if resp.status_code == 200:
                return ProviderHealth(self.name, True, latency, None, time.time())
            return ProviderHealth(self.name, False, latency, f"models endpoint HTTP {resp.status_code}", time.time())
        except Exception as exc:
            return ProviderHealth(self.name, False, (time.perf_counter() - started) * 1000.0,
                                  type(exc).__name__, time.time())

    def health(self) -> ProviderHealth:
        timeout = min(self.config.timeout_seconds, 10.0)
        with self._client(timeout) as client:
            return self._health_probe(lambda: client.get(self.config.models_url, headers=self._headers()))

    async def ahealth(self) -> ProviderHealth:
        timeout = min(self.config.timeout_seconds, 10.0)
        async with self._aclient(timeout) as client:
            return self._health_probe(lambda: None) if False else await self._ahealth_probe(client)

    async def _ahealth_probe(self, client: httpx.AsyncClient) -> ProviderHealth:
        started = time.perf_counter()
        try:
            resp = await client.get(self.config.models_url, headers=self._headers())
            latency = (time.perf_counter() - started) * 1000.0
            if resp.status_code == 200:
                return ProviderHealth(self.name, True, latency, None, time.time())
            return ProviderHealth(self.name, False, latency, f"models endpoint HTTP {resp.status_code}", time.time())
        except Exception as exc:
            return ProviderHealth(self.name, False, (time.perf_counter() - started) * 1000.0,
                                  type(exc).__name__, time.time())


class GroqProvider(BaseProvider):
    name = "groq"


class LMStudioProvider(BaseProvider):
    name = "lmstudio"


class DeepSeekProvider(BaseProvider):
    name = "deepseek"


_PROVIDER_CLASSES = {"groq": GroqProvider, "lmstudio": LMStudioProvider, "deepseek": DeepSeekProvider}


class ProviderRouter:
    def __init__(self, settings: Optional[LLMSettings] = None,
                 transports: Optional[Dict[str, httpx.BaseTransport]] = None):
        self.settings = settings or get_settings()
        transports = transports or {}
        self.providers: Dict[str, BaseProvider] = {
            name: cls(cfg, transport=transports.get(name))
            for name, cfg in self.settings.providers.items()
            for cls in [_PROVIDER_CLASSES[name]]
        }
        self._health: Dict[str, ProviderHealth] = {}

    def _order(self):
        return self.settings.enabled_order()

    def _health_ok(self, name: str):
        cached = self._health.get(name)
        if cached is not None and (time.time() - cached.checked_at) < self.settings.health_ttl_seconds:
            return cached.healthy, cached.last_error
        probe = self.providers[name].health()
        self._health[name] = probe
        return probe.healthy, probe.last_error

    async def _ahealth_ok(self, name: str):
        cached = self._health.get(name)
        if cached is not None and (time.time() - cached.checked_at) < self.settings.health_ttl_seconds:
            return cached.healthy, cached.last_error
        probe = await self.providers[name].ahealth()
        self._health[name] = probe
        return probe.healthy, probe.last_error

    def _record_failure(self, name: str, exc: LLMProviderError):
        if isinstance(exc, (LLMConnectionError, LLMAuthError)):
            self._health[name] = ProviderHealth(name, False, 0.0, str(exc), time.time())

    def complete(self, request: ChatRequest) -> ChatResponse:
        failures = []
        for name in self._order():
            healthy, err = self._health_ok(name)
            if not healthy:
                failures.append((name, f"unhealthy: {err}"))
                continue
            try:
                return self.providers[name].complete(request)
            except LLMProviderError as exc:
                logger.warning("llm.provider_failed provider=%s error=%s", name, exc)
                self._record_failure(name, exc)
                failures.append((name, str(exc)))
        raise LLMServiceUnavailableError(failures)

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        failures = []
        for name in self._order():
            healthy, err = await self._ahealth_ok(name)
            if not healthy:
                failures.append((name, f"unhealthy: {err}"))
                continue
            try:
                return await self.providers[name].acomplete(request)
            except LLMProviderError as exc:
                logger.warning("llm.provider_failed provider=%s error=%s", name, exc)
                self._record_failure(name, exc)
                failures.append((name, str(exc)))
        raise LLMServiceUnavailableError(failures)

    def health_status(self, refresh: bool = False) -> Dict[str, ProviderHealth]:
        if refresh:
            self._health.clear()
        out = {}
        for name in self._order():
            self._health_ok(name)
            out[name] = self._health[name]
        return out

    def describe(self) -> Dict:
        info = self.settings.redacted_dict()
        info["enabled_order"] = list(self._order())
        return info


_router_cache: Optional[ProviderRouter] = None


def get_router(refresh: bool = False) -> ProviderRouter:
    global _router_cache
    if _router_cache is None or refresh:
        _router_cache = ProviderRouter(settings=get_settings(refresh=refresh))
    return _router_cache


def chat(messages: List[ChatMessage], **kwargs) -> ChatResponse:
    return get_router().complete(ChatRequest(messages=messages, **kwargs))


async def achat(messages: List[ChatMessage], **kwargs) -> ChatResponse:
    return await get_router().acomplete(ChatRequest(messages=messages, **kwargs))
