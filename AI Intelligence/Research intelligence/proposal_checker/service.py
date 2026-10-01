import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ProposalChecker:
    """
    Semantic similarity/plagiarism review engine operating on the institution's corpus.
    Checks new proposals against existing thesis chunks for high semantic similarity.
    """
    def __init__(self, embedding_service):
        """
        embedding_service: An object with an `embed_text(text: str) -> np.ndarray` method.
        """
        self.embedding_service = embedding_service

    def check_similarity(self, new_proposal_text: str, existing_thesis_chunks: List[Dict[str, Any]], threshold: float = 0.85) -> List[Dict[str, Any]]:
        """
        Checks a new proposal against existing thesis chunks for high similarity.
        Returns a list of flagged chunks exceeding the threshold.
        """
        if not self.embedding_service or not existing_thesis_chunks:
            logger.warning("Embedding service or corpus chunks missing. Skipping similarity check.")
            return []

        logger.info(f"Checking proposal similarity against {len(existing_thesis_chunks)} corpus chunks...")
        
        # 1. Embed the new proposal
        proposal_vector = self.embedding_service.embed_text(new_proposal_text)
        
        flagged_chunks = []
        for chunk in existing_thesis_chunks:
            chunk_vector = chunk.get('vector')
            if chunk_vector is None:
                continue
                
            # 2. Calculate Cosine Similarity
            dot_product = np.dot(proposal_vector, chunk_vector)
            norm_proposal = np.linalg.norm(proposal_vector)
            norm_chunk = np.linalg.norm(chunk_vector)
            
            if norm_proposal == 0 or norm_chunk == 0:
                continue
                
            similarity = dot_product / (norm_proposal * norm_chunk)
            
            # 3. Flag if above threshold
            if similarity >= threshold:
                flagged_chunks.append({
                    "thesis_id": chunk.get('thesis_id', 'unknown'),
                    "chunk_id": chunk.get('id', 'unknown'),
                    "similarity_score": float(similarity),
                    "text_preview": chunk.get('text', '')[:150] + "...",
                    "page": chunk.get('page', 'unknown')
                })
                
        # Sort by highest similarity first
        flagged_chunks.sort(key=lambda x: x['similarity_score'], reverse=True)
        logger.info(f"Proposal check flagged {len(flagged_chunks)} chunks above threshold {threshold}.")
        return flagged_chunks