import fitz
import structlog

logger = structlog.get_logger()

class DigitalParser:
    def extract(self, file_path: str) -> tuple[list[str], list[int]]:
        if file_path.lower().endswith('.docx'):
            return self._extract_docx(file_path)
        return self._extract_pdf(file_path)

    def _extract_docx(self, file_path: str) -> tuple[list[str], list[int]]:
        import docx
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs])
        return [text], []

    def _extract_pdf(self, pdf_path: str) -> tuple[list[str], list[int]]:
        doc = fitz.open(pdf_path)
        page_texts = []
        failed_pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()
            if len(text) < 50 and len(page.get_images(full=True)) > 0:
                failed_pages.append(page_num)
                page_texts.append("")
            else:
                page_texts.append(text)
        doc.close()
        return page_texts, failed_pages