from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Provenance(BaseModel):
    document_id: str
    source_file: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    chunk_id: Optional[str] = None
    char_offset_start: Optional[int] = None
    char_offset_end: Optional[int] = None
    access_classification: str = "public"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model_version: Optional[str] = None

class Document(BaseModel):
    id: str
    title: str
    source_file: str
    file_hash: str
    total_pages: int
    access_classification: str
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DocumentPage(BaseModel):
    document_id: str
    page_number: int
    is_scanned: bool
    text_content: str
    image_path: Optional[str] = None
    ocr_confidence: Optional[float] = None
    extraction_method: str
    provenance: Provenance

class Section(BaseModel):
    document_id: str
    section_id: str
    title: str
    level: int
    start_page: int
    end_page: int
    provenance: Provenance

class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    section_id: Optional[str]
    text: str
    token_count: int
    overlap_count: int
    provenance: Provenance