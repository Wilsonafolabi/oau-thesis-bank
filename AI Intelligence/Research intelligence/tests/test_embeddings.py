import pytest
import os
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from embeddings.service import EmbeddingService
from embeddings.indexer import EmbeddingIndexer
from db.models import AIChunk, AIDocument

class TestEmbeddingService:
    """Unit tests for embedding service (no database required)"""
    
    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer to avoid loading real model"""
        with patch('embeddings.service.SentenceTransformer') as mock_st:
            mock_model = MagicMock()
            # Return 1024-dim embeddings
            mock_model.encode.return_value = np.random.rand(2, 1024).astype(np.float32)
            mock_st.return_value = mock_model
            yield mock_model
    
    def test_embedding_dimensions(self, mock_sentence_transformer):
        """Verify embeddings have correct dimensions"""
        service = EmbeddingService()
        embeddings = service.embed_texts(["test1", "test2"])
        
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 1024
        assert len(embeddings[1]) == 1024
    
    def test_batching(self, mock_sentence_transformer):
        """Verify batching works correctly"""
        service = EmbeddingService()
        texts = [f"text_{i}" for i in range(100)]
        
        # Mock encode to track batch calls
        call_count = 0
        def mock_encode(batch, **kwargs):
            nonlocal call_count
            call_count += 1
            return np.random.rand(len(batch), 1024).astype(np.float32)
        
        mock_sentence_transformer.encode.side_effect = mock_encode
        
        embeddings = service.embed_texts(texts, batch_size=32)
        
        assert len(embeddings) == 100
        assert call_count == 4  # 100 texts / 32 batch_size = 4 batches (32+32+32+4)
    
    def test_dimension_mismatch_raises_error(self):
        """Verify dimension mismatch is caught"""
        with patch('embeddings.service.SentenceTransformer') as mock_st:
            mock_model = MagicMock()
            # Return wrong dimensions (768 instead of 1024)
            mock_model.encode.return_value = np.random.rand(1, 768).astype(np.float32)
            mock_st.return_value = mock_model
            
            with pytest.raises(ValueError, match="dimension mismatch"):
                EmbeddingService()

class TestEmbeddingIndexer:
    """Unit tests for indexer (mocked database)"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock AsyncSession"""
        db = AsyncMock(spec=AsyncSession)
        return db
    
    @pytest.fixture
    def mock_embedding_service(self):
        """Mock EmbeddingService"""
        service = MagicMock(spec=EmbeddingService)
        service.model_name = "BAAI/bge-large-en-v1.5"
        service.model_version = "stock-v1"
        service.embed_texts.return_value = [
            np.random.rand(1024).tolist() for _ in range(5)
        ]
        return service
    
    @pytest.mark.asyncio
    async def test_index_document_success(self, mock_db, mock_embedding_service):
        """Test successful document indexing"""
        # Mock chunks
        chunks = [
            AIChunk(id=f"chunk_{i}", document_id="doc_1", text=f"text_{i}", is_embedded=False)
            for i in range(5)
        ]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = chunks
        mock_db.execute.return_value = mock_result
        
        indexer = EmbeddingIndexer(embedding_service=mock_embedding_service)
        result = await indexer.index_document("doc_1", mock_db)
        
        assert result["indexed"] == 5
        assert result["failed"] == 0
        
        # Verify chunks were updated
        for chunk in chunks:
            assert chunk.is_embedded == True
            assert chunk.embedding_model == "BAAI/bge-large-en-v1.5"
            assert chunk.vector is not None
    
    @pytest.mark.asyncio
    async def test_skip_already_embedded_chunks(self, mock_db, mock_embedding_service):
        """Test that already-embedded chunks are skipped"""
        chunks = [
            AIChunk(id="chunk_1", document_id="doc_1", text="text_1", is_embedded=True),
            AIChunk(id="chunk_2", document_id="doc_1", text="text_2", is_embedded=False),
        ]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [chunks[1]]  # Only unembedded
        mock_db.execute.return_value = mock_result
        
        indexer = EmbeddingIndexer(embedding_service=mock_embedding_service)
        result = await indexer.index_document("doc_1", mock_db)
        
        assert result["indexed"] == 1
        mock_embedding_service.embed_texts.assert_called_once_with(["text_2"], batch_size=32, normalize=True)
    
    @pytest.mark.asyncio
    async def test_invalidate_document(self, mock_db, mock_embedding_service):
        """Test embedding invalidation"""
        chunks = [
            AIChunk(id="chunk_1", document_id="doc_1", is_embedded=True, vector=[0.1]*1024),
            AIChunk(id="chunk_2", document_id="doc_1", is_embedded=True, vector=[0.2]*1024),
        ]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = chunks
        mock_db.execute.return_value = mock_result
        
        indexer = EmbeddingIndexer(embedding_service=mock_embedding_service)
        count = await indexer.invalidate_document("doc_1", mock_db)
        
        assert count == 2
        for chunk in chunks:
            assert chunk.is_embedded == False
            assert chunk.vector is None
            assert chunk.embedding_model is None

class TestEmbeddingIntegration:
    """Integration tests requiring PostgreSQL with pgvector"""
    
    @pytest.mark.skipif(
        not os.getenv("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set - skipping integration tests"
    )
    @pytest.mark.asyncio
    async def test_persistence_to_pgvector(self):
        """Test actual persistence to PostgreSQL with pgvector"""
        # This test requires a real PostgreSQL database with pgvector extension
        # Set TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/test_db
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from db.models import Base
        
        engine = create_async_engine(os.getenv("TEST_DATABASE_URL"))
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        async with async_session() as session:
            # Create test document and chunk
            doc = AIDocument(id="test_doc", backend_thesis_id="thesis_1", 
                           backend_user_id="user_1", object_key="test.pdf")
            session.add(doc)
            
            chunk = AIChunk(id="test_chunk", document_id="test_doc", 
                          text="Test text", is_embedded=False)
            session.add(chunk)
            await session.commit()
            
            # Generate and persist embedding
            service = EmbeddingService()
            embedding = service.embed_texts(["Test text"])[0]
            
            chunk.vector = embedding
            chunk.is_embedded = True
            await session.commit()
            
            # Verify retrieval
            result = await session.execute(select(AIChunk).where(AIChunk.id == "test_chunk"))
            retrieved = result.scalar_one()
            
            assert retrieved.is_embedded == True
            assert retrieved.vector is not None
            assert len(retrieved.vector) == 1024
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
