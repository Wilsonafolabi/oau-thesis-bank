import re
import unicodedata
from typing import List
from .schemas import DocumentPage, Section, Provenance

SECTIONS = ["abstract", "introduction", "literature review", "methodology", "results", "discussion", "conclusion", "references", "appendices"]

def normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def detect_sections(pages: List[DocumentPage], document_id: str) -> List[Section]:
    sections = []
    current_section = "front_matter"
    start_page = 1
    
    for i, page in enumerate(pages):
        text = page.text_content.lower()
        for sec in SECTIONS:
            if re.search(rf'\b{sec}\b', text):
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