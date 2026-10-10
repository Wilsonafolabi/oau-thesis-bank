import json
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
from llm_providers import get_router, ChatMessage, ChatRequest
from research_gap_engine.evidence_extractor import ExtractedEvidence

class GapType(str, Enum):
    EXPLICIT_LIMITATION = "explicit_limitation"  # Stated by authors
    CONFLICTING_FINDINGS = "conflicting_findings"  # Contradictory results
    UNDEREXPLORED_AREA = "underexplored_area"  # Inferred from comparison
    FUTURE_OPPORTUNITY = "future_opportunity"  # From future work sections

@dataclass
class ResearchGap:
    gap_type: GapType
    description: str
    supporting_evidence: List[Dict]  # [{doc_id, passage, section}]
    explanation: str
    limitations: str
    confidence: float  # 0.0 to 1.0

class GapAnalyzer:
    """Analyzes extracted evidence to identify research gaps."""
    
    def __init__(self):
        self.router = get_router()
        self.min_theses_for_comparison = 3
        self.min_evidence_per_gap = 2
    
    def analyze_gaps(self, evidence_list: List[ExtractedEvidence]) -> List[ResearchGap]:
        """Analyze multiple theses to identify research gaps."""
        if len(evidence_list) < self.min_theses_for_comparison:
            return []
        
        gaps = []
        
        # 1. Extract explicit limitations
        explicit_gaps = self._extract_explicit_limitations(evidence_list)
        gaps.extend(explicit_gaps)
        
        # 2. Find conflicting findings
        conflict_gaps = self._find_conflicting_findings(evidence_list)
        gaps.extend(conflict_gaps)
        
        # 3. Identify underexplored areas
        underexplored_gaps = self._identify_underexplored_areas(evidence_list)
        gaps.extend(underexplored_gaps)
        
        # 4. Extract future opportunities
        future_gaps = self._extract_future_opportunities(evidence_list)
        gaps.extend(future_gaps)
        
        return gaps
    
    def _extract_explicit_limitations(self, evidence_list: List[ExtractedEvidence]) -> List[ResearchGap]:
        """Extract gaps from explicitly stated limitations."""
        gaps = []
        
        for evidence in evidence_list:
            if not evidence.limitations:
                continue
            
            for limitation in evidence.limitations:
                gap = ResearchGap(
                    gap_type=GapType.EXPLICIT_LIMITATION,
                    description=limitation,
                    supporting_evidence=[{
                        "document_id": evidence.document_id,
                        "title": evidence.title,
                        "passage": limitation,
                        "section": "limitations"
                    }],
                    explanation=f"The authors of '{evidence.title}' explicitly identified this as a limitation of their study.",
                    limitations="This is an explicit statement by the authors, not an inference.",
                    confidence=0.95
                )
                gaps.append(gap)
        
        return gaps
    
    def _find_conflicting_findings(self, evidence_list: List[ExtractedEvidence]) -> List[ResearchGap]:
        """Find contradictory findings across theses."""
        gaps = []
        
        # Group findings by topic/keyword
        findings_by_topic = {}
        for evidence in evidence_list:
            for finding in evidence.findings:
                # Simple keyword extraction
                keywords = self._extract_keywords(finding)
                for keyword in keywords:
                    if keyword not in findings_by_topic:
                        findings_by_topic[keyword] = []
                    findings_by_topic[keyword].append({
                        "document_id": evidence.document_id,
                        "title": evidence.title,
                        "finding": finding
                    })
        
        # Use LLM to detect conflicts
        for topic, findings in findings_by_topic.items():
            if len(findings) < 2:
                continue
            
            conflict = self._detect_conflict_with_llm(topic, findings)
            if conflict:
                gaps.append(conflict)
        
        return gaps
    
    def _detect_conflict_with_llm(self, topic: str, findings: List[Dict]) -> Optional[ResearchGap]:
        """Use LLM to detect if findings conflict."""
        findings_text = "\n\n".join([
            f"From '{f['title']}': {f['finding']}" for f in findings
        ])
        
        prompt = f"""Analyze these research findings about '{topic}' and determine if they conflict or contradict each other.

Findings:
{findings_text}

If there is a clear conflict, respond with JSON:
{{
  "has_conflict": true,
  "description": "Brief description of the conflict",
  "explanation": "Why these findings appear to contradict"
}}

If no conflict, respond with:
{{
  "has_conflict": false
}}
"""
        
        try:
            response = self.router.complete(ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                max_tokens=500,
                temperature=0.1
            ))
            
            result = json.loads(response.content)
            if result.get("has_conflict"):
                return ResearchGap(
                    gap_type=GapType.CONFLICTING_FINDINGS,
                    description=result["description"],
                    supporting_evidence=[{
                        "document_id": f["document_id"],
                        "title": f["title"],
                        "passage": f["finding"],
                        "section": "findings"
                    } for f in findings],
                    explanation=result["explanation"],
                    limitations="Conflict detection is based on LLM analysis and may not capture nuanced differences in methodology or context.",
                    confidence=0.75
                )
        except Exception as e:
            print(f"Error detecting conflict: {e}")
        
        return None
    
    def _identify_underexplored_areas(self, evidence_list: List[ExtractedEvidence]) -> List[ResearchGap]:
        """Identify areas that appear underexplored based on research questions."""
        gaps = []
        
        # Collect all research questions
        all_questions = []
        for evidence in evidence_list:
            all_questions.extend([(evidence.document_id, evidence.title, q) for q in evidence.research_questions])
        
        if len(all_questions) < 2:
            return gaps
        
        # Use LLM to find gaps
        questions_text = "\n".join([
            f"From '{title}': {q}" for _, title, q in all_questions
        ])
        
        prompt = f"""Based on these research questions from multiple theses, identify potential underexplored areas or research gaps.

Research Questions:
{questions_text}

Respond with JSON array of gaps:
[
  {{
    "description": "Description of the underexplored area",
    "explanation": "Why this appears to be underexplored",
    "supporting_docs": ["doc_id1", "doc_id2"]
  }}
]

Only identify gaps if you can see clear evidence of missing coverage. Limit to 3 most significant gaps.
"""
        
        try:
            response = self.router.complete(ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                max_tokens=1000,
                temperature=0.2
            ))
            
            result = json.loads(response.content)
            for gap_data in result:
                supporting_docs = gap_data.get("supporting_docs", [])
                supporting_evidence = [
                    {
                        "document_id": doc_id,
                        "title": title,
                        "passage": q,
                        "section": "research_questions"
                    }
                    for doc_id, title, q in all_questions
                    if doc_id in supporting_docs
                ]
                
                if len(supporting_evidence) >= self.min_evidence_per_gap:
                    gap = ResearchGap(
                        gap_type=GapType.UNDEREXPLORED_AREA,
                        description=gap_data["description"],
                        supporting_evidence=supporting_evidence,
                        explanation=gap_data["explanation"],
                        limitations="This gap is inferred from comparing research questions and may not reflect the full scope of existing research.",
                        confidence=0.65
                    )
                    gaps.append(gap)
        except Exception as e:
            print(f"Error identifying underexplored areas: {e}")
        
        return gaps
    
    def _extract_future_opportunities(self, evidence_list: List[ExtractedEvidence]) -> List[ResearchGap]:
        """Extract future research opportunities from future work sections."""
        gaps = []
        
        for evidence in evidence_list:
            if not evidence.future_work:
                continue
            
            for opportunity in evidence.future_work:
                gap = ResearchGap(
                    gap_type=GapType.FUTURE_OPPORTUNITY,
                    description=opportunity,
                    supporting_evidence=[{
                        "document_id": evidence.document_id,
                        "title": evidence.title,
                        "passage": opportunity,
                        "section": "future_work"
                    }],
                    explanation=f"The authors of '{evidence.title}' suggested this as a direction for future research.",
                    limitations="This is a suggestion by the authors and may not reflect current research priorities.",
                    confidence=0.85
                )
                gaps.append(gap)
        
        return gaps
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract key terms from text."""
        # Simple keyword extraction
        words = re.findall(r'\b[A-Za-z]{4,}\b', text.lower())
        # Remove common words
        stop_words = {'this', 'that', 'with', 'from', 'have', 'been', 'were', 'they', 'their', 'which', 'would', 'could', 'should'}
        return [w for w in words if w not in stop_words][:5]
