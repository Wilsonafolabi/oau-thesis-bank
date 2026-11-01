-- Phase 3 V2 migration: 001_initial_schema.sql
-- Creates the ai_intelligence schema and all Phase 3 V2 tables:
--   ai_documents, ai_pages, ai_chunks, ai_jobs,
--   researcher_memories, memory_entities, memory_relationships,
--   thesis_summaries, working_memory_exchanges.
--
-- Run against the PostgreSQL database configured by RI_DATABASE_URL.
-- Requires the pgvector extension for vector columns (used by V1 reference;
-- V2 uses Cloudflare Vectorize instead, but pgvector may be needed for
-- hybrid search in future stages).
--
-- Safe to rerun: all statements use IF NOT EXISTS or guard on data_type.

-- Create the schema FIRST so enum types and tables can reference it.
CREATE SCHEMA IF NOT EXISTS ai_intelligence;

-- gen_random_uuid() is built into PostgreSQL 13+; pgcrypto covers older versions.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- Create enum types BEFORE tables that reference them.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'ai_intelligence' AND t.typname = 'ai_job_stage'
    ) THEN
        CREATE TYPE ai_intelligence.ai_job_stage AS ENUM (
            'extraction', 'chunking', 'embedding', 'vectorize', 'complete', 'failed'
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'ai_intelligence' AND t.typname = 'ai_job_status'
    ) THEN
        CREATE TYPE ai_intelligence.ai_job_status AS ENUM (
            'pending', 'processing', 'success', 'failed'
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'ai_intelligence' AND t.typname = 'ai_memory_type'
    ) THEN
        CREATE TYPE ai_intelligence.ai_memory_type AS ENUM (
            'profile', 'document_summary', 'research_interest',
            'research_objective', 'methodology_preference',
            'working_exchange', 'entity', 'supervisor_info'
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'ai_intelligence' AND t.typname = 'ai_memory_source'
    ) THEN
        CREATE TYPE ai_intelligence.ai_memory_source AS ENUM (
            'author_stated', 'system_inferred',
            'extracted_from_conversation', 'extracted_from_document'
        );
    END IF;
END $$;

