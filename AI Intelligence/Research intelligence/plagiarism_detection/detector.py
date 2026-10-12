import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from plagiarism_detection.boilerplate_filter import BoilerplateFilter
from plagiarism_detection.exact_match import ExactMatchScorer
from plagiarism_detection.semantic_similarity import SemanticSimilarityScorer
from embeddings.service import EmbeddingService
from db.models import AIChunk, AIDocument

class PlagiarismDetector:
    """Orchestrates plagiarism detection using multiple signals."""
    
    def __init__(
        self,
        exact_match_threshold: float = 0.8,
        semantic_threshold: float = 0.85,
        max_chunks_to_compare: int = 100,
        max_processing_time: int = 60  # seconds
    ):
        self.boilerplate_filter = BoilerplateFilter()
        self.exact_scorer = ExactMatchScorer(similarity_threshold=exact_match_threshold)
        self.embedding_service = EmbeddingService()
        self.semantic_scorer = SemanticSimilarityScorer(
            self.embedding_service, 
            similarity_threshold=semantic_threshold
        )
        self.max_chunks = max_chunks_to_compare
        self.max_time = max_processing_time
    
    async def detect_similarity(
        self,
        db: AsyncSession,
        submitted_text: str,
        user_id: str,
        access_levels: List[str] = ["public"],
        exclude_document_ids: List[str] = None
    ) -> Dict:
        """
        Detect potential plagiarism by comparing submitted text against indexed theses.
        
        Returns:
            {
                "timestamp": str,
                "submitted_text_length": int,
                "chunks_compared": int,
                "exact_matches": List[Dict],
                "semantic_matches": List[Dict],
                "summary": {
                    "exact_match_count": int,
                    "semantic_match_count": int,
                    "highest_exact_score": float,
                    "highest_semantic_score": float,
                    "assessment": str
                },
                "limitations": List[str]
            }
        """
        exclude_document_ids = exclude_document_ids or []
        start_time = datetime.utcnow()
        
        # 1. Filter boilerplate from submitted text
        submitted_chunks = [{"text": submitted_text, "chunk_id": "submitted"}]
        filtered_submitted = self.boilerplate_filter.filter_chunks(submitted_chunks)
        
        if not filtered_submitted:
            return {
                "timestamp": start_time.isoformat(),
                "submitted_text_length": len(submitted_text),
                "chunks_compared": 0,
                "exact_matches": [],
                "semantic_matches": [],
                "summary": {
                    "exact_match_count": 0,
                    "semantic_match_count": 0,
                    "highest_exact_score": 0.0,
                    "highest_semantic_score": 0.0,
                    "assessment": "No comparable text after filtering boilerplate."
                },
                "limitations": ["Submitted text was filtered as boilerplate or references."]
            }
        
        # 2. Fetch accessible chunks from database
        query = select(AIChunk).where(AIChunk.is_embedded == True)
        
        # Exclude specific documents
        if exclude_document_ids:
            query = query.where(~AIChunk.document_id.in_(exclude_document_ids))
        
        result = await db.execute(query)
        all_chunks = result.scalars().all()
        
        # 3. Filter by access permissions
        accessible_chunks = []
        for chunk in all_chunks:
            # Check if document is accessible
            doc_result = await db.execute(
                select(AIDocument).where(AIDocument.id == chunk.document_id)
            )
            doc = doc_result.scalar_one_or_none()
            
            if doc and doc.access_level in access_levels:
                accessible_chunks.append({
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "metadata": {
                        "title": doc.backend_thesis_id,  # Use backend ID as title proxy
                        "section": chunk.section,
                        "page_number": chunk.chunk_index,  # Approximate
                        "access_level": doc.access_level
                    }
                })
        
        # 4. Filter boilerplate from candidates
        filtered_candidates = self.boilerplate_filter.filter_chunks(accessible_chunks)
        
        # 5. Limit chunks to compare
        candidates_to_compare = filtered_candidates[:self.max_chunks]
        
        # 6. Find exact matches
        exact_matches = self.exact_scorer.find_matching_passages(
            submitted_text, 
            candidates_to_compare,
            top_k=10
        )
        
        # 7. Find semantic matches
        semantic_matches = self.semantic_scorer.find_semantic_matches(
            submitted_text,
            candidates_to_compare,
            top_k=10
        )
        
        # 8. Calculate summary
        highest_exact = max([m["scores"]["sequence_ratio"] for m in exact_matches], default=0.0)
        highest_semantic = max([m["scores"]["cosine_similarity"] for m in semantic_matches], default=0.0)
        
        # Assessment
        if highest_exact > 0.95:
            assessment = "High likelihood of exact duplication. Requires human review."
        elif highest_exact > 0.8:
            assessment = "Potential near-duplicate text detected. Requires human review."
        elif highest_semantic > 0.9:
            assessment = "High semantic similarity detected. May indicate paraphrasing. Requires human review."
        elif highest_semantic > 0.85:
            assessment = "Moderate semantic similarity. Could be common phrasing or legitimate citation."
        else:
            assessment = "No significant similarity detected."
        
        return {
            "timestamp": start_time.isoformat(),
            "submitted_text_length": len(submitted_text),
            "chunks_compared": len(candidates_to_compare),
            "exact_matches": exact_matches,
            "semantic_matches": semantic_matches,
            "summary": {
                "exact_match_count": len(exact_matches),
                "semantic_match_count": len(semantic_matches),
                "highest_exact_score": round(highest_exact, 4),
                "highest_semantic_score": round(highest_semantic, 4),
                "assessment": assessment
            },
            "limitations": [
                "Detection is based on available indexed theses only.",
                "Cannot detect cross-language plagiarism.",
                "Semantic similarity may miss subtle paraphrasing.",
                "Common academic phrases may trigger false positives.",
                "This is a screening tool, not a definitive misconduct finding."
            ]
        }
