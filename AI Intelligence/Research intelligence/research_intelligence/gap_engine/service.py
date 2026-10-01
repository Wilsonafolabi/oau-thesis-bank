import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class GapEngine:
    def __init__(self):
        self.model = None

    def detect_gaps(self, thesis_texts: List[str]) -> List[Dict]:
        logger.info(f"Running BERTopic gap detection on {len(thesis_texts)} texts...")
        return []