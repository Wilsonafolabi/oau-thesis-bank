import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from rag.schemas import RAGRequest, RAGResponse, Citation, VerificationStatus
from rag.grounding_validator import GroundingValidator
from retrieval.hybrid_search import HybridSearchService
from embeddings.service import EmbeddingService
from llm_providers import get_router, ChatMessage, ChatRequest
from security.nemoguardrails.runtime import get_runtime
from security.nemoguardrails.schemas import GuardrailsRequest, GuardrailOutcome

logger = logging.getLogger(__name__)

class RAGService:
    """
    Production RAG service that integrates hybrid search, LLM generation,
    grounding validation, and NeMo Guardrails.
    """
    
    def __init__(self):
        self.search_service = HybridSearchService()
        self.embedding_service = EmbeddingService()
        self.grounding_validator = GroundingValidator()
        self.guardrails_runtime = get_runtime()
        self.router = get_router()
        
        # Context window limits
        self.max_context_tokens = int(os.getenv("RAG_MAX_CONTEXT_TOKENS", "3000"))
        self.max_answer_tokens = int(os.getenv("RAG_MAX_ANSWER_TOKENS", "1024"))
    
    def _wrap_evidence(self, chunks: List[Dict]) -> str:
        """
        Wraps retrieved evidence in untrusted markers to prevent injection.
        """
        wrapped = []
        for i, chunk in enumerate(chunks, 1):
            wrapped.append(f"<evidence id=\"{i}\">\n{chunk['text']}\n</evidence>")
        return "\n\n".join(wrapped)
    
    def _build_citations(self, search_results: List, retrieved_chunks: List[Dict]) -> List[Citation]:
        """
        Builds citation objects from search results.
        """
        citations = []
        for result in search_results:
            # Find corresponding chunk
            chunk = next((c for c in retrieved_chunks if c['chunk_id'] == result.chunk_id), None)
            if chunk:
                citations.append(Citation(
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    title=result.title,
                    section=result.section,
                    page_number=result.page_number,
                    chunk_index=result.chunk_index,
                    relevance_score=result.score,
                    excerpt=result.excerpt
                ))
        return citations
    
    def _build_prompt(self, question: str, evidence: str) -> str:
        """
        Builds the LLM prompt with evidence and instructions.
        """
        return f"""You are a research assistant helping with thesis analysis. Answer the question using ONLY the provided evidence.

Question: {question}

Evidence:
{evidence}

Instructions:
- Answer ONLY based on the evidence provided
- If the evidence doesn't contain the answer, say "I cannot find sufficient evidence to answer this question."
- Cite sources using [chunk_id] format
- Do not invent information not in the evidence
- Be concise and accurate

Answer:"""
    
    def _extract_citations_from_answer(self, answer: str) -> List[str]:
        """
        Extracts chunk IDs cited in the answer.
        """
        pattern = r'\[(\d+)\]'
        matches = re.findall(pattern, answer)
        return matches
    
    async def process(self, db: AsyncSession, request: RAGRequest) -> RAGResponse:
        """
        Main RAG processing pipeline.
        """
        try:
            # Step 1: Input guardrails
            guardrails_req = GuardrailsRequest(
                request_id=request.request_id,
                user_input=request.question,
                evidence=[]
            )
            guardrails_resp = await self.guardrails_runtime.run(guardrails_req)
            
            if guardrails_resp.outcome == GuardrailOutcome.BLOCKED:
                return RAGResponse(
                    request_id=request.request_id,
                    answer="I cannot process this request due to safety policies.",
                    citations=[],
                    verification_status=VerificationStatus.UNVERIFIABLE,
                    metadata={"blocked_reason": guardrails_resp.reason}
                )
            
            # Step 2: Generate query embedding
            query_embedding = self.embedding_service.embed_texts([request.question])[0]
            
            # Step 3: Hybrid search
            search_results = await self.search_service.search(
                db=db,
                query=request.question,
                query_embedding=query_embedding,
                allowed_access_levels=request.access_levels,
                offset=0,
                limit=request.max_context_chunks
            )
            
            if not search_results:
                return RAGResponse(
                    request_id=request.request_id,
                    answer="I cannot find any relevant documents in the thesis bank.",
                    citations=[],
                    verification_status=VerificationStatus.INSUFFICIENT_EVIDENCE,
                    metadata={"retrieval_status": "no_results"}
                )
            
            # Step 4: Fetch full chunks for context
            from sqlalchemy import select
            from db.models import AIChunk
            
            chunk_ids = [r.chunk_id for r in search_results]
            result = await db.execute(
                select(AIChunk).where(AIChunk.id.in_(chunk_ids))
            )
            retrieved_chunks = [
                {
                    'chunk_id': chunk.chunk_id,
                    'document_id': chunk.document_id,
                    'text': chunk.text,
                    'metadata': chunk.metadata or {}
                }
                for chunk in result.scalars().all()
            ]
            
            # Step 5: Wrap evidence
            evidence_text = self._wrap_evidence(retrieved_chunks)
            
            # Step 6: Build prompt and generate answer
            prompt = self._build_prompt(request.question, evidence_text)
            
            chat_request = ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                max_tokens=request.max_tokens,
                temperature=0.3
            )
            
            llm_response = self.router.complete(chat_request)
            answer = llm_response.content
            
            # Step 7: Build citations
            citations = self._build_citations(search_results, retrieved_chunks)
            
            # Step 8: Grounding validation
            status, confidence, invalid_citations = self.grounding_validator.validate_answer(
                answer, citations, retrieved_chunks
            )
            
            # Remove invalid citations
            if invalid_citations:
                citations = [c for c in citations if c.chunk_id not in invalid_citations]
                status = VerificationStatus.UNVERIFIABLE
                confidence = 0.0
            
            # Step 9: Output guardrails
            output_guardrails_req = GuardrailsRequest(
                request_id=request.request_id,
                user_input=answer,
                evidence=retrieved_chunks
            )
            output_guardrails_resp = await self.guardrails_runtime.run(output_guardrails_req)
            
            if output_guardrails_resp.outcome == GuardrailOutcome.BLOCKED:
                return RAGResponse(
                    request_id=request.request_id,
                    answer="The generated answer was blocked by safety policies.",
                    citations=[],
                    verification_status=VerificationStatus.UNVERIFIABLE,
                    metadata={"blocked_reason": output_guardrails_resp.reason}
                )
            
            # Step 10: Return response
            return RAGResponse(
                request_id=request.request_id,
                answer=answer,
                citations=citations,
                verification_status=status,
                confidence=confidence,
                metadata={
                    "chunks_retrieved": len(retrieved_chunks),
                    "chunks_cited": len(citations),
                    "llm_provider": llm_response.provider,
                    "llm_model": llm_response.model
                }
            )
            
        except Exception as e:
            logger.error(f"RAG processing failed: {e}", exc_info=True)
            return RAGResponse(
                request_id=request.request_id,
                answer="An error occurred while processing your request.",
                citations=[],
                verification_status=VerificationStatus.UNVERIFIABLE,
                metadata={"error": str(e)}
            )