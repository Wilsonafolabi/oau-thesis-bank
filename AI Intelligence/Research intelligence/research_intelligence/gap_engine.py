import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class GapEngine:
    """
    Unsupervised research-gap detection mechanism operating on the institution's corpus.
    Uses BERTopic to identify themes and surface under-researched topics (Section 7.7).
    """
    def __init__(self):
        self.model = None
        self.is_initialized = False

    def initialize_model(self):
        """Initializes BERTopic. Packaged as an optional extra per Section 7.10."""
        try:
            from bertopic import BERTopic
            from sentence_transformers import SentenceTransformer
            
            # Use a lightweight embedding model for speed, or BGE-large for production
            embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            self.model = BERTopic(
                embedding_model=embedding_model,
                language="english",
                min_topic_size=3, # Lower threshold to catch niche gaps
                calculate_probabilities=True
            )
            self.is_initialized = True
            logger.info("BERTopic gap detection engine initialized successfully.")
        except ImportError:
            logger.error("BERTopic not installed. Install via: pip install bertopic sentence-transformers")
            self.is_initialized = False

    def detect_gaps(self, thesis_texts: List[str], thesis_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Surfaces under-researched topics from the corpus.
        A 'gap' is defined as a valid topic cluster with very few associated documents.
        """
        if not self.is_initialized:
            self.initialize_model()
            
        if not self.model or not thesis_texts:
            logger.warning("Gap engine not initialized or no texts provided.")
            return []

        logger.info(f"Running BERTopic gap detection on {len(thesis_texts)} thesis abstracts/chunks...")
        
        # Fit the model to the corpus
        topics, probs = self.model.fit_transform(thesis_texts)
        topic_info = self.model.get_topic_info()
        
        gaps = []
        for _, row in topic_info.iterrows():
            topic_id = row['Topic']
            count = row['Count']
            
            # Topic -1 is outliers/noise. We want real topics with LOW counts (under-researched)
            if topic_id != -1 and count <= 3: 
                topic_words = self.model.get_topic(topic_id)
                gaps.append({
                    "topic_id": topic_id,
                    "topic_name": row['Name'],
                    "document_count": count,
                    "representative_keywords": [word[0] for word in topic_words[:5]],
                    "thesis_ids": [thesis_ids[i] for i, t in enumerate(topics) if t == topic_id]
                })
                
        # Sort by document count ascending (biggest gaps first)
        gaps.sort(key=lambda x: x['document_count'])
        logger.info(f"Detected {len(gaps)} potential research gaps.")
        return gaps