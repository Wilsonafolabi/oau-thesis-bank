import time, structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .parsers.digital import DigitalParser
from .parsers.metadata import MetadataExtractor
from .ocr.engine import OCREngine
from .layout.engine import LayoutEngine
from .normalization.cleaner import TextCleaner
from .chunking.chunker import TokenChunker
from .storage.repository import ChunkRepository
from .storage.file_store import FileStore
from .models import DocumentChunk, ChunkProvenance, ProcessingResult

logger = structlog.get_logger()

class DocumentProcessingPipeline:
    def __init__(self, db_dsn: str):
        self.parser = DigitalParser()
        self.ocr = OCREngine()
        self.layout = LayoutEngine()
        self.cleaner = TextCleaner()
        self.chunker = TokenChunker()
        self.repo = ChunkRepository(db_dsn)
        self.file_store = FileStore()
        self.metadata_extractor = MetadataExtractor()

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError))
    )
    async def process(self, job_id: str, document_id: str, raw_file_path: str, user_metadata: dict = None) -> ProcessingResult:
        start_time = time.time()
        errors = []
        try:
            secure_path, file_hash = self.file_store.validate_and_store(raw_file_path)
            extracted_meta = self.metadata_extractor.extract(secure_path)
            final_meta = {**extracted_meta, **(user_metadata or {})}
            
            page_texts, failed_pages = self.parser.extract(secure_path)
            if failed_pages:
                ocr_results = self.ocr.process_pages(secure_path, failed_pages)
                for idx, text in ocr_results.items():
                    page_texts[idx] = text

            section_map = self.layout.detect_sections(page_texts)
            all_chunks = []
            
            for page_idx, text in enumerate(page_texts):
                current_section = section_map.get(page_idx, "unknown")
                cleaned_text = self.cleaner.clean(text)
                if not cleaned_text: continue

                raw_chunks = self.chunker.chunk_text(cleaned_text)
                for chunk_idx, (chunk_text, token_count, char_start, char_end) in enumerate(raw_chunks):
                    chunk_id = f"{document_id}_p{page_idx+1}_c{chunk_idx}"
                    provenance = ChunkProvenance(
                        document_id=document_id, page=page_idx + 1, section=current_section,
                        chunk_index=chunk_idx, source="pdf_digital_ocr",
                        char_offset_start=char_start, char_offset_end=char_end
                    )
                    all_chunks.append(DocumentChunk(
                        provenance=provenance, text=chunk_text, token_count=token_count,
                        metadata={"file_hash": file_hash, **final_meta}
                    ))

            await self.repo.save_chunks(all_chunks)
            return ProcessingResult(document_id=document_id, job_id=job_id, total_pages=len(page_texts),
                                    ocr_pages=len(failed_pages), chunks_generated=len(all_chunks),
                                    processing_time_ms=int((time.time() - start_time) * 1000),
                                    status="success", errors=errors)
        except Exception as e:
            logger.error("pipeline_failed", document_id=document_id, error=str(e))
            errors.append(str(e))
            raise