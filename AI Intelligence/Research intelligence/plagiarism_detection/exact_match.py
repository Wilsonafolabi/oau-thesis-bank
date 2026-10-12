import re
from typing import List, Dict, Set, Tuple
from difflib import SequenceMatcher
from collections import Counter

class ExactMatchScorer:
    """Detects exact and near-duplicate text using character and token-level similarity."""
    
    def __init__(self, ngram_size: int = 5, similarity_threshold: float = 0.8):
        self.ngram_size = ngram_size
        self.similarity_threshold = similarity_threshold
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase
        text = text.lower()
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove punctuation for token comparison
        text = re.sub(r'[^\w\s]', ' ', text)
        return text.strip()
    
    def _get_ngrams(self, text: str, n: int) -> List[str]:
        """Extract character n-grams from text."""
        text = self._normalize_text(text)
        if len(text) < n:
            return [text] if text else []
        return [text[i:i+n] for i in range(len(text) - n + 1)]
    
    def _get_token_ngrams(self, text: str, n: int = 3) -> List[str]:
        """Extract token n-grams from text."""
        tokens = self._normalize_text(text).split()
        if len(tokens) < n:
            return [' '.join(tokens)] if tokens else []
        return [' '.join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]
    
    def jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        """Calculate Jaccard similarity between two sets."""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0
    
    def sequence_similarity(self, text1: str, text2: str) -> float:
        """Calculate sequence matching ratio."""
        text1 = self._normalize_text(text1)
        text2 = self._normalize_text(text2)
        return SequenceMatcher(None, text1, text2).ratio()
    
    def calculate_exact_match_score(self, text1: str, text2: str) -> Dict[str, float]:
        """
        Calculate multiple exact match scores.
        
        Returns:
            {
                "char_ngram_jaccard": float,  # Character-level n-gram overlap
                "token_ngram_jaccard": float,  # Token-level n-gram overlap
                "sequence_ratio": float,  # Overall sequence similarity
                "is_exact_match": bool  # Whether it exceeds threshold
            }
        """
        # Character n-gram similarity
        ngrams1 = set(self._get_ngrams(text1, self.ngram_size))
        ngrams2 = set(self._get_ngrams(text2, self.ngram_size))
        char_jaccard = self.jaccard_similarity(ngrams1, ngrams2)
        
        # Token n-gram similarity
        token_ngrams1 = set(self._get_token_ngrams(text1, 3))
        token_ngrams2 = set(self._get_token_ngrams(text2, 3))
        token_jaccard = self.jaccard_similarity(token_ngrams1, token_ngrams2)
        
        # Sequence similarity
        seq_ratio = self.sequence_similarity(text1, text2)
        
        # Determine if it's an exact match
        max_score = max(char_jaccard, token_jaccard, seq_ratio)
        is_exact = max_score >= self.similarity_threshold
        
        return {
            "char_ngram_jaccard": round(char_jaccard, 4),
            "token_ngram_jaccard": round(token_jaccard, 4),
            "sequence_ratio": round(seq_ratio, 4),
            "is_exact_match": is_exact
        }
    
    def find_matching_passages(self, query_text: str, candidate_chunks: List[dict], top_k: int = 5) -> List[Dict]:
        """Find the most similar passages from candidates."""
        matches = []
        
        for chunk in candidate_chunks:
            candidate_text = chunk.get("text", "")
            scores = self.calculate_exact_match_score(query_text, candidate_text)
            
            if scores["is_exact_match"]:
                matches.append({
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "text": candidate_text,
                    "match_type": "exact_duplicate" if scores["sequence_ratio"] > 0.95 else "near_duplicate",
                    "scores": scores,
                    "metadata": chunk.get("metadata", {})
                })
        
        # Sort by sequence ratio (highest first)
        matches.sort(key=lambda x: x["scores"]["sequence_ratio"], reverse=True)
        return matches[:top_k]

