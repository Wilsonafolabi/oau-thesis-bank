import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class GapEngine:
    def __init__(self):
        self.model = None
        self.is_initialized = False

    def initialize_model(self):
        try:
            from bertopic import BERTopic
            from sentence_transformers import SentenceTransformer
            
            embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            self.model = BERTopic(
                embedding_model=embedding_model,
                language="english",
                min_topic_size=2,
                calculate_probabilities=True
            )
            self.is_initialized = True
            logger.info("BERTopic gap detection engine initialized successfully.")
        except ImportError:
            logger.warning("BERTopic not installed. Falling back to mock gap detection.")
            self.is_initialized = False

    def detect_gaps(self, thesis_texts: List[str], thesis_ids: List[str] = None) -> List[Dict[str, Any]]:
        if not self.is_initialized:
            self.initialize_model()
            
        if not thesis_texts:
            return []

        # Need at least 5 documents for BERTopic to work properly
        if len(thesis_texts) < 5:
            logger.warning(f"Only {len(thesis_texts)} documents provided. BERTopic requires at least 5 for reliable gap detection.")
            return [{
                "topic_id": 0,
                "topic_name": "Insufficient Data for Gap Detection",
                "document_count": len(thesis_texts),
                "representative_keywords": ["need", "more", "data", "theses"],
                "thesis_ids": thesis_ids or [],
                "note": f"Upload at least {5 - len(thesis_texts)} more theses to enable AI-powered gap detection."
            }]

        if not self.model:
            return [{
                "topic_id": 1,
                "topic_name": "Mock Research Gap (BERTopic not installed)",
                "document_count": 1,
                "representative_keywords": ["mock", "gap", "bertopic"],
                "thesis_ids": thesis_ids[:1] if thesis_ids else []
            }]

        try:
            logger.info(f"Running BERTopic gap detection on {len(thesis_texts)} thesis abstracts/chunks...")
            topics, probs = self.model.fit_transform(thesis_texts)
            topic_info = self.model.get_topic_info()
            
            gaps = []
            for _, row in topic_info.iterrows():
                topic_id = row['Topic']
                count = row['Count']
                
                if topic_id != -1 and count <= 3: 
                    topic_words = self.model.get_topic(topic_id)
                    gaps.append({
                        "topic_id": int(topic_id),
                        "topic_name": str(row['Name']),
                        "document_count": int(count),
                        "representative_keywords": [str(word[0]) for word in topic_words[:5]],
                        "thesis_ids": [thesis_ids[i] for i, t in enumerate(topics) if t == topic_id] if thesis_ids else []
                    })
                    
            gaps.sort(key=lambda x: x['document_count'])
            logger.info(f"Detected {len(gaps)} potential research gaps.")
            return gaps
            
        except Exception as e:
            logger.error(f"BERTopic failed: {e}. Falling back to mock data.")
            return [{
                "topic_id": 999,
                "topic_name": "Gap Detection Error",
                "document_count": 0,
                "representative_keywords": ["error", "retry"],
                "thesis_ids": [],
                "note": f"BERTopic processing failed: {str(e)[:100]}..."
            }]