-- Run this against your PostgreSQL database
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    page INTEGER,
    section TEXT,
    chunk_index INTEGER,
    source TEXT,
    processing_version TEXT,
    text TEXT NOT NULL,
    token_count INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_vector ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100); -- For later pgvector integration
