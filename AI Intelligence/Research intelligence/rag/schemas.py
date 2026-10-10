from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

class VerificationStatus(str, Enum):
    GROUNDED = "grounded"           # Fully supported by retrieved evidence
    PARTIAL = "partial"             # Some claims supported, some inferred
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # Not enough evidence
    UNVERIFIABLE = "unverifiable"   # Cannot verify claims

class Citation(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    section: str
    page_number: int
    chunk_index: int
    relevance_score: float
    excerpt: str

class RAGRequest(BaseModel):
    request_id: str
    question: str
    user_id: str
    access_levels: List[str] = Field(default=["public"])
    conversation_id: Optional[str] = None
    max_context_chunks: int = Field(default=10, ge=1, le=50)
    max_tokens: int = Field(default=1024, ge=100, le=4096)

class RAGResponse(BaseModel):
    request_id: str
    answer: str
    citations: List[Citation]
    verification_status: VerificationStatus
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)