import sys
import os
import pytest
import numpy as np

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from recommendation.service import RecommendationService, InteractionLogger
from research_intelligence.gap_engine.service import GapEngine
from proposal_checker.service import ProposalChecker
from evaluation.rag_evaluator import RAGEvaluator

def test_recommendation_service_initialization():
    mock_theses = [{"id": "t1", "created_at": None}]
    service = RecommendationService(theses=mock_theses)
    assert service.use_learned == False

def test_interaction_logging():
    logger = InteractionLogger()
    logger.log_event("user_1", "thesis_1", "view")
    assert len(logger.interactions) == 1
    assert logger.interactions[0]["event_type"] == "view"

def test_gap_engine_initialization():
    engine = GapEngine()
    # Check that it initialized safely without BERTopic installed
    assert engine.model is None

def test_proposal_checker_similarity():
    class MockEmbedder:
        def embed_text(self, text): return np.array([1.0, 0.0, 0.0])
    
    checker = ProposalChecker(embedding_service=MockEmbedder())
    chunks = [
        {"thesis_id": "t1", "id": "c1", "vector": np.array([1.0, 0.0, 0.0]), "text": "Exact match text", "page": 1}
    ]
    results = checker.check_similarity("Exact match text", chunks, threshold=0.90)
    assert len(results) == 1
    assert results[0]["similarity_score"] == 1.0

def test_rag_evaluator_grounding_pass():
    evaluator = RAGEvaluator()
    context = "The OAU Thesis Bank uses BGE-large embeddings and pgvector for hybrid retrieval."
    answer = "The system uses BGE-large embeddings and pgvector."
    result = evaluator.evaluate_grounding("query", context, answer)
    assert result["grounded"] == True
    assert result["score"] >= 0.30

def test_rag_evaluator_grounding_fail():
    evaluator = RAGEvaluator()
    context = "The system uses Python and Django."
    answer = "The system is built with Node.js and React."
    result = evaluator.evaluate_grounding("query", context, answer)
    assert result["grounded"] == False
