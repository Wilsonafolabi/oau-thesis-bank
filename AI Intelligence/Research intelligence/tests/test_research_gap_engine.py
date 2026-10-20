import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from research_gap_engine.evidence_extractor import EvidenceExtractor
from research_gap_engine.gap_analysis import GapAnalyzer, GapType
from research_gap_engine.engine import ResearchGapEngine

class TestEvidenceExtractor:
    def test_extract_from_chunks_with_limitations(self):
        chunks = [
            {
                "document_id": "doc1",
                "metadata": {"title": "Thesis 1"},
                "text": "This study was limited by the small sample size. The research could not include rural areas.",
                "section": "limitations"
            }
        ]
        
        extractor = EvidenceExtractor()
        evidence = extractor.extract_from_chunks(chunks)
        
        assert evidence.document_id == "doc1"
        assert len(evidence.limitations) > 0
        assert any("sample size" in lim for lim in evidence.limitations)
    
    def test_extract_from_chunks_with_future_work(self):
        chunks = [
            {
                "document_id": "doc1",
                "metadata": {"title": "Thesis 1"},
                "text": "Future research should explore the impact of climate change. Further studies could examine long-term effects.",
                "section": "future work"
            }
        ]
        
        extractor = EvidenceExtractor()
        evidence = extractor.extract_from_chunks(chunks)
        
        assert len(evidence.future_work) > 0
        assert any("climate change" in fw for fw in evidence.future_work)
    
    def test_extract_from_empty_chunks(self):
        extractor = EvidenceExtractor()
        evidence = extractor.extract_from_chunks([])
        assert evidence is None

class TestGapAnalyzer:
    @pytest.fixture
    def mock_router(self):
        with patch('research_gap_engine.gap_analysis.get_router') as mock:
            router = MagicMock()
            mock.return_value = router
            yield router
    
    def test_extract_explicit_limitations(self, mock_router):
        from research_gap_engine.evidence_extractor import ExtractedEvidence
        
        evidence_list = [
            ExtractedEvidence(
                document_id="doc1",
                title="Thesis 1",
                research_questions=[],
                limitations=["Small sample size limited the generalizability"],
                findings=[],
                future_work=[],
                raw_passages={}
            )
        ]
        
        analyzer = GapAnalyzer()
        gaps = analyzer._extract_explicit_limitations(evidence_list)
        
        assert len(gaps) == 1
        assert gaps[0].gap_type == GapType.EXPLICIT_LIMITATION
        assert "sample size" in gaps[0].description
    
    def test_insufficient_theses(self, mock_router):
        from research_gap_engine.evidence_extractor import ExtractedEvidence
        
        evidence_list = [
            ExtractedEvidence("doc1", "Thesis 1", [], [], [], [], {}),
            ExtractedEvidence("doc2", "Thesis 2", [], [], [], [], {})
        ]
        
        analyzer = GapAnalyzer()
        gaps = analyzer.analyze_gaps(evidence_list)
        
        assert len(gaps) == 0  # Need at least 3 theses

class TestResearchGapEngine:
    @pytest.mark.asyncio
    async def test_empty_corpus(self):
        engine = ResearchGapEngine()
        
        with patch.object(engine.search_service, 'search', return_value=[]):
            result = await engine.analyze_research_gaps(
                db=AsyncMock(),
                query="test query",
                user_id="user1"
            )
            
            assert result["corpus_size"] == 0
            assert result["sufficient_evidence"] == False
            assert "No relevant theses" in result["limitations"]
    
    @pytest.mark.asyncio
    async def test_insufficient_theses(self):
        engine = ResearchGapEngine()
        
        # Mock search results with only 2 theses
        mock_results = [
            MagicMock(document_id="doc1", chunk_id="c1"),
            MagicMock(document_id="doc1", chunk_id="c2"),
            MagicMock(document_id="doc2", chunk_id="c3"),
        ]
        
        with patch.object(engine.search_service, 'search', return_value=mock_results):
            result = await engine.analyze_research_gaps(
                db=AsyncMock(),
                query="test query",
                user_id="user1"
            )
            
            assert result["corpus_size"] == 2
            assert result["sufficient_evidence"] == False
            assert "Insufficient evidence" in result["limitations"]
    
    @pytest.mark.asyncio
    async def test_inaccessible_theses_filtered(self):
        engine = ResearchGapEngine()
        
        # Mock search that respects access levels
        mock_results = [
            MagicMock(document_id="doc1", chunk_id="c1"),
        ]
        
        with patch.object(engine.search_service, 'search', return_value=mock_results) as mock_search:
            await engine.analyze_research_gaps(
                db=AsyncMock(),
                query="test query",
                user_id="user1",
                access_levels=["public"]
            )
            
            # Verify search was called with access levels
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["allowed_access_levels"] == ["public"]
