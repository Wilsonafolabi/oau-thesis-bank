import asyncio
import os
import logging
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import AIChunk, AIDocument
from embeddings.service import EmbeddingService

logger = logging.getLogger(__name__)

class EmbeddingIndexer:
    """Handles batched embedding generation and persistence for document chunks"""
    
    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()
        self.batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
    
    async def index_document(self, document_id: str, db: AsyncSession) -> dict:
        """
        Generate and persist embeddings for all chunks of a document.
        
        Args:
            document_id: The document ID to index
            db: Async SQLAlchemy session
        
        Returns:
            Dict with indexing statistics
        
        Raises:
            ValueError: If document not found
            RuntimeError: If embedding generation fails
        """
        # Update document status to processing
        await db.execute(
            update(AIDocument)
            .where(AIDocument.id == document_id)
            .values(embedding_status="processing")
        )
        await db.commit()
        
        try:
            # Fetch all unembedded chunks for this document
            result = await db.execute(
                select(AIChunk).where(
                    AIChunk.document_id == document_id,
                    AIChunk.is_embedded == False
                )
            )
            chunks = result.scalars().all()
            
            if not chunks:
                logger.info(f"No unembedded chunks found for document {document_id}")
                await db.execute(
                    update(AIDocument)
                    .where(AIDocument.id == document_id)
                    .values(embedding_status="completed")
                )
                await db.commit()
                return {"indexed": 0, "skipped": 0, "failed": 0}
            
            logger.info(f"Indexing {len(chunks)} chunks for document {document_id}")
            
            # Extract texts
            texts = [chunk.text for chunk in chunks]
            
            # Generate embeddings
            embeddings = self.embedding_service.embed_texts(
                texts, 
                batch_size=self.batch_size,
                normalize=True
            )
            
            # Update chunks with embeddings
            indexed_count = 0
            for chunk, embedding in zip(chunks, embeddings):
                chunk.vector = embedding
                chunk.is_embedded = True
                chunk.embedding_model = self.embedding_service.model_name
                chunk.embedding_version = self.embedding_service.model_version
                indexed_count += 1
            
            await db.commit()
            
            # Update document status to completed
            await db.execute(
                update(AIDocument)
                .where(AIDocument.id == document_id)
                .values(embedding_status="completed")
            )
            await db.commit()
            
            logger.info(f"Successfully indexed {indexed_count} chunks for document {document_id}")
            return {"indexed": indexed_count, "skipped": 0, "failed": 0}
            
        except Exception as e:
            logger.error(f"Failed to index document {document_id}: {e}")
            # Update document status to failed
            await db.execute(
                update(AIDocument)
                .where(AIDocument.id == document_id)
                .values(embedding_status="failed")
            )
            await db.commit()
            raise
    
    async def invalidate_document(self, document_id: str, db: AsyncSession) -> int:
        """
        Remove embeddings for a document (e.g., when document is updated or deleted).
        
        Args:
            document_id: The document ID to invalidate
            db: Async SQLAlchemy session
        
        Returns:
            Number of chunks invalidated
        """
        result = await db.execute(
            select(AIChunk).where(AIChunk.document_id == document_id)
        )
        chunks = result.scalars().all()
        
        invalidated_count = 0
        for chunk in chunks:
            if chunk.is_embedded:
                chunk.vector = None
                chunk.is_embedded = False
                chunk.embedding_model = None
                chunk.embedding_version = None
                invalidated_count += 1
        
        await db.execute(
            update(AIDocument)
            .where(AIDocument.id == document_id)
            .values(embedding_status="pending")
        )
        await db.commit()
        
        logger.info(f"Invalidated {invalidated_count} chunks for document {document_id}")
        return invalidated_count
