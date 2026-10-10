import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum as SAEnum, Boolean
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector
import enum

Base = declarative_base()

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"

class AIDocument(Base):
    __tablename__ = "ai_documents"
    __table_args__ = {"schema": "ai_intelligence"}
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    backend_thesis_id = Column(String, nullable=False, unique=True, index=True)
    backend_user_id = Column(String, nullable=False, index=True)
    object_key = Column(String, nullable=False)
    file_hash = Column(String)
    access_level = Column(String, default="private")
    embedding_status = Column(String, default="pending") # 'pending', 'processing', 'completed', 'failed'
    created_at = Column(DateTime, default=datetime.utcnow)

class AIJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = {"schema": "ai_intelligence"}
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("ai_intelligence.ai_documents.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String, default="extraction")
    status = Column(SAEnum(JobStatus), default=JobStatus.PENDING)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    error_message = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AIChunk(Base):
    __tablename__ = "ai_chunks"
    __table_args__ = {"schema": "ai_intelligence"}
    
    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("ai_intelligence.ai_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    section = Column(String)
    chunk_index = Column(Integer)
    text = Column(Text, nullable=False)
    token_count = Column(Integer)
    is_embedded = Column(Boolean, default=False)
    embedding_model = Column(String) # Track which model generated this embedding
    embedding_version = Column(String) # Track model version for invalidation
    vector = Column(Vector(1024)) # pgvector column for 1024-dim embeddings