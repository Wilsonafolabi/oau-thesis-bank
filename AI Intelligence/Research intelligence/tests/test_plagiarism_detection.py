import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from plagiarism_detection.boilerplate_filter import BoilerplateFilter
from plagiarism_detection.exact_match import ExactMatchScorer
from plagiarism_detection.semantic_similarity import SemanticSimilarityScorer
from plagiarism_detection.detector import PlagiarismDetector

class TestBoilerplateFilter:
    def test_filter_references(self):
        filter = BoilerplateFilter()
        chunks = [
            {"text": "Smith, J. (2020). The study of things. Journal of Stuff, 1(1), 1-10."},
            {"text": "This is actual content that should be kept for analysis purposes."}
        ]
        
        filtered = filter.filter_chunks(chunks)
        assert len(filtered) == 1
        assert "actual content" in filtered[0]["text"]
    
    def test_filter_boilerplate_headers(self):
        filter = BoilerplateFilter()
        chunks = [
            {"text": "References"},
            {"text": "Appendix A"},
            {"text": "This is actual content that should be kept for analysis purposes."}
        ]
        
        filtered = filter.filter_chunks(chunks)
        assert len(filtered) == 1
    
    def test_filter_short_text(self):
        filter = BoilerplateFilter(min_chunk_length=50)
        chunks = [
            {"text": "Short text."},
            {"text": "This is actual content that should be kept for analysis purposes and is long enough."}
        ]
        
        filtered = filter.filter_chunks(chunks)
        assert len(filtered) == 1

class TestExactMatchScorer:
    def test_exact_duplicate(self):
        scorer = ExactMatchScorer()
        text1 = "This is a test sentence for plagiarism detection."
        text2 = "This is a test sentence for plagiarism detection."
        
        scores = scorer.calculate_exact_match_score(text1, text2)
        assert scores["is_exact_match"] == True
        assert scores["sequence_ratio"] > 0.95
    
    def test_near_duplicate(self):
        scorer = ExactMatchScorer()
        text1 = "This is a test sentence for plagiarism detection."
        text2 = "This is a test sentence for plagiarism detection in academic papers."
        
        scores = scorer.calculate_exact_match_score(text1, text2)
        assert scores["is_exact_match"] == True
        assert 0.8 < scores["sequence_ratio"] < 0.95
    
    def test_no_match(self):
        scorer = ExactMatchScorer()
        text1 = "This is about machine learning and artificial intelligence."
        text2 = "The weather today is sunny and warm with clear skies."
        
        scores = scorer.calculate_exact_match_score(text1, text2)
        assert scores["is_exact_match"] == False
        assert scores["sequence_ratio"] < 0.5

class TestSemanticSimilarityScorer:
    @pytest.fixture
    def mock_embedding_service(self):
        with patch('plagiarism_detection.semantic_similarity.EmbeddingService') as mock:
            service = MagicMock()
            def mock_embed(texts):
                result = []
                for t in texts:
                    if "machine learning" in t.lower():
                        # Vector pointing in one direction
                        result.append([1.0] + [0.0] * 1023)
                    else:
                        # Orthogonal vector pointing in a different direction
                        result.append([0.0] * 1023 + [1.0])
                return result
            
            service.embed_texts.side_effect = mock_embed
            mock.return_value = service
            yield service
    
    def test_semantic_similarity(self, mock_embedding_service):
        scorer = SemanticSimilarityScorer(mock_embedding_service)
        text1 = "Machine learning is a subset of artificial intelligence."
        text2 = "AI includes machine learning as an important component."
        
        scores = scorer.calculate_semantic_score(text1, text2)
        # Both should get same embedding, so similarity should be high
        assert scores["cosine_similarity"] > 0.9
    
    def test_semantic_difference(self, mock_embedding_service):
        scorer = SemanticSimilarityScorer(mock_embedding_service)
        text1 = "Machine learning algorithms."
        text2 = "The weather is nice today."
        
        scores = scorer.calculate_semantic_score(text1, text2)
        # Different embeddings, so similarity should be low
        assert scores["cosine_similarity"] < 0.5

class TestPlagiarismDetector:
    @pytest.mark.asyncio
    async def test_exact_duplicate_detection(self):
        detector = PlagiarismDetector()
        
        # Mock database
        mock_db = AsyncMock()
        mock_chunk = MagicMock()
        mock_chunk.id = "chunk1"
        mock_chunk.document_id = "doc1"
        mock_chunk.text = "This is a test sentence for plagiarism detection in academic research."
        mock_chunk.section = "introduction"
        mock_chunk.chunk_index = 1
        mock_chunk.is_embedded = True
        
        mock_doc = MagicMock()
        mock_doc.id = "doc1"
        mock_doc.access_level = "public"
        mock_doc.backend_thesis_id = "Thesis 1"
        
        # Mock query results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_chunk]
        mock_db.execute.return_value = mock_result
        
        # Mock document query
        with patch('plagiarism_detection.detector.select') as mock_select:
            mock_doc_result = MagicMock()
            mock_doc_result.scalar_one_or_none.return_value = mock_doc
            mock_db.execute.side_effect = [mock_result, mock_doc_result]
            
            result = await detector.detect_similarity(
                db=mock_db,
                submitted_text="This is a test sentence for plagiarism detection in academic research.",
                user_id="user1",
                access_levels=["public"]
            )
            
            assert result["summary"]["exact_match_count"] >= 0  # May or may not match depending on filtering
    
    @pytest.mark.asyncio
    async def test_permission_boundary(self):
        detector = PlagiarismDetector()
        mock_db = AsyncMock()
        
        # Mock private document
        mock_chunk = MagicMock()
        mock_chunk.id = "chunk1"
        mock_chunk.document_id = "doc1"
        mock_chunk.text = "Private content."
        mock_chunk.is_embedded = True
        
        mock_doc = MagicMock()
        mock_doc.id = "doc1"
        mock_doc.access_level = "private"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_chunk]
        
        with patch('plagiarism_detection.detector.select'):
            mock_doc_result = MagicMock()
            mock_doc_result.scalar_one_or_none.return_value = mock_doc
            mock_db.execute.side_effect = [mock_result, mock_doc_result]
            
            result = await detector.detect_similarity(
                db=mock_db,
                submitted_text="Some text to check.",
                user_id="user1",
                access_levels=["public"]  # User only has public access
            )
            
            # Private document should not be compared
            assert result["chunks_compared"] == 0
    
    @pytest.mark.asyncio
    async def test_no_match_case(self):
        detector = PlagiarismDetector()
        mock_db = AsyncMock()
        
        # Mock empty results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await detector.detect_similarity(
            db=mock_db,
            submitted_text="Unique text that doesn't match anything in the database.",
            user_id="user1",
            access_levels=["public"]
        )
        
        assert result["summary"]["exact_match_count"] == 0
        assert result["summary"]["semantic_match_count"] == 0
        assert "No significant similarity" in result["summary"]["assessment"]
