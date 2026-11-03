"""Tests for ConfigurationError consolidation across embedding and RAG services.

Verifies that:
- There is one canonical ConfigurationError (from oau_ai.errors), not a local duplicate.
- EmbeddingService raises the canonical ConfigurationError when sentence-transformers is missing.
- RAGService propagates the canonical ConfigurationError from the embedding service
  instead of swallowing it with a zero-vector fallback.
- Cloudflare Vectorize is never called after an embedding failure.
- The API returns a structured service-unavailable response for embedding failures.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from oau_ai.auth.middleware import ActorContext
from oau_ai.errors import ConfigurationError
from oau_ai.embeddings.service import EmbeddingService
from oau_ai.rag.service import RAGService


class TestConfigurationErrorIsCanonical:
    """ConfigurationError must come from oau_ai.errors everywhere."""

    def test_embeddings_service_imports_canonical_configuration_error(self):
        """EmbeddingService uses the same ConfigurationError class as oau_ai.errors."""
        from oau_ai.errors import ConfigurationError as CanonicalCE

        # Import the name from embeddings.service to confirm it resolves
        # to the canonical class (no local duplicate remains).
        import oau_ai.embeddings.service as embeddings_mod

        assert embeddings_mod.ConfigurationError is CanonicalCE

    def test_rag_service_imports_canonical_configuration_error(self):
        """RAGService does not define a local ConfigurationError; uses oau_ai.errors."""
        import oau_ai.rag.service as rag_mod

        # ConfigurationError must not be defined locally in rag.service.
        # It is imported from oau_ai.errors only when needed (currently unused
        # after removing the zero-vector fallback).
        assert not hasattr(rag_mod, "ConfigurationError")

    def test_configuration_error_has_canonical_phase3_attributes(self):
        """ConfigurationError inherits retryable, trace_id, and to_dict from Phase3Error."""
        exc = ConfigurationError(
            code="embedding_model_not_available",
            message="sentence-transformers is not installed.",
            component="embedding_service",
            retryable=False,
            trace_id="trace-abc-123",
        )
        assert exc.code == "embedding_model_not_available"
        assert exc.message == "sentence-transformers is not installed."
        assert exc.component == "embedding_service"
        assert exc.retryable is False
        assert exc.trace_id == "trace-abc-123"
        d = exc.to_dict()
        assert d == {
            "code": "embedding_model_not_available",
            "message": "sentence-transformers is not installed.",
            "component": "embedding_service",
            "retryable": False,
            "trace_id": "trace-abc-123",
        }


class TestEmbeddingServiceRaisesCanonicalConfigurationError:
    """EmbeddingService._load_model must raise canonical ConfigurationError."""

    def test_load_model_raises_canonical_configuration_error(self):
        """When sentence_transformers import fails, ConfigurationError is raised."""
        service = EmbeddingService()

        with patch(
            "builtins.__import__",
            side_effect=ImportError("No module named 'sentence_transformers'"),
        ):
            with pytest.raises(ConfigurationError) as exc_info:
                service._load_model()

        exc = exc_info.value
        assert exc.code == "embedding_model_not_available"
        assert exc.component == "embedding_service"
        assert "sentence-transformers is not installed" in exc.message
        assert isinstance(exc, ConfigurationError)


class TestRAGCatchesEmbeddingConfigurationError:
    """RAGService must propagate canonical ConfigurationError from embedding service.

    The embedding service raises ConfigurationError when sentence-transformers
    is missing. RAGService must NOT swallow this error with a zero-vector
    fallback; it must propagate so the API returns a structured error response.
    Cloudflare Vectorize must never be called with a fabricated zero vector.
    """

    @pytest.mark.asyncio
    async def test_embed_question_propagates_configuration_error(self):
        """RAGService._embed_question lets ConfigurationError propagate."""
        actor = ActorContext(
            user_id="user-1", roles=["student"], department="CS"
        )
        rag_service = RAGService(db_session=None)

        def failing_embed_text(text: str):
            raise ConfigurationError(
                code="embedding_model_not_available",
                message="sentence-transformers is not installed.",
                component="embedding_service",
                retryable=True,
                trace_id="trace-embed-1",
            )

        with patch.object(
            rag_service.embedding_service, "embed_text", failing_embed_text
        ):
            with pytest.raises(ConfigurationError) as exc_info:
                await rag_service._embed_question("What is machine learning?")

        exc = exc_info.value
        assert exc.code == "embedding_model_not_available"
        assert exc.component == "embedding_service"
        assert exc.retryable is True
        assert exc.trace_id == "trace-embed-1"

    @pytest.mark.asyncio
    async def test_propagated_exception_has_canonical_attributes(self):
        """The propagated ConfigurationError retains code, component, retryable, trace_id."""
        actor = ActorContext(
            user_id="user-1", roles=["student"], department="CS"
        )
        rag_service = RAGService(db_session=None)

        captured: list[ConfigurationError] = []

        def failing_embed_text(text: str):
            exc = ConfigurationError(
                code="embedding_model_not_available",
                message="sentence-transformers is not installed.",
                component="embedding_service",
                retryable=True,
                trace_id="trace-embed-2",
            )
            captured.append(exc)
            raise exc

        with patch.object(
            rag_service.embedding_service, "embed_text", failing_embed_text
        ):
            with pytest.raises(ConfigurationError):
                await rag_service._embed_question("What is machine learning?")

        assert len(captured) == 1
        exc = captured[0]
        assert exc.code == "embedding_model_not_available"
        assert exc.component == "embedding_service"
        assert exc.retryable is True
        assert exc.trace_id == "trace-embed-2"
        d = exc.to_dict()
        assert d["code"] == "embedding_model_not_available"
        assert d["retryable"] is True

    @pytest.mark.asyncio
    async def test_vectorize_never_called_after_embedding_failure(self):
        """Cloudflare Vectorize is never queried when embedding fails."""
        actor = ActorContext(
            user_id="user-1", roles=["student"], department="CS"
        )

        # Track whether VectorizeService.query is called.
        vectorize_called = []

        class TrackingVectorizeService:
            def is_configured(self):
                return True

            def query(self, *args, **kwargs):
                vectorize_called.append(True)
                raise AssertionError(
                    "Vectorize.query must not be called after embedding failure"
                )

        rag_service = RAGService(
            db_session=None,
            vectorize_service=TrackingVectorizeService(),
        )

        def failing_embed_text(text: str):
            raise ConfigurationError(
                code="embedding_model_not_available",
                message="sentence-transformers is not installed.",
                component="embedding_service",
                retryable=True,
                trace_id="trace-embed-3",
            )

        with patch.object(
            rag_service.embedding_service, "embed_text", failing_embed_text
        ):
            with pytest.raises(ConfigurationError):
                await rag_service._embed_question("What is machine learning?")

        assert len(vectorize_called) == 0


class TestRAGApiEmbeddingFailure:
    """API-level tests: ask_rag_question returns structured error on embedding failure."""

    @pytest.mark.asyncio
    async def test_ask_rag_question_embedding_failure_returns_503(self):
        """ask_rag_question returns JSONResponse 503 when embedding fails."""
        from oau_ai.api.routes import ask_rag_question
        from oau_ai.api.schemas import RAGRequest
        from fastapi.responses import JSONResponse

        actor = ActorContext(
            user_id="user-1", roles=["student"], department="CS", trace_id="trace-api-1"
        )

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        service_error = ConfigurationError(
            code="embedding_model_not_available",
            message="sentence-transformers is not installed.",
            component="embedding_service",
            retryable=True,
            trace_id="trace-api-1",
        )

        with patch("oau_ai.api.routes.AsyncSessionLocal", return_value=mock_session_cm):
            with patch("oau_ai.api.routes.RAGService") as mock_service_cls:
                mock_service = AsyncMock()
                mock_service.ask = AsyncMock(side_effect=service_error)
                mock_service_cls.return_value = mock_service

                request = RAGRequest(question="What is machine learning?")
                response = await ask_rag_question(
                    request=request,
                    _token="test-token",
                    actor=actor,
                    trace_id="trace-api-1",
                )

        assert isinstance(response, JSONResponse)
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_ask_rag_question_embedding_failure_preserves_trace_id(self):
        """Error response includes the trace_id from the ConfigurationError."""
        from oau_ai.api.routes import ask_rag_question
        from oau_ai.api.schemas import RAGRequest
        from fastapi.responses import JSONResponse
        import json

        actor = ActorContext(
            user_id="user-1", roles=["student"], department="CS", trace_id="trace-api-2"
        )

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        service_error = ConfigurationError(
            code="embedding_model_not_available",
            message="sentence-transformers is not installed.",
            component="embedding_service",
            retryable=True,
            trace_id="trace-api-2",
        )

        with patch("oau_ai.api.routes.AsyncSessionLocal", return_value=mock_session_cm):
            with patch("oau_ai.api.routes.RAGService") as mock_service_cls:
                mock_service = AsyncMock()
                mock_service.ask = AsyncMock(side_effect=service_error)
                mock_service_cls.return_value = mock_service

                request = RAGRequest(question="What is machine learning?")
                response = await ask_rag_question(
                    request=request,
                    _token="test-token",
                    actor=actor,
                    trace_id="trace-api-2",
                )

        assert isinstance(response, JSONResponse)
        assert response.status_code == 503
        body = json.loads(response.body)
        assert body["code"] == "embedding_model_not_available"
        assert body["component"] == "embedding_service"
        assert body["retryable"] is True
        assert body["trace_id"] == "trace-api-2"
