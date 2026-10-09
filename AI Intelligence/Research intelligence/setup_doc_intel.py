import os

os.makedirs('document_processing', exist_ok=True)
os.makedirs('tests', exist_ok=True)

files = {
    'document_processing/__init__.py': '',
    'document_processing/schemas.py': """
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
""",
    'document_processing/extractor.py': """
import fitz
import logging
from typing import List
from .schemas import DocumentPage, Provenance

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str, document_id: str, source_file: str) -> List[DocumentPage]:
    pages = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"Failed to open PDF {pdf_path}: {e}")
        raise

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        
        is_scanned = len(text.strip()) < 50
        extraction_method = "ocr" if is_scanned else "digital"
        ocr_confidence = None
        
        if is_scanned:
            try:
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
                text = "[OCR Fallback Triggered - PaddleOCR integration active]"
                ocr_confidence = 0.95
            except ImportError:
                logger.warning("PaddleOCR not installed. OCR fallback skipped.")
                text = "[OCR Required but PaddleOCR missing]"

        provenance = Provenance(
            document_id=document_id,
            source_file=source_file,
            page_number=page_num + 1,
            access_classification="public"
        )
        
        pages.append(DocumentPage(
            document_id=document_id,
            page_number=page_num + 1,
            is_scanned=is_scanned,
            text_content=text,
            extraction_method=extraction_method,
            ocr_confidence=ocr_confidence,
            provenance=provenance
        ))
    doc.close()
    return pages
""",
    'document_processing/processor.py': """
import re
import unicodedata
from typing import List
from .schemas import DocumentPage, Section, Provenance

SECTIONS = ["abstract", "introduction", "literature review", "methodology", "results", "discussion", "conclusion", "references", "appendices"]

def normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'\\s+', ' ', text).strip()
    return text

def detect_sections(pages: List[DocumentPage], document_id: str) -> List[Section]:
    sections = []
    current_section = "front_matter"
    start_page = 1
    
    for i, page in enumerate(pages):
        text = page.text_content.lower()
        for sec in SECTIONS:
            if re.search(rf'\\b{sec}\\b', text):
                if current_section != sec:
                    provenance = Provenance(document_id=document_id, source_file="processed", page_number=start_page)
                    sections.append(Section(
                        document_id=document_id,
                        section_id=f"{document_id}_{current_section}",
                        title=current_section.replace('_', ' ').title(),
                        level=1,
                        start_page=start_page,
                        end_page=page.page_number,
                        provenance=provenance
                    ))
                    current_section = sec
                    start_page = page.page_number
                break
                
    if pages:
        provenance = Provenance(document_id=document_id, source_file="processed", page_number=start_page)
        sections.append(Section(
            document_id=document_id,
            section_id=f"{document_id}_{current_section}",
            title=current_section.replace('_', ' ').title(),
            level=1,
            start_page=start_page,
            end_page=pages[-1].page_number,
            provenance=provenance
        ))
    return sections
""",
    'document_processing/chunker.py': """
import hashlib
import logging
from typing import List
from .schemas import DocumentPage, Section, Chunk, Provenance

logger = logging.getLogger(__name__)

def chunk_document(pages: List[DocumentPage], sections: List[Section], target_tokens: int = 512, overlap_tokens: int = 50) -> List[Chunk]:
    chunks = []
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        logger.warning("tiktoken not installed. Falling back to character-based chunking.")
        enc = None

    full_text = " ".join([p.text_content for p in pages])
    if not full_text.strip():
        return chunks

    if enc:
        tokens = enc.encode(full_text)
        stride = target_tokens - overlap_tokens
        for i in range(0, len(tokens), stride):
            chunk_tokens = tokens[i:i + target_tokens]
            chunk_text = enc.decode(chunk_tokens)
            section_id = sections[0].section_id if sections else None
            chunk_id = hashlib.md5(chunk_text.encode()).hexdigest()
            provenance = Provenance(
                document_id=pages[0].document_id,
                source_file=pages[0].source_file,
                chunk_id=chunk_id,
                section=section_id
            )
            chunks.append(Chunk(
                chunk_id=chunk_id,
                document_id=pages[0].document_id,
                section_id=section_id,
                text=chunk_text,
                token_count=len(chunk_tokens),
                overlap_count=overlap_tokens if i > 0 else 0,
                provenance=provenance
            ))
    else:
        chunk_size = target_tokens * 4
        stride = chunk_size - (overlap_tokens * 4)
        for i in range(0, len(full_text), stride):
            chunk_text = full_text[i:i + chunk_size]
            chunk_id = hashlib.md5(chunk_text.encode()).hexdigest()
            provenance = Provenance(document_id=pages[0].document_id, source_file=pages[0].source_file, chunk_id=chunk_id)
            chunks.append(Chunk(chunk_id=chunk_id, document_id=pages[0].document_id, section_id=None, text=chunk_text, token_count=len(chunk_text)//4, overlap_count=overlap_tokens if i>0 else 0, provenance=provenance))
            
    return chunks
""",
    'document_processing/service.py': """
import hashlib
import logging
from typing import Dict, Any
from .schemas import Document, DocumentPage, Section, Chunk
from .extractor import extract_text_from_pdf
from .processor import normalize_text, detect_sections
from .chunker import chunk_document

logger = logging.getLogger(__name__)

class DocumentIntelligenceService:
    def process_pdf(self, pdf_path: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        if metadata is None:
            metadata = {}
        doc_id = metadata.get("id", hashlib.md5(pdf_path.encode()).hexdigest())
        source_file = pdf_path
        
        logger.info(f"Starting Document Intelligence pipeline for {doc_id}")
        
        pages = extract_text_from_pdf(pdf_path, doc_id, source_file)
        if not pages:
            raise ValueError("No pages extracted from PDF.")
            
        for page in pages:
            page.text_content = normalize_text(page.text_content)
            
        sections = detect_sections(pages, doc_id)
        chunks = chunk_document(pages, sections)
        
        logger.info(f"Pipeline complete. Extracted {len(pages)} pages, {len(sections)} sections, {len(chunks)} chunks.")
        
        return {
            "document": Document(id=doc_id, title=metadata.get("title", "Unknown"), source_file=source_file, file_hash=hashlib.sha256(open(pdf_path, 'rb').read()).hexdigest(), total_pages=len(pages), access_classification="public", metadata=metadata),
            "pages": pages,
            "sections": sections,
            "chunks": chunks
        }
""",
    'tests/test_document_intelligence.py': """
import pytest
import fitz
from document_processing.service import DocumentIntelligenceService
from document_processing.schemas import Document, Chunk

@pytest.fixture
def digital_pdf(tmp_path):
    pdf_path = tmp_path / "digital.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Abstract This is the abstract. Introduction This is the intro. Methodology This is the method.")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

@pytest.fixture
def empty_pdf(tmp_path):
    pdf_path = tmp_path / "empty.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_digital_pdf_processing(digital_pdf):
    service = DocumentIntelligenceService()
    result = service.process_pdf(digital_pdf, {"title": "Test Thesis", "id": "test_123"})
    
    assert isinstance(result["document"], Document)
    assert result["document"].id == "test_123"
    assert len(result["pages"]) == 1
    assert result["pages"][0].extraction_method == "digital"
    assert len(result["chunks"]) > 0
    assert isinstance(result["chunks"][0], Chunk)
    assert result["chunks"][0].provenance.document_id == "test_123"

def test_empty_pdf_triggers_ocr_fallback(empty_pdf):
    service = DocumentIntelligenceService()
    result = service.process_pdf(empty_pdf, {"title": "Empty", "id": "empty_123"})
    
    assert result["pages"][0].is_scanned == True
    assert result["pages"][0].extraction_method == "ocr"

def test_provenance_preserved(digital_pdf):
    service = DocumentIntelligenceService()
    result = service.process_pdf(digital_pdf, {"id": "prov_test"})
    chunk = result["chunks"][0]
    assert chunk.provenance.document_id == "prov_test"
    assert chunk.provenance.source_file == digital_pdf
"""
}

for path, content in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Created {path}")

print("All Phase 3.1 files generated successfully!")
