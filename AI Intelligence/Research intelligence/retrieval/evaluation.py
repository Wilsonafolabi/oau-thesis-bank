import math
from typing import List

def calculate_recall_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """Calculates Recall@K: proportion of relevant documents found in top K."""
    retrieved_k = retrieved_ids[:k]
    relevant_set = set(relevant_ids)
    if not relevant_set:
        return 0.0
    hits = sum(1 for rid in retrieved_k if rid in relevant_set)
    return hits / len(relevant_set)

def calculate_mrr(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """Calculates Mean Reciprocal Rank: 1/rank of the first relevant document."""
    relevant_set = set(relevant_ids)
    for i, rid in enumerate(retrieved_ids):
        if rid in relevant_set:
            return 1.0 / (i + 1)
    return 0.0

def calculate_ndcg_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """
    Calculates Normalized Discounted Cumulative Gain@K.
    Uses binary relevance (1 if relevant, 0 otherwise) for simplicity.
    """
    retrieved_k = retrieved_ids[:k]
    relevant_set = set(relevant_ids)
    
    # Calculate DCG
    dcg = 0.0
    for i, rid in enumerate(retrieved_k):
        if rid in relevant_set:
            dcg += 1.0 / math.log2(i + 2)
            
    # Calculate Ideal DCG (all relevant items at the top)
    ideal_relevant_count = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_relevant_count))
    
    return dcg / idcg if idcg > 0 else 0.0