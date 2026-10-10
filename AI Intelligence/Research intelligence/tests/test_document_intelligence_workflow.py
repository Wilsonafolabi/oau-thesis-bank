import pytest, os, io, json, asyncio
from unittest.mock import AsyncMock, patch
from pathlib import Path
import fitz
from PIL import Image, ImageDraw

from document_processing.pipeline import DocumentProcessingPipeline
from document_processing.storage.file_store import FileStore
from document_processing.models import ProcessingResult

TEST_DIR = Path("test_artifacts")
TEST_DIR.mkdir(exist_ok=True)

def create_digital_pdf(path, text="This is a digital thesis about machine learning."):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.save(path)
    doc.close()

def create_scanned_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    img = Image.new('RGB', (800, 1000), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Scanned thesis page about agriculture.", fill='black')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    page.insert_image(fitz.Rect(72, 72, 500, 700), stream=img_bytes.read())
    doc.save(path)
    doc.close()

@pytest.fixture
def pipeline():
    with patch('document_processing.pipeline.ChunkRepository') as MockRepo:
        mock_repo_instance = AsyncMock()
        MockRepo.return_value = mock_repo_instance
        p = DocumentProcessingPipeline(db_dsn="mock://db")
        p.repo = mock_repo_instance
        yield p

@pytest.mark.asyncio
async def test_digital_pdf_extraction(pipeline):
    path = str(TEST_DIR / "digital.pdf")
    create_digital_pdf(path)
    res = await pipeline.process("job1", "doc1", path)
    assert res.status == "success"
    assert res.total_pages == 1
    assert res.ocr_pages == 0
    assert res.chunks_generated > 0

@pytest.mark.asyncio
async def test_scanned_pdf_ocr_fallback(pipeline):
    path = str(TEST_DIR / "scanned.pdf")
    create_scanned_pdf(path)
    res = await pipeline.process("job2", "doc2", path)
    assert res.status == "success"
    assert res.ocr_pages == 1

@pytest.mark.asyncio
async def test_yoruba_diacritics_preserved(pipeline):
    yoruba_text = "Àkòyàbà: Ìwádìí yìí dá lórí ẹ̀kọ́ Yorùbá."
    # Mock the parser to bypass PyMuPDF font rendering limitations in test PDFs
    with patch.object(pipeline.parser, 'extract', return_value=([yoruba_text], [])):
        path = str(TEST_DIR / "dummy.pdf")
        create_digital_pdf(path, "dummy")
        res = await pipeline.process("job3", "doc3", path)
        assert res.status == "success"
        saved_chunks = pipeline.repo.save_chunks.call_args[0][0]
        text = " ".join([c.text for c in saved_chunks])
        assert "Àkòyàbà" in text and "Yorùbá" in text

@pytest.mark.asyncio
async def test_empty_pdf(pipeline):
    path = str(TEST_DIR / "empty.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    res = await pipeline.process("job4", "doc4", path)
    assert res.status == "success"
    assert res.chunks_generated == 0

@pytest.mark.asyncio
async def test_corrupted_file(pipeline):
    path = str(TEST_DIR / "corrupted.pdf")
    with open(path, "wb") as f: f.write(b"not a pdf")
    with pytest.raises(Exception):
        await pipeline.process("job5", "doc5", path)

@pytest.mark.asyncio
async def test_path_traversal_prevention(pipeline):
    with pytest.raises(ValueError, match="Path traversal detected"):
        await pipeline.process("job6", "doc6", "../../../etc/passwd")

@pytest.mark.asyncio
async def test_duplicate_upload_dedup(pipeline):
    path = str(TEST_DIR / "dup.pdf")
    create_digital_pdf(path)
    store = FileStore(base_dir=str(TEST_DIR / "storage"))
    p1, h1 = store.validate_and_store(path)
    p2, h2 = store.validate_and_store(path)
    assert h1 == h2
    assert p1 == p2