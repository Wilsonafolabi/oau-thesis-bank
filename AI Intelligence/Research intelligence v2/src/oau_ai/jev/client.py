
"""
JEV System One asynchronous client.

Responsibilities:
- Load JEV credentials and configuration from environment variables.
- Submit structured decision requests to System One.
- Handle HTTP errors, timeouts and invalid responses.
- Preserve provider error details for debugging.
- Manage HTTP connection lifecycle.

Expected success:
    {
        "status": "success",
        "data": {...}
    }
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("oau_ai.jev.client")


class JEVClient:
    """Asynchronous client for JEV System One."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 20.0,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("JEV_API_KEY")

        self.base_url = (
            base_url
            or os.getenv(
                "JEV_BASE_URL",
                "https://api.typesafe.ai/v1",
            )
        ).rstrip("/")

        self.model = model or os.getenv("JEV_MODEL")

        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_available(self) -> bool:
        """Return whether all required configuration is present."""
        return bool(self.api_key and self.model and self.base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        """Create or reuse the asynchronous HTTP client."""

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
            )

        return self._client

    async def classify(
        self,
        state: Dict[str, Any],
        questions: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Submit a decision request to JEV System One.

        Returns a structured result without exposing API credentials.
        """

        if not self.api_key:
            return {
                "status": "unavailable",
                "reason": "missing_api_key",
            }

        if not self.model:
            return {
                "status": "unavailable",
                "reason": "missing_model",
            }

        if not isinstance(state, dict):
            return {
                "status": "error",
                "reason": "invalid_state",
            }

        if not isinstance(questions, dict) or not questions:
            return {
                "status": "error",
                "reason": "invalid_questions",
            }

        endpoint = f"{self.base_url}/systemone"

        payload = {
            "model": self.model,
            "state": state,
            "questions": questions,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            client = await self._get_client()

            response = await client.post(
                endpoint,
                json=payload,
                headers=headers,
            )

            response.raise_for_status()

            try:
                result = response.json()
            except ValueError:
                logger.error("JEV returned a non-JSON response")

                return {
                    "status": "error",
                    "reason": "invalid_json",
                    "details": response.text[:4000],
                }

            if not isinstance(result, dict):
                logger.error("JEV returned an unexpected response type")

                return {
                    "status": "error",
                    "reason": "invalid_output",
                }

            return {
                "status": "success",
                "data": result,
            }

        except httpx.TimeoutException:
            logger.warning(
                "JEV request timed out after %s seconds",
                self.timeout,
            )

            return {
                "status": "error",
                "reason": "timeout",
            }

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            details = exc.response.text[:4000]

            logger.error(
                "JEV HTTP error %s: %s",
                status_code,
                details,
            )

            return {
                "status": "error",
                "reason": "http_error",
                "status_code": status_code,
                "details": details,
            }

        except httpx.RequestError as exc:
            logger.error(
                "JEV connection error: %s",
                type(exc).__name__,
            )

            return {
                "status": "error",
                "reason": "connection_error",
            }

        except Exception:
            logger.exception("Unexpected JEV client failure")

            return {
                "status": "error",
                "reason": "internal_error",
            }

    async def close(self) -> None:
        """Release HTTP resources during application shutdown."""

        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
