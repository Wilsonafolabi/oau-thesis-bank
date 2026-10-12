import re
from typing import List, Set

class BoilerplateFilter:
    """Filters out references, quotations, common phrases, and boilerplate text."""
    
    # Common academic boilerplate patterns
    BOILERPLATE_PATTERNS = [
        r"^(acknowledgements?|abstract|table of contents|list of (figures|tables))\s*$",
        r"^(references|bibliography|works cited)\s*$",
        r"^(appendix|appendices)\s*$",
        r"^(chapter|section)\s+\d+",
    ]
    
    # Common phrases that appear in many documents
    COMMON_PHRASES = {
        "in this study we",
        "the purpose of this research",
        "this thesis is organized as follows",
        "the results show that",
        "further research is needed",
        "according to the literature",
        "the methodology used in this",
        "data was collected from",
        "the findings suggest that",
        "limitations of this study include",
    }
    
    # Reference patterns (citations, bibliographic entries)
    REFERENCE_PATTERNS = [
        r"\[\d+\]",  # [1], [2], etc.
        r"\(\w+,\s*\d{4}\)",  # (Author, 2020)
        r"^\s*\w+,\s*\w+\.\s*\(\d{4}\)\.",  # Author, A. (2020).
        r"https?://\S+",  # URLs
        r"doi:\S+",  # DOI references
    ]
    
    def __init__(self, min_chunk_length: int = 50):
        self.min_chunk_length = min_chunk_length
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for efficiency."""
        self.boilerplate_regex = [re.compile(p, re.IGNORECASE) for p in self.BOILERPLATE_PATTERNS]
        self.reference_regex = [re.compile(p) for p in self.REFERENCE_PATTERNS]
    
    def is_boilerplate(self, text: str) -> bool:
        """Check if text is boilerplate (section headers, etc.)."""
        text_clean = text.strip().lower()
        
        # Check against boilerplate patterns
        for pattern in self.boilerplate_regex:
            if pattern.search(text_clean):
                return True
        
        # Check if too short
        if len(text_clean) < self.min_chunk_length:
            return True
        
        return False
    
    def is_reference(self, text: str) -> bool:
        """Check if text is a reference or citation."""
        # Check for reference patterns
        for pattern in self.reference_regex:
            if pattern.search(text):
                return True
        
        # Check if it looks like a bibliographic entry
        if re.match(r"^\s*\w+,\s*\w+\.\s*\(\d{4}\)", text):
            return True
        
        return False
    
    def contains_common_phrase(self, text: str) -> bool:
        """Check if text contains common academic phrases."""
        text_lower = text.lower()
        for phrase in self.COMMON_PHRASES:
            if phrase in text_lower:
                return True
        return False
    
    def filter_chunks(self, chunks: List[dict]) -> List[dict]:
        """Filter out boilerplate and reference chunks."""
        filtered = []
        for chunk in chunks:
            text = chunk.get("text", "")
            
            # Skip boilerplate
            if self.is_boilerplate(text):
                continue
            
            # Skip references
            if self.is_reference(text):
                continue
            
            filtered.append(chunk)
        
        return filtered
