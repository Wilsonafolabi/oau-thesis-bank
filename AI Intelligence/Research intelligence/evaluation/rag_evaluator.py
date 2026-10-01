import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class RAGEvaluator:
    def __init__(self):
        pass

    def evaluate_grounding(self, query: str, retrieved_context: str, generated_answer: str) -> Dict[str, Any]:
        if not retrieved_context or not generated_answer:
            return {"grounded": False, "score": 0.0, "reason": "Missing context or answer"}

        context_words = set(re.findall(r'\b\w{4,}\b', retrieved_context.lower()))
        answer_words = set(re.findall(r'\b\w{4,}\b', generated_answer.lower()))
        
        stop_words = {'this', 'that', 'with', 'from', 'have', 'been', 'were', 'they', 'their', 'about'}
        context_words -= stop_words
        answer_words -= stop_words

        if not context_words:
            return {"grounded": False, "score": 0.0, "reason": "No meaningful words in context"}

        overlap = answer_words.intersection(context_words)
        score = len(overlap) / len(answer_words) if answer_words else 0.0
        is_grounded = score >= 0.30
        
        return {
            "grounded": is_grounded,
            "score": round(score, 2),
            "overlap_count": len(overlap),
            "reason": f"Found {len(overlap)} matching meaningful terms out of {len(answer_words)} in answer."
        }

    def evaluate_batch(self, evaluation_set: List[Dict[str, str]]) -> Dict[str, Any]:
        results = []
        grounded_count = 0
        
        for item in evaluation_set:
            res = self.evaluate_grounding(
                query=item.get("query", ""),
                retrieved_context=item.get("context", ""),
                generated_answer=item.get("answer", "")
            )
            results.append(res)
            if res["grounded"]:
                grounded_count += 1
                
        pass_rate = (grounded_count / len(evaluation_set)) * 100 if evaluation_set else 0.0
        
        return {
            "total_evaluated": len(evaluation_set),
            "grounded_count": grounded_count,
            "grounding_pass_rate_percent": round(pass_rate, 2),
            "detailed_results": results
        }