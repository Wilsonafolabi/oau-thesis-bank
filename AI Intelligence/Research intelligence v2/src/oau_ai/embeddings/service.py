"""Embedding generation service.

Supports sentence-transformers (BAAI/bge-large-en-v1.5 by default) for
generating embeddings. Raises ConfigurationError if the required package is
not installed — no silent fallback to a non-real embedding model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..config import get_settings
from ..errors import ConfigurationError


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
        import os

        self.model_name = model_name or os.environ.get(
            "EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5"
        )
        self.model_version = model_version or os.environ.get(
            "EMBEDDING_MODEL_VERSION", "stock-v1"
        )
        self._model = None
        self._model_loaded = False

    def _load_model(self) -> None:
        """Load the sentence-transformers model if not already loaded."""
        if self._model_loaded:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self._model_loaded = True
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

    def embed_text(self, text: str) -> EmbeddingResult:
        """Generate an embedding for a single text string."""
        self._load_model()
        assert self._model is not None
        vector = self._model.encode([text], normalize_embeddings=True)[0]
        return EmbeddingResult(
            vector=vector.tolist(),
            model_name=self.model_name,
            model_version=self.model_version,
        )

    def embed_texts(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for multiple text strings."""
        self._load_model()
        assert self._model is not None
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [
            EmbeddingResult(
                vector=v.tolist(),
                model_name=self.model_name,
                model_version=self.model_version,
            )
            for v in vectors
        ]
