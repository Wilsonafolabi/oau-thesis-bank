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