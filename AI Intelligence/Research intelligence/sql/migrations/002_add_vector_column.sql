-- Migration: Add pgvector support to ai_chunks table
-- Run this after 001_document_intelligence.sql

-- Add vector column (1024 dimensions for BAAI/bge-large-en-v1.5)
ALTER TABLE ai_intelligence.ai_chunks 
ADD COLUMN IF NOT EXISTS vector vector(1024);

-- Add embedding metadata columns
ALTER TABLE ai_intelligence.ai_chunks 
ADD COLUMN IF NOT EXISTS embedding_model TEXT,
ADD COLUMN IF NOT EXISTS embedding_version TEXT;

-- Create HNSW index for fast cosine similarity search
-- HNSW is preferred over IVFFlat for datasets < 1M vectors
CREATE INDEX IF NOT EXISTS idx_ai_chunks_vector_hnsw 
ON ai_intelligence.ai_chunks 
USING hnsw (vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Note: HNSW parameters can be tuned based on dataset size:
-- m: Number of connections per layer (16 is good default)
-- ef_construction: Size of dynamic candidate list during index build (64 is good default)
-- For larger datasets (>100k vectors), consider increasing ef_construction to 128-256