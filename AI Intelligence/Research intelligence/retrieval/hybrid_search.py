import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sentence_transformers import CrossEncoder
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    section: str
    page_number: int
    chunk_index: int
    score: float
    excerpt: str
    metadata: Dict[str, Any]

class HybridSearchService:
    def __init__(self, reranker_model_name: str = "BAAI/bge-reranker-base"):
        self.reranker_model_name = reranker_model_name
        self.reranker = None
        self._load_reranker()
        
        # Configurable limits from environment
        self.candidate_limit = int(os.getenv("HYBRID_TOP_K_CANDIDATES", "50"))
        self.final_limit = int(os.getenv("HYBRID_TOP_K_FINAL", "20"))
        self.rrf_k = 60 # Standard RRF constant
        self.timeout_seconds = float(os.getenv("SEARCH_TIMEOUT_SECONDS", "10.0"))

    def _load_reranker(self):
        try:
            logger.info(f"Loading reranker model: {self.reranker_model_name}")
            self.reranker = CrossEncoder(self.reranker_model_name)
            logger.info("Reranker loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load reranker: {e}. Reranking will be disabled.")
            self.reranker = None

    def validate_query(self, query: str) -> str:
        if not query or not isinstance(query, str):
            raise ValueError("Query must be a non-empty string")
        cleaned = query.strip()
        if len(cleaned) < 2:
            raise ValueError("Query too short (min 2 chars)")
        
        # CRITICAL: Preserve Yoruba diacritics. Only normalize whitespace.
        # Do NOT use NFKC/NFD here as it can decompose and lose diacritic rendering.
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned

    async def lexical_search(self, db: AsyncSession, query: str, limit: int) -> List[Dict[str, Any]]:
        # Uses PostgreSQL 'simple' dictionary to preserve Yoruba diacritics (no stemming)
        sql = text("""
            SELECT chunk_id, document_id, section, chunk_index, text, metadata,
                   ts_rank_cd(to_tsvector('simple', text), plainto_tsquery('simple', :query)) as rank
            FROM ai_intelligence.ai_chunks
            WHERE to_tsvector('simple', text) @@ plainto_tsquery('simple', :query)
            ORDER BY rank DESC
            LIMIT :limit
        """)
        result = await db.execute(sql, {"query": query, "limit": limit})
        return [dict(row) for row in result.mappings().all()]

    async def vector_search(self, db: AsyncSession, query_embedding: List[float], limit: int) -> List[Dict[str, Any]]:
        sql = text("""
            SELECT chunk_id, document_id, section, chunk_index, text, metadata,
                   (1 - (vector <=> :embedding::vector)) as similarity
            FROM ai_intelligence.ai_chunks
            WHERE vector IS NOT NULL
            ORDER BY vector <=> :embedding::vector ASC
            LIMIT :limit
        """)
        result = await db.execute(sql, {"embedding": query_embedding, "limit": limit})
        return [dict(row) for row in result.mappings().all()]

    def reciprocal_rank_fusion(self, lexical_results: List[Dict], vector_results: List[Dict], k: int = 60) -> List[Dict]:
        fused = {}
        
        for rank, item in enumerate(lexical_results):
            cid = item['chunk_id']
            if cid not in fused:
                fused[cid] = {**item, 'rrf_score': 0.0, 'lexical_rank': rank + 1, 'vector_rank': None}
            fused[cid]['rrf_score'] += 1.0 / (k + rank + 1)
            
        for rank, item in enumerate(vector_results):
            cid = item['chunk_id']
            if cid not in fused:
                fused[cid] = {**item, 'rrf_score': 0.0, 'lexical_rank': None, 'vector_rank': rank + 1}
            else:
                fused[cid]['vector_rank'] = rank + 1
            fused[cid]['rrf_score'] += 1.0 / (k + rank + 1)
            
        return sorted(fused.values(), key=lambda x: x['rrf_score'], reverse=True)

    def filter_by_permissions(self, results: List[Dict], allowed_access_levels: List[str]) -> List[Dict]:
        """
        SECURITY CRITICAL: Filters candidates BEFORE reranking to prevent 
        the reranker from wasting compute on, or accidentally elevating, 
        inaccessible documents.
        """
        filtered = []
        for item in results:
            meta = item.get('metadata', {})
            if isinstance(meta, str):
                meta = json.loads(meta)
                item['metadata'] = meta
            
            access_level = meta.get('access_level', 'public')
            if access_level in allowed_access_levels:
                filtered.append(item)
        return filtered

    def rerank(self, query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
        if not self.reranker or not candidates:
            # Graceful degradation: fallback to RRF score if model failed to load
            for item in candidates[:top_k]:
                item['final_score'] = item.get('rrf_score', 0.0)
            return candidates[:top_k]
            
        pairs = [[query, item['text']] for item in candidates]
        try:
            scores = self.reranker.predict(pairs, show_progress_bar=False)
            for item, score in zip(candidates, scores):
                item['final_score'] = float(score)
        except Exception as e:
            logger.error(f"Reranking failed, falling back to RRF: {e}")
            for item in candidates:
                item['final_score'] = item.get('rrf_score', 0.0)
                
        return sorted(candidates, key=lambda x: x['final_score'], reverse=True)[:top_k]

    def format_results(self, candidates: List[Dict]) -> List[SearchResult]:
        results = []
        for item in candidates:
            meta = item.get('metadata', {})
            if isinstance(meta, str):
                meta = json.loads(meta)
            
            # Safe excerpt: truncate to 200 chars to prevent massive payloads
            raw_text = item.get('text', '')
            excerpt = raw_text[:200] + "..." if len(raw_text) > 200 else raw_text
            
            results.append(SearchResult(
                chunk_id=item['chunk_id'],
                document_id=item['document_id'],
                title=meta.get('title', 'Unknown Title'),
                section=item.get('section', 'unknown'),
                page_number=meta.get('page_number', 1),
                chunk_index=item.get('chunk_index', 0),
                score=round(item.get('final_score', 0.0), 4),
                excerpt=excerpt,
                metadata=meta
            ))
        return results

    async def search(
        self, 
        db: AsyncSession, 
        query: str, 
        query_embedding: List[float], 
        allowed_access_levels: List[str] = ["public"], 
        offset: int = 0,
        limit: Optional[int] = None
    ) -> List[SearchResult]:
        clean_query = self.validate_query(query)
        final_limit = limit or self.final_limit
        
        # 1. Parallel retrieval (conceptually, executed sequentially here for simplicity)
        lexical_results = await self.lexical_search(db, clean_query, self.candidate_limit)
        vector_results = await self.vector_search(db, query_embedding, self.candidate_limit)
        
        # 2. Candidate Fusion (RRF)
        fused = self.reciprocal_rank_fusion(lexical_results, vector_results, k=self.rrf_k)
        
        # 3. STRICT Permission Filtering (Before reranking)
        allowed = self.filter_by_permissions(fused, allowed_access_levels)
        
        # 4. BGE Reranking
        reranked = self.rerank(clean_query, allowed, top_k=self.candidate_limit)
        
        # 5. Pagination & Formatting
        paginated = reranked[offset:offset + final_limit]
        return self.format_results(paginated)