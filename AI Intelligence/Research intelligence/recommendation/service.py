import logging
from datetime import datetime
from typing import List, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)

class InteractionLogger:
    def __init__(self):
        self.interactions: List[Dict[str, Any]] = []

    def log_event(self, user_id: str, thesis_id: str, event_type: str):
        record = {
            "user_id": user_id, "thesis_id": thesis_id, 
            "event_type": event_type, "timestamp": datetime.utcnow()
        }
        self.interactions.append(record)
        logger.info(f"Logged interaction: {user_id} -> {thesis_id} ({event_type})")

class BaselineRecommender:
    def __init__(self, interactions: List[Dict], theses: List[Dict]):
        self.interactions = interactions
        self.theses = {t['id']: t for t in theses}

    def get_scores(self, top_k: int = 10) -> List[Dict]:
        scores = []
        for thesis_id, thesis in self.theses.items():
            views = sum(1 for i in self.interactions if i['thesis_id'] == thesis_id and i['event_type'] == 'view')
            downloads = sum(1 for i in self.interactions if i['thesis_id'] == thesis_id and i['event_type'] == 'download')
            days_old = (datetime.utcnow() - thesis.get('created_at', datetime.utcnow())).days
            recency = 1.0 / (1.0 + 0.1 * days_old)
            final_score = ((views * 1.0) + (downloads * 3.0)) * 0.7 + (recency * 10) * 0.3
            scores.append({"thesis_id": thesis_id, "score": final_score})
        scores.sort(key=lambda x: x['score'], reverse=True)
        return scores[:top_k]

class LearnedRecommender:
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

class RecommendationService:
    def __init__(self, theses: List[Dict]):
        # THIS IS THE FIX: Initialize the logger tool here
        self.logger_tool = InteractionLogger()
        self.baseline = BaselineRecommender(self.logger_tool.interactions, theses)
        self.learned_model = LearnedRecommender()
        self.use_learned = False

    def train_on_data(self, interactions: List[Dict]):
        if len(interactions) > 10:
            self.learned_model.train(interactions)
            self.use_learned = True
            # Update baseline with new interactions too
            self.baseline = BaselineRecommender(interactions, list(self.baseline.theses.values()))

    def get_recommendations(self, user_id: str, top_k: int = 5):
        if self.use_learned:
            return self.learned_model.get_recommendations(user_id, top_k)
        return self.baseline.get_scores(top_k)