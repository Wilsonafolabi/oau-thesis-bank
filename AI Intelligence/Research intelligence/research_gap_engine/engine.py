import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from retrieval.hybrid_search import HybridSearchService
from embeddings.service import EmbeddingService
from research_gap_engine.evidence_extractor import EvidenceExtractor
from research_gap_engine.gap_analysis import GapAnalyzer, ResearchGap
from db.models import AIChunk, AIDocument

class ResearchGapEngine:
    """Main engine for identifying research gaps across theses."""
    
    def __init__(self):
        self.search_service = HybridSearchService()
        self.embedding_service = EmbeddingService()
        self.evidence_extractor = EvidenceExtractor()
        self.gap_analyzer = GapAnalyzer()
        self.min_theses_required = 3
    
    async def analyze_research_gaps(
        self,
        db: AsyncSession,
        query: str,
        user_id: str,
        access_levels: List[str] = ["public"],
        max_theses: int = 10
    ) -> Dict:
        """
        Analyze research gaps for a given query.
        
        Returns:
            {
                "query": str,
                "timestamp": str,
                "corpus_size": int,
                "sufficient_evidence": bool,
                "gaps": List[ResearchGap],
                "limitations": str
            }
        """
        # 1. Generate query embedding
        query_embedding = self.embedding_service.embed_texts([query])[0]
        
        # 2. Search for relevant theses
        search_results = await self.search_service.search(
            db=db,
            query=query,
            query_embedding=query_embedding,
            allowed_access_levels=access_levels,
            limit=100  # Get more chunks to cover multiple theses
        )
        
        if not search_results:
            return {
                "query": query,
                "timestamp": datetime.utcnow().isoformat(),
                "corpus_size": 0,
                "sufficient_evidence": False,
                "gaps": [],
                "limitations": "No relevant theses found in the corpus."
            }
        
        # 3. Group chunks by document_id
        chunks_by_doc = {}
        for result in search_results:
            doc_id = result.document_id
            if doc_id not in chunks_by_doc:
                chunks_by_doc[doc_id] = []
            chunks_by_doc[doc_id].append(result.dict())
        
        # 4. Check if we have enough theses
        if len(chunks_by_doc) < self.min_theses_required:
            return {
                "query": query,
                "timestamp": datetime.utcnow().isoformat(),
                "corpus_size": len(chunks_by_doc),
                "sufficient_evidence": False,
                "gaps": [],
                "limitations": f"Insufficient evidence: only {len(chunks_by_doc)} theses found, minimum {self.min_theses_required} required for reliable gap analysis."
            }
        
        # 5. Fetch full chunk data from database
        all_chunk_ids = [r.chunk_id for r in search_results]
        result = await db.execute(
            select(AIChunk).where(AIChunk.id.in_(all_chunk_ids))
        )
        full_chunks = {chunk.id: chunk.dict() for chunk in result.scalars().all()}
        
        # 6. Extract evidence from each thesis
        evidence_list = []
        for doc_id, chunks in list(chunks_by_doc.items())[:max_theses]:
            # Enrich chunks with full data
            enriched_chunks = [full_chunks.get(c["chunk_id"], c) for c in chunks]
            evidence = self.evidence_extractor.extract_from_chunks(enriched_chunks)
            if evidence:
                evidence_list.append(evidence)
        
        if len(evidence_list) < self.min_theses_required:
            return {
                "query": query,
                "timestamp": datetime.utcnow().isoformat(),
                "corpus_size": len(evidence_list),
                "sufficient_evidence": False,
                "gaps": [],
                "limitations": f"Insufficient extractable evidence: only {len(evidence_list)} theses had relevant sections."
            }
        
        # 7. Analyze gaps
        gaps = self.gap_analyzer.analyze_gaps(evidence_list)
        
        # 8. Return results
        return {
            "query": query,
            "timestamp": datetime.utcnow().isoformat(),
            "corpus_size": len(evidence_list),
            "sufficient_evidence": True,
            "gaps": [self._gap_to_dict(gap) for gap in gaps],
            "limitations": "Gap analysis is based on available theses in the repository and may not reflect the full state of research in this area."
        }
    
    def _gap_to_dict(self, gap: ResearchGap) -> Dict:
        """Convert ResearchGap to dictionary."""
        return {
            "gap_type": gap.gap_type.value,
            "description": gap.description,
            "supporting_evidence": gap.supporting_evidence,
            "explanation": gap.explanation,
            "limitations": gap.limitations,
            "confidence": gap.confidence
        }
