"""Cloudflare Vectorize service — vector index for thesis chunk embeddings.

Vectorize stores embeddings and retrieval metadata only. It does NOT replace
the document repository. Canonical chunk text and provenance live in
PostgreSQL. Vectorize point IDs map back to chunk IDs stored in PostgreSQL.

Makes genuine HTTP calls to the Cloudflare Vectorize API. Mocked transports
are injected only by unit tests.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from ..config import VectorizeConfig, get_vectorize_config
from ..errors import ConfigurationError, ProviderUnavailableError

logger = logging.getLogger("oau_ai.vectorize")


def metadata_in_filter(field: str, values: List[Any]) -> Dict[str, Any]:
    """Build a Cloudflare Vectorize metadata membership filter."""
    return {field: {"$in": list(values)}}


class VectorizeService:
    """Client for a Cloudflare Vectorize index.

    Provides upsert (embedding + metadata) and query (nearest neighbors).
    Returns Vectorize point IDs; callers map back to canonical chunk records
    stored in PostgreSQL.
    """

    def __init__(
        self,
        config: Optional[VectorizeConfig] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.config = config or get_vectorize_config()
        self._transport = transport
        if not self.config.configured:
            logger.warning(
                "Vectorize not configured: API token or account ID missing."
            )

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_token:
            headers["Authorization"] = f"Bearer {self.config.api_token}"
        return headers

    def _client(self, timeout: float) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(transport=self._transport, timeout=timeout)
        return httpx.Client(timeout=timeout)

    def _aclient(self, timeout: float) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(transport=self._transport, timeout=timeout)
        return httpx.AsyncClient(timeout=timeout)

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code in (401, 403):
            raise ProviderUnavailableError(
                message=f"Vectorize authentication rejected (HTTP {resp.status_code})",
                component="vectorize",
            )
        if resp.status_code >= 400:
            # Capture the response body for diagnostics — Cloudflare may
            # include a specific error code/message in the body.
            detail = resp.text[:500]
            raise ProviderUnavailableError(
                message=(
                    f"Vectorize request rejected (HTTP {resp.status_code}): {detail}"
                ),
                component="vectorize",
            )

    def is_configured(self) -> bool:
        return self.config.configured

    def upsert(
        self,
        vectors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Upsert vectors with metadata into the index.

        Each vector item should include:
          - id: Vectorize point id (maps to canonical chunk_id externally)
          - values: embedding float list
          - metadata: retrieval metadata (document_id, chunk_id, access_classification, etc.)
        """
        if not self.config.configured:
            raise ConfigurationError(
                code="vectorize_not_configured",
                message=(
                    "Cloudflare Vectorize is not configured. Set VECTORIZE_API_TOKEN "
                    "and VECTORIZE_ACCOUNT_ID."
                ),
                component="vectorize",
            )
        url = self.config.index_url + "/upsert"
        payload = {"vectors": vectors}
        started = time.perf_counter()
        try:
            with self._client(60.0) as client:
                resp = client.post(url, headers=self._headers(), json=payload)
            self._raise_for_status(resp)
            return resp.json()
        except httpx.HTTPError as exc:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
            logger.error(
                "vectorize.upsert_failed error=%s duration_ms=%s",
                type(exc).__name__,
                duration_ms,
            )
            raise ProviderUnavailableError(
                message=f"Vectorize upsert failed: {exc}",
                component="vectorize",
            ) from exc

    async def aupsert(
        self,
        vectors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self.config.configured:
            raise ConfigurationError(
                code="vectorize_not_configured",
                message=(
                    "Cloudflare Vectorize is not configured. Set VECTORIZE_API_TOKEN "
                    "and VECTORIZE_ACCOUNT_ID."
                ),
                component="vectorize",
            )
        url = self.config.index_url + "/upsert"
        payload = {"vectors": vectors}
        started = time.perf_counter()
        try:
            async with self._aclient(60.0) as client:
                resp = await client.post(
                    url, headers=self._headers(), json=payload
                )
            self._raise_for_status(resp)
            return resp.json()
        except httpx.HTTPError as exc:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
            logger.error(
                "vectorize.aupsert_failed error=%s duration_ms=%s",
                type(exc).__name__,
                duration_ms,
            )
            raise ProviderUnavailableError(
                message=f"Vectorize upsert failed: {exc}",
                component="vectorize",
            ) from exc

    async def adelete(self, ids: List[str]) -> Dict[str, Any]:
        """Delete vectors by point id from the index."""
        if not ids:
            return {"deleted": 0}
        if not self.config.configured:
            raise ConfigurationError(
                code="vectorize_not_configured",
                message=(
                    "Cloudflare Vectorize is not configured. Set VECTORIZE_API_TOKEN "
                    "and VECTORIZE_ACCOUNT_ID."
                ),
                component="vectorize",
            )
        url = self.config.index_url + "/delete"
        payload = {"ids": ids}
        started = time.perf_counter()
        try:
            async with self._aclient(60.0) as client:
                resp = await client.post(
                    url, headers=self._headers(), json=payload
                )
            self._raise_for_status(resp)
            return resp.json()
        except httpx.HTTPError as exc:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
            logger.error(
                "vectorize.adelete_failed error=%s duration_ms=%s",
                type(exc).__name__,
                duration_ms,
            )
            raise ProviderUnavailableError(
                message=f"Vectorize delete failed: {exc}",
                component="vectorize",
            ) from exc

    def query(
        self,
        vector: List[float],
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Query nearest neighbors. Returns Vectorize matches with point ids
        and scores. Callers map point ids back to canonical chunk records."""
        if not self.config.configured:
            raise ConfigurationError(
                code="vectorize_not_configured",
                message=(
                    "Cloudflare Vectorize is not configured. Set VECTORIZE_API_TOKEN "
                    "and VECTORIZE_ACCOUNT_ID."
                ),
                component="vectorize",
            )
        # Validate dimension against configured index dimension to catch
        # mismatches before they reach Cloudflare as HTTP 400s.
        if len(vector) != self.config.dimensions:
            raise ProviderUnavailableError(
                message=(
                    f"Vector dimension mismatch: query vector has {len(vector)} "
                    f"dimensions but index is configured for "
                    f"{self.config.dimensions} dimensions."
                ),
                component="vectorize",
            )
        url = self.config.index_url + "/query"
        payload: Dict[str, Any] = {
            "vector": vector,
            "topK": top_k,
            "returnValues": True,
            "returnMetadata": "all",
        }
        if filter:
            payload["filter"] = filter
        started = time.perf_counter()
        try:
            with self._client(60.0) as client:
                resp = client.post(url, headers=self._headers(), json=payload)
            self._raise_for_status(resp)
            return resp.json()
        except httpx.HTTPError as exc:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
            logger.error(
                "vectorize.query_failed error=%s duration_ms=%s",
                type(exc).__name__,
                duration_ms,
            )
            raise ProviderUnavailableError(
                message=f"Vectorize query failed: {exc}",
                component="vectorize",
            ) from exc

    async def aquery(
        self,
        vector: List[float],
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.config.configured:
            raise ConfigurationError(
                code="vectorize_not_configured",
                message=(
                    "Cloudflare Vectorize is not configured. Set VECTORIZE_API_TOKEN "
                    "and VECTORIZE_ACCOUNT_ID."
                ),
                component="vectorize",
            )
        # Validate dimension against configured index dimension.
        if len(vector) != self.config.dimensions:
            raise ProviderUnavailableError(
                message=(
                    f"Vector dimension mismatch: query vector has {len(vector)} "
                    f"dimensions but index is configured for "
                    f"{self.config.dimensions} dimensions."
                ),
                component="vectorize",
            )
        url = self.config.index_url + "/query"
        payload: Dict[str, Any] = {
            "vector": vector,
            "topK": top_k,
            "returnValues": True,
            "returnMetadata": "all",
        }
        if filter:
            payload["filter"] = filter
        started = time.perf_counter()
        try:
            async with self._aclient(60.0) as client:
                resp = await client.post(
                    url, headers=self._headers(), json=payload
                )
            self._raise_for_status(resp)
            return resp.json()
        except httpx.HTTPError as exc:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
            logger.error(
                "vectorize.aquery_failed error=%s duration_ms=%s",
                type(exc).__name__,
                duration_ms,
            )
            raise ProviderUnavailableError(
                message=f"Vectorize query failed: {exc}",
                component="vectorize",
            ) from exc
