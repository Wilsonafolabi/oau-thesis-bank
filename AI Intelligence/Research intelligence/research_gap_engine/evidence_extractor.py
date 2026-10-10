import re
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class ExtractedEvidence:
    document_id: str
    title: str
    research_questions: List[str]
    limitations: List[str]
    findings: List[str]
    future_work: List[str]
    raw_passages: Dict[str, List[str]]  # section -> passages

class EvidenceExtractor:
    """Extracts structured research elements from thesis chunks."""
    
    SECTION_PATTERNS = {
        "research_questions": [
            r"(?:research\s+questions?|objectives?|aims?)",
            r"(?:this\s+(?:study|research|thesis)\s+(?:aims?|seeks?|investigates?))",
        ],
        "limitations": [
            r"(?:limitations?|constraints?|shortcomings?)",
            r"(?:this\s+(?:study|research)\s+(?:is|was)\s+(?:limited|constrained))",
        ],
        "findings": [
            r"(?:findings?|results?|conclusions?)",
            r"(?:the\s+(?:study|research)\s+(?:found|revealed|demonstrated))",
        ],
        "future_work": [
            r"(?:future\s+(?:work|research|studies|directions))",
            r"(?:further\s+research)",
            r"(?:recommendations?\s+for\s+future)",
        ],
    }
    
    def extract_from_chunks(self, chunks: List[Dict]) -> ExtractedEvidence:
        """Extract research elements from a list of chunks belonging to one document."""
        if not chunks:
            return None
        
        doc_id = chunks[0].get("document_id")
        title = chunks[0].get("metadata", {}).get("title", "Unknown")
        
        evidence = ExtractedEvidence(
            document_id=doc_id,
            title=title,
            research_questions=[],
            limitations=[],
            findings=[],
            future_work=[],
            raw_passages={"research_questions": [], "limitations": [], "findings": [], "future_work": []}
        )
        
        for chunk in chunks:
            text = chunk.get("text", "")
            section = chunk.get("section", "").lower()
            
            # Check if chunk belongs to a relevant section
            for element_type, patterns in self.SECTION_PATTERNS.items():
                if any(re.search(p, section, re.IGNORECASE) for p in patterns):
                    # Extract sentences that match the element type
                    sentences = self._extract_relevant_sentences(text, element_type)
                    if sentences:
                        getattr(evidence, element_type).extend(sentences)
                        evidence.raw_passages[element_type].extend(sentences)
        
        # Deduplicate
        for element_type in ["research_questions", "limitations", "findings", "future_work"]:
            unique_items = list(set(getattr(evidence, element_type)))
            setattr(evidence, element_type, unique_items)
            evidence.raw_passages[element_type] = list(set(evidence.raw_passages[element_type]))
        
        return evidence
    
    def _extract_relevant_sentences(self, text: str, element_type: str) -> List[str]:
        """Extract sentences relevant to the element type."""
        sentences = re.split(r'[.!?]+', text)
        relevant = []
        
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20:  # Skip very short sentences
                continue
            
            # Check if sentence contains keywords for this element type
            if element_type == "research_questions":
                if re.search(r'\b(what|how|why|whether|investigate|examine|explore|determine|assess)\b', sent, re.IGNORECASE):
                    relevant.append(sent)
            elif element_type == "limitations":
                if re.search(r'\b(limit\w*|constrain\w*|restrict\w*|unable|cannot|challenge\w*|drawback\w*|shortcoming\w*)\b', sent, re.IGNORECASE):
                    relevant.append(sent)
            elif element_type == "findings":
                if re.search(r'\b(found|revealed|demonstrated|showed|indicated|suggest|conclude|result)\b', sent, re.IGNORECASE):
                    relevant.append(sent)
            elif element_type == "future_work":
                if re.search(r'\b(future|further|recommend|should|could|next|subsequent|potential)\b', sent, re.IGNORECASE):
                    relevant.append(sent)
        
        return relevant[:5]  # Limit to top 5 per chunk

