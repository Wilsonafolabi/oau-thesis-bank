from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    result: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: Optional[str] = None

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)

class RAGRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=1000)
    document_ids: Optional[List[str]] = None

class DocumentUploadResponse(BaseModel):
    document_id: str
    job_id: str
    status: JobStatus
