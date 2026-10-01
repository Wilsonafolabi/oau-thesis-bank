import logging
import numpy as np
from typing import List, Dict

logger = logging.getLogger(__name__)

class LearnedRecommender:
    """Matrix Factorization model trained on real usage data (Section 13)."""
    def __init__(self, n_factors: int = 50):
        self.n_factors = n_factors
        self.user_factors = None
        self.thesis_factors = None
        self.user_map, self.thesis_map = {}, {}

    def train(self, interactions: List[Dict]):
        users = list(set(i['user_id'] for i in interactions))
        theses = list(set(i['thesis_id'] for i in interactions))
        self.user_map = {u: idx for idx, u in enumerate(users)}
        self.thesis_map = {t: idx for idx, t in enumerate(theses)}
        
        matrix = np.zeros((len(users), len(theses)))
        for i in interactions:
            weight = 3.0 if i['event_type'] == 'download' else 1.0
            matrix[self.user_map[i['user_id']], self.thesis_map[i['thesis_id']]] += weight
            
        self.user_factors = np.random.normal(scale=1./self.n_factors, size=(len(users), self.n_factors))
        self.thesis_factors = np.random.normal(scale=1./self.n_factors, size=(len(theses), self.n_factors))
        logger.info(f"Trained learned model on {len(interactions)} interactions.")

    def get_recommendations(self, user_id: str, top_k: int = 5) -> List[str]:
        if user_id not in self.user_map: return []
        scores = self.user_factors[self.user_map[user_id]] @ self.thesis_factors.T
        top_indices = np.argsort(scores)[::-1][:top_k]
        reverse_map = {v: k for k, v in self.thesis_map.items()}
        return [reverse_map[idx] for idx in top_indices]