-- ===== ai_documents =====
CREATE TABLE IF NOT EXISTS ai_intelligence.ai_documents (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    backend_thesis_id VARCHAR NOT NULL UNIQUE,
    backend_user_id VARCHAR NOT NULL,
    object_key VARCHAR NOT NULL,
    file_hash VARCHAR,
    access_level VARCHAR NOT NULL DEFAULT 'private',
    embedding_status VARCHAR NOT NULL DEFAULT 'pending',
    thesis_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ai_documents_backend_thesis_id
    ON ai_intelligence.ai_documents (backend_thesis_id);
CREATE INDEX IF NOT EXISTS ix_ai_documents_backend_user_id
    ON ai_intelligence.ai_documents (backend_user_id);
CREATE INDEX IF NOT EXISTS ix_ai_documents_access_level
    ON ai_intelligence.ai_documents (access_level);

-- ===== ai_pages =====
CREATE TABLE IF NOT EXISTS ai_intelligence.ai_pages (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    document_id VARCHAR NOT NULL
        REFERENCES ai_intelligence.ai_documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    is_scanned BOOLEAN NOT NULL DEFAULT FALSE,
    text_content TEXT,
    char_offset_start INTEGER,
    char_offset_end INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_pages_document_page
    ON ai_intelligence.ai_pages (document_id, page_number);
CREATE INDEX IF NOT EXISTS ix_ai_pages_document_id
    ON ai_intelligence.ai_pages (document_id);

-- ===== ai_chunks =====
CREATE TABLE IF NOT EXISTS ai_intelligence.ai_chunks (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    document_id VARCHAR NOT NULL
        REFERENCES ai_intelligence.ai_documents(id) ON DELETE CASCADE,
    page_id VARCHAR
        REFERENCES ai_intelligence.ai_pages(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER,
    vectorize_point_id VARCHAR UNIQUE,
    embedding_model VARCHAR,
    embedding_version VARCHAR,
    is_embedded BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ai_chunks_document_id
    ON ai_intelligence.ai_chunks (document_id);
CREATE INDEX IF NOT EXISTS ix_ai_chunks_page_id
    ON ai_intelligence.ai_chunks (page_id);
CREATE INDEX IF NOT EXISTS ix_ai_chunks_vectorize_point_id
    ON ai_intelligence.ai_chunks (vectorize_point_id);

-- ===== ai_jobs =====
CREATE TABLE IF NOT EXISTS ai_intelligence.ai_jobs (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    document_id VARCHAR NOT NULL
        REFERENCES ai_intelligence.ai_documents(id) ON DELETE CASCADE,
    job_type VARCHAR NOT NULL DEFAULT 'document_ingestion',
    stage ai_intelligence.ai_job_stage NOT NULL DEFAULT 'extraction'::ai_intelligence.ai_job_stage,
    status ai_intelligence.ai_job_status NOT NULL DEFAULT 'pending'::ai_intelligence.ai_job_status,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    error_stage VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ai_jobs_document_id
    ON ai_intelligence.ai_jobs (document_id);
CREATE INDEX IF NOT EXISTS ix_ai_jobs_status
    ON ai_intelligence.ai_jobs (status);

-- ===== researcher_memories =====
CREATE TABLE IF NOT EXISTS ai_intelligence.researcher_memories (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR NOT NULL,
    memory_type ai_intelligence.ai_memory_type NOT NULL,
    source ai_intelligence.ai_memory_source NOT NULL,
    key VARCHAR NOT NULL,
    value TEXT NOT NULL,
    confidence VARCHAR NOT NULL DEFAULT '0.5',
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    archived_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    source_document_id VARCHAR,
    source_chunk_id VARCHAR,
    provenance JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_researcher_memories_user_id
    ON ai_intelligence.researcher_memories (user_id);
CREATE INDEX IF NOT EXISTS ix_researcher_memories_user_type
    ON ai_intelligence.researcher_memories (user_id, memory_type);
CREATE INDEX IF NOT EXISTS ix_researcher_memories_user_key
    ON ai_intelligence.researcher_memories (user_id, key);
CREATE INDEX IF NOT EXISTS ix_researcher_memories_source_document_id
    ON ai_intelligence.researcher_memories (source_document_id);

-- ===== memory_entities =====
CREATE TABLE IF NOT EXISTS ai_intelligence.memory_entities (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    entity_name VARCHAR NOT NULL,
    normalized_name VARCHAR NOT NULL,
    description TEXT,
    confidence VARCHAR NOT NULL DEFAULT '0.5',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    provenance JSONB
);

CREATE INDEX IF NOT EXISTS ix_memory_entities_user_id
    ON ai_intelligence.memory_entities (user_id);
CREATE INDEX IF NOT EXISTS ix_memory_entities_user_type
    ON ai_intelligence.memory_entities (user_id, entity_type);
CREATE INDEX IF NOT EXISTS ix_memory_entities_user_normalized
    ON ai_intelligence.memory_entities (user_id, normalized_name);

-- ===== memory_relationships =====
CREATE TABLE IF NOT EXISTS ai_intelligence.memory_relationships (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR NOT NULL,
    source_entity_id VARCHAR NOT NULL
        REFERENCES ai_intelligence.memory_entities(id) ON DELETE CASCADE,
    target_entity_id VARCHAR NOT NULL
        REFERENCES ai_intelligence.memory_entities(id) ON DELETE CASCADE,
    relationship_type VARCHAR NOT NULL,
    confidence VARCHAR NOT NULL DEFAULT '0.5',
    provenance JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_memory_relationships_user
    ON ai_intelligence.memory_relationships (user_id);
CREATE INDEX IF NOT EXISTS ix_memory_relationships_source
    ON ai_intelligence.memory_relationships (source_entity_id);
CREATE INDEX IF NOT EXISTS ix_memory_relationships_target
    ON ai_intelligence.memory_relationships (target_entity_id);

-- ===== thesis_summaries =====
CREATE TABLE IF NOT EXISTS ai_intelligence.thesis_summaries (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    document_id VARCHAR NOT NULL
        REFERENCES ai_intelligence.ai_documents(id) ON DELETE CASCADE,
    backend_thesis_id VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,
    title VARCHAR,
    abstract_summary TEXT,
    research_questions JSONB,
    objectives JSONB,
    methodology TEXT,
    findings JSONB,
    limitations JSONB,
    key_entities JSONB,
    word_count INTEGER,
    confidence VARCHAR NOT NULL DEFAULT '0.5',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_thesis_summaries_document_id
    ON ai_intelligence.thesis_summaries (document_id);
CREATE INDEX IF NOT EXISTS ix_thesis_summaries_user
    ON ai_intelligence.thesis_summaries (user_id);
CREATE INDEX IF NOT EXISTS ix_thesis_summaries_thesis
    ON ai_intelligence.thesis_summaries (backend_thesis_id);

-- ===== working_memory_exchanges =====
CREATE TABLE IF NOT EXISTS ai_intelligence.working_memory_exchanges (
    id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR NOT NULL,
    exchange_type VARCHAR NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    unresolved_questions JSONB,
    decisions JSONB,
    current_tasks JSONB,
    is_summarized BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_working_memory_user_created
    ON ai_intelligence.working_memory_exchanges (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_working_memory_exchanges_user_id
    ON ai_intelligence.working_memory_exchanges (user_id);

-- Migrate existing VARCHAR stage column to enum type if present (safe for reruns).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ai_intelligence'
        AND table_name = 'ai_jobs'
        AND column_name = 'stage'
        AND data_type = 'character varying'
    ) THEN
        ALTER TABLE ai_intelligence.ai_jobs
        ALTER COLUMN stage TYPE ai_intelligence.ai_job_stage
        USING stage::ai_intelligence.ai_job_stage;
    END IF;
END $$;

-- Migrate existing VARCHAR status column to enum type if present (safe for reruns).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ai_intelligence'
        AND table_name = 'ai_jobs'
        AND column_name = 'status'
        AND data_type = 'character varying'
    ) THEN
        ALTER TABLE ai_intelligence.ai_jobs
        ALTER COLUMN status TYPE ai_intelligence.ai_job_status
        USING status::ai_intelligence.ai_job_status;
    END IF;
END $$;
