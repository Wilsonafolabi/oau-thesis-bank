import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from retrieval.hybrid_search import HybridSearchService, SearchResult
from retrieval.evaluation import calculate_recall_at_k, calculate_mrr, calculate_ndcg_at_k

# ==============================================================================
# HYBRID SEARCH TESTS
# ==============================================================================

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def search_service():
    with patch('retrieval.hybrid_search.CrossEncoder') as mock_ce:
        mock_ce.return_value.predict.return_value = [0.95, 0.85, 0.10]
        service = HybridSearchService()
        service.candidate_limit = 10
        service.final_limit = 5
        return service

@pytest.mark.asyncio
async def test_empty_and_malformed_query_validation(search_service):
    with pytest.raises(ValueError, match="non-empty string"):
        search_service.validate_query("")
    with pytest.raises(ValueError, match="too short"):
        search_service.validate_query(" a ")

@pytest.mark.asyncio
async def test_yoruba_diacritics_preserved(search_service):
    query = "  Àkòyàbà: Ìwádìí yìí dá lórí ẹ̀kọ́  "
    clean = search_service.validate_query(query)
    assert "Àkòyàbà" in clean
    assert "Ìwádìí" in clean
    assert "ẹ̀kọ́" in clean
    assert clean == "Àkòyàbà: Ìwádìí yìí dá lórí ẹ̀kọ́"

@pytest.mark.asyncio
async def test_permission_filtering_blocks_private(search_service):
    results = [
        {"chunk_id": "c1", "text": "t1", "metadata": json.dumps({"access_level": "public", "title": "T1"})},
        {"chunk_id": "c2", "text": "t2", "metadata": json.dumps({"access_level": "private", "title": "T2"})},
    ]
    filtered = search_service.filter_by_permissions(results, ["public"])
    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == "c1"

@pytest.mark.asyncio
async def test_rrf_fusion_prioritizes_cross_matches(search_service):
    lexical = [
        {"chunk_id": "c1", "text": "t1", "metadata": "{}"}, 
        {"chunk_id": "c2", "text": "t2", "metadata": "{}"}
    ]
    vector = [
        {"chunk_id": "c2", "text": "t2", "metadata": "{}"}, 
        {"chunk_id": "c3", "text": "t3", "metadata": "{}"}
    ]
    
    fused = search_service.reciprocal_rank_fusion(lexical, vector, k=60)
    assert fused[0]["chunk_id"] == "c2"
    assert fused[0]["lexical_rank"] == 2
    assert fused[0]["vector_rank"] == 1

@pytest.mark.asyncio
async def test_full_search_pipeline_integration(search_service, mock_db):
    mock_row = {
        "chunk_id": "c1", "document_id": "d1", "section": "intro", "chunk_index": 0, 
        "text": "Yoruba text ẹ̀kọ́ is important.", 
        "metadata": json.dumps({"access_level": "public", "title": "Test Thesis", "page_number": 1})
    }
    
    # Properly mock the SQLAlchemy Result object
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]
    mock_db.execute.return_value = mock_result
    
    results = await search_service.search(
        db=mock_db,
        query="ẹ̀kọ́",
        query_embedding=[0.1] * 1024,
        allowed_access_levels=["public"],
        offset=0,
        limit=5
    )
    
    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert results[0].chunk_id == "c1"
    assert "ẹ̀kọ́" in results[0].excerpt
    assert results[0].score > 0

# ==============================================================================
# EVALUATION METRICS TESTS
# ==============================================================================

def test_recall_at_k():
    retrieved = ["d1", "d2", "d3", "d4", "d5"]
    relevant = ["d1", "d3", "d6"]
    assert calculate_recall_at_k(retrieved, relevant, k=3) == 2/3
    assert calculate_recall_at_k(retrieved, relevant, k=2) == 1/3

def test_mrr():
    retrieved = ["d4", "d2", "d1", "d3"]
    relevant = ["d1", "d3"]
    assert calculate_mrr(retrieved, relevant) == 1/3

def test_ndcg_at_k():
    retrieved = ["d1", "d4", "d2", "d3"]
    relevant = ["d1", "d2"]
    ndcg = calculate_ndcg_at_k(retrieved, relevant, k=4)
    assert 0.91 < ndcg < 0.93