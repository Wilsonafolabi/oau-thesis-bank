import os
import logging
from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Production embedding service using BAAI/bge-large-en-v1.5"""
    
    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5")
        self.model_version = os.getenv("EMBEDDING_MODEL_VERSION", "stock-v1")
        self.expected_dim = int(os.getenv("EMBEDDING_DIM", "1024"))
        self.device = device or os.getenv("EMBEDDING_INFERENCE_DEVICE", "cpu")
        
        logger.info(f"Loading embedding model: {self.model_name} on {self.device}")
        self.model = SentenceTransformer(self.model_name, device=self.device)
        
        # Verify dimensions on load
        test_embedding = self.model.encode(["test"], normalize_embeddings=True)
        actual_dim = len(test_embedding[0])
        if actual_dim != self.expected_dim:
            raise ValueError(
                f"Model dimension mismatch: expected {self.expected_dim}, got {actual_dim}. "
                f"Update EMBEDDING_DIM in .env or use correct model."
            )
        logger.info(f"Embedding model loaded successfully. Dimensions: {actual_dim}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RuntimeError, ConnectionError, TimeoutError))
    )
    def embed_texts(self, texts: List[str], batch_size: int = 32, normalize: bool = True) -> List[List[float]]:
        """
        Generate embeddings for a list of texts with batching and error handling.
        
        Args:
            texts: List of text strings to embed
            batch_size: Number of texts to process in each batch
            normalize: Whether to L2-normalize embeddings (recommended for cosine similarity)
        
        Returns:
            List of embedding vectors (each is a list of floats)
        
        Raises:
            ValueError: If any embedding has wrong dimensions
            RuntimeError: If embedding generation fails after retries
        """
        if not texts:
            return []
        
        logger.info(f"Embedding {len(texts)} texts in batches of {batch_size}")
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.debug(f"Processing batch {i//batch_size + 1}: {len(batch)} texts")
            
            try:
                embeddings = self.model.encode(
                    batch,
                    batch_size=batch_size,
                    normalize_embeddings=normalize,
                    show_progress_bar=False
                )
                
                # Verify dimensions for each embedding
                for idx, emb in enumerate(embeddings):
                    if len(emb) != self.expected_dim:
                        raise ValueError(
                            f"Embedding dimension mismatch at batch {i//batch_size + 1}, "
                            f"text {idx}: expected {self.expected_dim}, got {len(emb)}"
                        )
                
                # Convert to list of lists for JSON serialization
                all_embeddings.extend([emb.tolist() for emb in embeddings])
                
            except Exception as e:
                logger.error(f"Failed to embed batch {i//batch_size + 1}: {e}")
                raise
        
        logger.info(f"Successfully embedded {len(all_embeddings)} texts")
        return all_embeddings
    
    def get_model_info(self) -> dict:
        """Return metadata about the loaded embedding model"""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "dimensions": self.expected_dim,
            "device": self.device,
            "normalization": True
        }