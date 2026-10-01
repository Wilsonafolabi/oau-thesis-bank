import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

class BaselineRecommender:
    """Computes popularity/recency baseline (Section 7.8)."""
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