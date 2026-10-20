import re
from typing import List, Dict, Any, Tuple
from rag.schemas import Citation, VerificationStatus

class GroundingValidator:
    """
    Validates that LLM-generated answers are actually grounded in retrieved evidence.
    This is a REAL check, not just prompting the LLM to cite sources.
    """
    
    def __init__(self):
        # Patterns to detect unsupported claims
        self.unsupported_patterns = [
            r"(?i)according to (?:my|the) (?:knowledge|training|data)",
            r"(?i)I (?:believe|think|assume|guess)",
            r"(?i)it is (?:likely|probably|possibly) that",
            r"(?i)(?:some|many|most) (?:sources|studies|researchers) (?:say|claim|suggest)",
        ]
        
    def extract_citations_from_text(self, answer: str) -> List[str]:
        """
        Extracts citation references from answer text.
        Looks for patterns like [c1], [999], [chunk_123], etc.
        """
        # Match patterns like [c1], [999], [chunk_123]
        pattern = r'\[([^\]]+)\]'
        matches = re.findall(pattern, answer)
        return matches
    
    def validate_citations(self, answer: str, citations: List[Citation], retrieved_chunks: List[Dict]) -> Tuple[bool, List[str]]:
        """
        Validates that all citations in the answer actually reference retrieved chunks.
        Returns (is_valid, list_of_invalid_citation_ids)
        """
        retrieved_chunk_ids = {chunk['chunk_id'] for chunk in retrieved_chunks}
        
        # Extract citations from answer text
        text_citations = self.extract_citations_from_text(answer)
        
        # Check if all text citations exist in retrieved chunks
        invalid_citations = []
        for cit in text_citations:
            if cit not in retrieved_chunk_ids:
                invalid_citations.append(cit)
        
        return len(invalid_citations) == 0, invalid_citations
    
    def check_evidence_support(self, answer: str, retrieved_chunks: List[Dict]) -> Tuple[VerificationStatus, float]:
        """
        Checks if the answer is supported by retrieved evidence.
        Returns (status, confidence_score)
        """
        if not retrieved_chunks:
            return VerificationStatus.INSUFFICIENT_EVIDENCE, 0.0
        
        # Check for unsupported claim patterns
        unsupported_count = 0
        for pattern in self.unsupported_patterns:
            if re.search(pattern, answer):
                unsupported_count += 1
        
        # Calculate simple overlap between answer and evidence
        answer_lower = answer.lower()
        evidence_text = " ".join([chunk['text'].lower() for chunk in retrieved_chunks])
        
        # Extract key terms from answer (simple word extraction)
        answer_words = set(re.findall(r'\b\w+\b', answer_lower))
        evidence_words = set(re.findall(r'\b\w+\b', evidence_text))
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'but', 'this', 'that', 'it', 'they', 'we', 'you', 'i'}
        answer_words -= stop_words
        evidence_words -= stop_words
        
        if not answer_words:
            overlap_ratio = 0.0
        else:
            overlap = answer_words & evidence_words
            overlap_ratio = len(overlap) / len(answer_words)
        
        # Determine verification status
        if unsupported_count > 0 or overlap_ratio < 0.3:
            return VerificationStatus.INSUFFICIENT_EVIDENCE, overlap_ratio
        elif overlap_ratio < 0.6:
            return VerificationStatus.PARTIAL, overlap_ratio
        else:
            return VerificationStatus.GROUNDED, overlap_ratio
    
    def validate_answer(self, answer: str, citations: List[Citation], retrieved_chunks: List[Dict]) -> Tuple[VerificationStatus, float, List[str]]:
        """
        Complete validation of answer grounding.
        Returns (status, confidence, invalid_citation_ids)
        """
        # Validate citations
        citations_valid, invalid_citations = self.validate_citations(answer, citations, retrieved_chunks)
        
        if not citations_valid:
            return VerificationStatus.UNVERIFIABLE, 0.0, invalid_citations
        
        # Check evidence support
        status, confidence = self.check_evidence_support(answer, retrieved_chunks)
        
        return status, confidence, []