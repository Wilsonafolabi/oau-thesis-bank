import numpy as np
from typing import List, Dict
from embeddings.service import EmbeddingService

class SemanticSimilarityScorer:
    """Detects semantic similarity using embeddings."""
    
    def __init__(self, embedding_service: EmbeddingService, similarity_threshold: float = 0.85):
        self.embedding_service = embedding_service
        self.similarity_threshold = similarity_threshold
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def calculate_semantic_score(self, text1: str, text2: str) -> Dict[str, float]:
        """
        Calculate semantic similarity using embeddings.
        
        Returns:
            {
                "cosine_similarity": float,
                "is_semantically_similar": bool
            }
        """
        # Get embeddings
        embeddings = self.embedding_service.embed_texts([text1, text2])
        emb1, emb2 = embeddings[0], embeddings[1]
        
        # Calculate cosine similarity
        cosine_sim = self.cosine_similarity(emb1, emb2)
        is_similar = cosine_sim >= self.similarity_threshold
        
        return {
            "cosine_similarity": round(cosine_sim, 4),
            "is_semantically_similar": is_similar
        }
    
    def find_semantic_matches(self, query_text: str, candidate_chunks: List[dict], top_k: int = 5) -> List[Dict]:
        """Find semantically similar passages."""
        # Get query embedding
        query_embedding = self.embedding_service.embed_texts([query_text])[0]
        
        matches = []
        for chunk in candidate_chunks:
            candidate_text = chunk.get("text", "")
            
            # Get candidate embedding
            candidate_embedding = self.embedding_service.embed_texts([candidate_text])[0]
            
            # Calculate similarity
            cosine_sim = self.cosine_similarity(query_embedding, candidate_embedding)
            
            if cosine_sim >= self.similarity_threshold:
                matches.append({
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "text": candidate_text,
                    "match_type": "semantic_similarity",
                    "scores": {
                        "cosine_similarity": round(cosine_sim, 4),
                        "is_semantically_similar": True
                    },
                    "metadata": chunk.get("metadata", {})
                })
        
        # Sort by cosine similarity
        matches.sort(key=lambda x: x["scores"]["cosine_similarity"], reverse=True)
        return matches[:top_k]
