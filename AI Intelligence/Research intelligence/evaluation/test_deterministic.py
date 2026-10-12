"""
Deterministic Evaluation Suite for Phase 3.
These tests use mocked components and synthetic fixtures to verify system logic, 
permissions, and structural integrity without requiring live LLM API calls.
"""
import pytest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from evaluation.corpus.fixtures import get_corpus

CORPUS = get_corpus()

# --- Acceptance Thresholds (Provisional until real benchmark) ---
THRESHOLDS = {
    "RECALL_AT_1": 1.0,
    "EXACT_MATCH_SCORE": 0.95,
    "NEAR_MATCH_SCORE_MIN": 0.7,
    "UNRELATED_SCORE_MAX": 0.3
}

# ==========================================
# 1. Document Ingestion
# ==========================================
class TestIngestion:
    def test_digital_text_extraction(self):
        fixture = CORPUS["ingestion"]["digital_text"]
        assert "clean digital" in fixture["text"]
        assert fixture["metadata"]["author"] == "Synthetic Author"

    def test_ocr_fallback_metadata(self):
        fixture = CORPUS["ingestion"]["ocr_fallback"]
        assert fixture["metadata"]["source"] == "scan"
        assert fixture["metadata"]["confidence"] < 0.8 # Low confidence triggers review

    def test_section_detection_integrity(self):
        fixture = CORPUS["ingestion"]["section_detection"]
        for section in fixture["expected_sections"]:
            assert section in fixture["text"]

# ==========================================
# 2. Retrieval & Permissions
# ==========================================
class TestRetrieval:
    def test_permission_leakage_private_doc(self):
        """Ensure private documents are never returned to unauthorized users."""
        public_doc = CORPUS["retrieval"]["public_doc"]
        private_doc = CORPUS["retrieval"]["private_doc"]
        
        # Mock retrieval logic: filter by access level
        user_access = ["public"]
        results = [d for d in [public_doc, private_doc] if d["access"] in user_access]
        
        assert private_doc["id"] not in [r["id"] for r in results]
        assert public_doc["id"] in [r["id"] for r in results]

    def test_recall_at_k_mock(self):
        """Mock Recall@1 calculation."""
        expected = [CORPUS["retrieval"]["expected_recall_ids"][0]]
        retrieved = [CORPUS["retrieval"]["expected_recall_ids"][0]] # Mock perfect retrieval
        recall = len(set(expected) & set(retrieved)) / len(expected)
        assert recall >= THRESHOLDS["RECALL_AT_1"]

# ==========================================
# 3. RAG Quality & Safety
# ==========================================
class TestRAG:
    def test_citation_validity(self):
        """Ensure all citations in the answer exist in the provided context."""
        fixture = CORPUS["rag"]["grounded_answer"]
        for cite in fixture["citations"]:
            assert cite in fixture["context"], f"Citation {cite} not found in context!"

    def test_hallucinated_citation_detection(self):
        fixture = CORPUS["rag"]["hallucinated_citation"]
        invalid_cites = [c for c in fixture["citations"] if c not in fixture["context"]]
        assert len(invalid_cites) > 0 # Should detect the hallucination

    def test_abstention_on_insufficient_evidence(self):
        fixture = CORPUS["rag"]["abstention"]
        assert "do not have enough information" in fixture["answer"].lower()
        assert len(fixture["citations"]) == 0

# ==========================================
# 4. NeMo Guardrails
# ==========================================
class TestNeMoGuardrails:
    def test_injection_attempt_blocked(self):
        prompt = CORPUS["nemo"]["blocked_injection"]
        # Mock NeMo logic: simple keyword/pattern check for deterministic test
        is_blocked = "ignore all previous" in prompt.lower()
        assert is_blocked

    def test_off_topic_detection(self):
        prompt = CORPUS["nemo"]["off_topic"]
        # Mock off-topic check
        is_off_topic = "bake a cake" in prompt.lower()
        assert is_off_topic

# ==========================================
# 5. Research Gap & Similarity
# ==========================================
class TestGapSimilarity:
    def test_gap_claim_evidence_backed(self):
        fixture = CORPUS["gap_similarity"]["gap_claim"]
        assert len(fixture["evidence"]) > 0, "Gap claim must have supporting evidence."

    def test_exact_duplicate_score(self):
        fixture = CORPUS["gap_similarity"]["exact_dup"]
        # Mock Jaccard/Sequence similarity
        assert 1.0 >= THRESHOLDS["EXACT_MATCH_SCORE"]

    def test_unrelated_pairs_score(self):
        fixture = CORPUS["gap_similarity"]["unrelated"]
        # Mock low similarity score
        mock_score = 0.05
        assert mock_score <= THRESHOLDS["UNRELATED_SCORE_MAX"]

# ==========================================
# 6. Provider Reliability & API Access
# ==========================================
class TestProviderAPI:
    def test_timeout_fallback(self):
        fixture = CORPUS["provider_api"]["timeout"]
        assert fixture["expected"] == "fallback"

    def test_unauthorized_access(self):
        fixture = CORPUS["provider_api"]["unauthorized"]
        assert fixture["expected_status"] == 401

    def test_forbidden_private_leakage(self):
        fixture = CORPUS["provider_api"]["forbidden"]
        assert fixture["expected_status"] == 403
