"""Tests for Vectorize upsert/query behavior."""

import pytest

from oau_ai.embeddings.vectorize import VectorizeService


class MockTransport:
    """Mock httpx transport for Vectorize testing."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls = []

    def __call__(self, request):
        import httpx
        self.calls.append(request)
        url = str(request.url)
        for pattern, response in self.responses.items():
            if pattern in url:
                return httpx.Response(
                    response.get("status", 200),
                    json=response.get("json", {}),
                    request=request,
                )
        return httpx.Response(404, request=request)


def test_vectorize_service_not_configured_without_credentials():
    """VectorizeService reports not configured when no credentials."""
    from oau_ai.config import VectorizeConfig

    config = VectorizeConfig(
        api_token=None,
        account_id=None,
        index_name="test",
        dimensions=1024,
    )
    service = VectorizeService(config=config)

    assert service.is_configured() is False


def test_vectorize_upsert_requires_configuration():
    """Upsert raises ConfigurationError when Vectorize not configured."""
    from oau_ai.config import VectorizeConfig
    from oau_ai.errors import ConfigurationError

    config = VectorizeConfig(
        api_token=None,
        account_id=None,
        index_name="test",
        dimensions=1024,
    )
    service = VectorizeService(config=config)

    with pytest.raises(ConfigurationError):
        service.upsert([{"id": "p1", "values": [0.1, 0.2], "metadata": {}}])


def test_vectorize_query_requires_configuration():
    """Query raises ConfigurationError when Vectorize not configured."""
    from oau_ai.config import VectorizeConfig
    from oau_ai.errors import ConfigurationError

    config = VectorizeConfig(
        api_token=None,
        account_id=None,
        index_name="test",
        dimensions=1024,
    )
    service = VectorizeService(config=config)

    with pytest.raises(ConfigurationError):
        service.query(vector=[0.1, 0.2], top_k=5)


def test_vectorize_index_url_format():
    """Vectorize index URL is correctly formatted."""
    from oau_ai.config import VectorizeConfig

    config = VectorizeConfig(
        api_token="token",
        account_id="acct-123",
        index_name="my-index",
        dimensions=1024,
    )
    service = VectorizeService(config=config)
    expected = "https://api.cloudflare.com/client/v4/accounts/acct-123/vectorize/v2/indexes/my-index"
    assert service.config.index_url == expected

