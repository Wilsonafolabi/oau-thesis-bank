"""Embedding generation service.

Supports sentence-transformers (BAAI/bge-large-en-v1.5 by default) for
generating embeddings. Raises ConfigurationError if the required package is
not installed — no silent fallback to a non-real embedding model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from ..config import get_settings
from ..errors import ConfigurationError
from ..local_model_runtime import MODEL_RUNTIME_LOCK, clear_cuda_cache

_MODEL_CACHE = {}


@dataclass
class EmbeddingResult:
    """Result of embedding a single text."""

    vector: List[float]
    model_name: str
    model_version: str


class EmbeddingService:
    """Generate embeddings for text using the configured embedding model."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> None:
        self.model_name = model_name or os.environ.get(
            "EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5"
        )
        self.model_version = model_version or os.environ.get(
            "EMBEDDING_MODEL_VERSION", "stock-v1"
        )
        self.batch_size = max(1, int(os.environ.get("EMBEDDING_BATCH_SIZE", "8")))
        self._model = None
        self._model_loaded = False

    def _load_model(self) -> None:
        """Load the sentence-transformers model if not already loaded."""
        if self._model_loaded:
            return
        with MODEL_RUNTIME_LOCK:
            if self._model_loaded:
                return
            self._model = _MODEL_CACHE.get(self.model_name)
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self.model_name)
                except ImportError as exc:
                    raise ConfigurationError(
                        code="embedding_model_not_available",
                        message=(
                            f"sentence-transformers is not installed. Install it to use "
                            f"embedding model {self.model_name}."
                        ),
                        component="embedding_service",
                        retryable=True,
                    ) from exc
                _MODEL_CACHE[self.model_name] = self._model
            self._model_loaded = True

    def _encode(self, texts: List[str]):
        self._load_model()
        assert self._model is not None
        try:
            return self._model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=self.batch_size,
            )
        except RuntimeError as exc:
            message = str(exc).lower()
            if "cuda" not in message or "out of memory" not in message:
                raise

            self._model.to("cpu")
            clear_cuda_cache()
            return self._model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=self.batch_size,
            )

    def embed_text(self, text: str) -> EmbeddingResult:
        """Generate an embedding for a single text string."""
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings sequentially in small batches."""
        with MODEL_RUNTIME_LOCK:
            vectors = self._encode(texts)
        return [
            EmbeddingResult(
                vector=v.tolist(),
                model_name=self.model_name,
                model_version=self.model_version,
            )
            for v in vectors
        ]

    def release_device_memory(self) -> None:
        """Move the model off GPU and release cached CUDA allocations."""
        with MODEL_RUNTIME_LOCK:
            model = self._model
            if model is not None:
                try:
                    model.to("cpu")
                except Exception:
                    pass
                if _MODEL_CACHE.get(self.model_name) is model:
                    _MODEL_CACHE.pop(self.model_name, None)
                self._model = None
                self._model_loaded = False

            clear_cuda_cache()
