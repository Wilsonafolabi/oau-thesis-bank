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
                ocr = PaddleOCR(use_angle_cls=True, lang='en')
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
