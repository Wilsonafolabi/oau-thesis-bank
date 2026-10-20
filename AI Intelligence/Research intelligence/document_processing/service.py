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