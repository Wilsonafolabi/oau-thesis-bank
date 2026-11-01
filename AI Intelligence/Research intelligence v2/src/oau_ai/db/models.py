"""SQLAlchemy ORM models for Phase 3 V2 persistent data.

Tables live in the `ai_intelligence` schema, matching the V1 reference:
- ai_documents: document records (canonical text + provenance stored here)
- ai_pages: extracted page-level text
- ai_chunks: chunk records with provenance and Vectorize point mapping
- ai_jobs: ingestion job state machine

Canonical chunk text and provenance live in PostgreSQL. Vectorize stores only
embeddings and retrieval metadata (point_id -> chunk_id mapping).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    Enum as SAEnum,
    Boolean,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class ProcessingStage(str, enum.Enum):
    EXTRACTION = "extraction"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    VECTORIZE = "vectorize"
    COMPLETE = "complete"
    FAILED = "failed"


class AIDocument(Base):
    """Document record — canonical metadata and access control."""

    __tablename__ = "ai_documents"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    backend_thesis_id = Column(String, nullable=False, unique=True, index=True)
    backend_user_id = Column(String, nullable=False, index=True)
    object_key = Column(String, nullable=False)
    file_hash = Column(String, nullable=True)
    access_level = Column(String, nullable=False, default="private")
    embedding_status = Column(
        String,
        nullable=False,
        default="pending",
    )
    thesis_metadata = Column(JSON, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    pages = relationship(
        "AIPage",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    chunks = relationship(
        "AIChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    jobs = relationship(
        "AIJob",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AIPage(Base):
    """Extracted page-level text with page-level provenance."""

    __tablename__ = "ai_pages"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    document_id = Column(
        String,
        ForeignKey(
            "ai_intelligence.ai_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    page_number = Column(Integer, nullable=False)
    is_scanned = Column(Boolean, nullable=False, default=False)
    text_content = Column(Text, nullable=True)
    char_offset_start = Column(Integer, nullable=True)
    char_offset_end = Column(Integer, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    document = relationship("AIDocument", back_populates="pages")
    chunks = relationship(
        "AIChunk",
        back_populates="page",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_ai_pages_document_page", "document_id", "page_number", unique=True),
        {"schema": "ai_intelligence"},
    )


class AIChunk(Base):
    """Chunk record — canonical text + provenance + Vectorize point mapping."""

    __tablename__ = "ai_chunks"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    document_id = Column(
        String,
        ForeignKey(
            "ai_intelligence.ai_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    page_id = Column(
        String,
        ForeignKey(
            "ai_intelligence.ai_pages.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    # Vectorize point ID that maps back to this chunk.
    vectorize_point_id = Column(String, nullable=True, unique=True)
    embedding_model = Column(String, nullable=True)
    embedding_version = Column(String, nullable=True)
    is_embedded = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    document = relationship("AIDocument", back_populates="chunks")
    page = relationship("AIPage", back_populates="chunks")


class AIJob(Base):
    """Ingestion job state machine."""

    __tablename__ = "ai_jobs"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    document_id = Column(
        String,
        ForeignKey(
            "ai_intelligence.ai_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    job_type = Column(String, nullable=False, default="document_ingestion")
    stage = Column(
        SAEnum(
            ProcessingStage,
            name="ai_job_stage",
            schema="ai_intelligence",
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=ProcessingStage.EXTRACTION,
    )
    status = Column(
        SAEnum(
            JobStatus,
            name="ai_job_status",
            schema="ai_intelligence",
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=JobStatus.PENDING,
    )
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)
    error_stage = Column(String, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    document = relationship("AIDocument", back_populates="jobs")


class MemoryType(str, enum.Enum):
    """Type of memory entry."""

    PROFILE = "profile"
    DOCUMENT_SUMMARY = "document_summary"
    RESEARCH_INTEREST = "research_interest"
    RESEARCH_OBJECTIVE = "research_objective"
    METHODOLOGY_PREFERENCE = "methodology_preference"
    WORKING_EXCHANGE = "working_exchange"
    ENTITY = "entity"
    SUPERVISOR_INFO = "supervisor_info"


class MemorySource(str, enum.Enum):
    """Source of the memory entry."""

    AUTHOR_STATED = "author_stated"
    SYSTEM_INFERRED = "system_inferred"
    EXTRACTED_FROM_CONVERSATION = "extracted_from_conversation"
    EXTRACTED_FROM_DOCUMENT = "extracted_from_document"


class ResearcherMemory(Base):
    """Persistent researcher memory — scoped to owner user_id.

    Stores stable research context: interests, objectives, methodologies,
    preferences, and other researcher-specific facts. Each entry is owned by
    a single researcher and cannot be accessed by others.
    """

    __tablename__ = "researcher_memories"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(String, nullable=False, index=True)
    memory_type = Column(
        SAEnum(
            MemoryType,
            name="ai_memory_type",
            schema="ai_intelligence",
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
    )
    source = Column(
        SAEnum(
            MemorySource,
            name="ai_memory_source",
            schema="ai_intelligence",
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
    )
    key = Column(String, nullable=False, index=True)
    value = Column(Text, nullable=False)
    confidence = Column(String, nullable=False, default="0.5")
    is_archived = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    source_document_id = Column(String, nullable=True, index=True)
    source_chunk_id = Column(String, nullable=True)
    provenance = Column(JSON, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_researcher_memories_user_type", "user_id", "memory_type"),
        Index("ix_researcher_memories_user_key", "user_id", "key"),
        {"schema": "ai_intelligence"},
    )


class MemoryEntity(Base):
    """Extracted entity — research topics, researchers, institutions, etc.

    Entities are linked to memories and support relationship tracking.
    Scoped to owner user_id for isolation.
    """

    __tablename__ = "memory_entities"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False)  # topic, researcher, institution, supervisor, department
    entity_name = Column(String, nullable=False, index=True)
    normalized_name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    confidence = Column(String, nullable=False, default="0.5")
    first_seen_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    last_seen_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    occurrence_count = Column(Integer, nullable=False, default=1)
    provenance = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_memory_entities_user_type", "user_id", "entity_type"),
        Index("ix_memory_entities_user_normalized", "user_id", "normalized_name"),
        {"schema": "ai_intelligence"},
    )


class MemoryRelationship(Base):
    """Relationship between two memory entities.

    Tracks how entities relate to each other (e.g., researcher supervises,
    institution employs, topic relates to).
    """

    __tablename__ = "memory_relationships"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(String, nullable=False, index=True)
    source_entity_id = Column(
        String,
        ForeignKey(
            "ai_intelligence.memory_entities.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    target_entity_id = Column(
        String,
        ForeignKey(
            "ai_intelligence.memory_entities.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    relationship_type = Column(String, nullable=False)
    confidence = Column(String, nullable=False, default="0.5")
    provenance = Column(JSON, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_memory_relationships_user", "user_id"),
        Index("ix_memory_relationships_source", "source_entity_id"),
        Index("ix_memory_relationships_target", "target_entity_id"),
        {"schema": "ai_intelligence"},
    )


class ThesisSummary(Base):
    """Compact structured summary of an uploaded thesis.

    Reused across conversations instead of reprocessing entire documents.
    Linked to the original document record for provenance.
    """

    __tablename__ = "thesis_summaries"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    document_id = Column(
        String,
        ForeignKey(
            "ai_intelligence.ai_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    backend_thesis_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    abstract_summary = Column(Text, nullable=True)
    research_questions = Column(JSON, nullable=True)
    objectives = Column(JSON, nullable=True)
    methodology = Column(Text, nullable=True)
    findings = Column(JSON, nullable=True)
    limitations = Column(JSON, nullable=True)
    key_entities = Column(JSON, nullable=True)
    word_count = Column(Integer, nullable=True)
    confidence = Column(String, nullable=False, default="0.5")
    source_hash = Column(Text, nullable=True)
    source_version = Column(String, nullable=True)
    generated_at = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    # NULL marks the current version; a superseded row points at its successor.
    superseded_by = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_thesis_summaries_user", "user_id"),
        Index("ix_thesis_summaries_thesis", "backend_thesis_id"),
        {"schema": "ai_intelligence"},
    )


class WorkingMemoryExchange(Base):
    """Rolling window of conversation exchanges per researcher.

    Last 5 exchanges are kept verbatim; older exchanges are summarized.
    Preserves unresolved questions, decisions, and current research tasks.
    """

    __tablename__ = "working_memory_exchanges"
    __table_args__ = {"schema": "ai_intelligence"}

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(String, nullable=False, index=True)
    exchange_type = Column(String, nullable=False)  # user_message, assistant_response, summary
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    unresolved_questions = Column(JSON, nullable=True)
    decisions = Column(JSON, nullable=True)
    current_tasks = Column(JSON, nullable=True)
    is_summarized = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_working_memory_user_created", "user_id", "created_at"),
        {"schema": "ai_intelligence"},
    )
