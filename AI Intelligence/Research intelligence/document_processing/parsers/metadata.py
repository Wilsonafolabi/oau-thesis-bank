import fitz
from typing import Dict, Any

class MetadataExtractor:
    def extract(self, file_path: str) -> Dict[str, Any]:
        if not file_path.lower().endswith('.pdf'):
            return {}
        doc = fitz.open(file_path)
        meta = doc.metadata or {}
        extracted = {
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
            "keywords": meta.get("keywords", ""),
        }
        if not extracted["title"] and len(doc) > 0:
            text = doc[0].get_text("text").strip().split('\n')
            for line in text:
                line = line.strip()
                if 10 < len(line) < 200 and not line.lower().startswith("chapter"):
                    extracted["title"] = line
                    break
        doc.close()
        return {k: v for k, v in extracted.items() if v}