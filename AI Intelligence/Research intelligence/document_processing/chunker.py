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
                source_file=pages[0].provenance.source_file,
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
            provenance = Provenance(document_id=pages[0].document_id, source_file=pages[0].provenance.source_file, chunk_id=chunk_id)
            chunks.append(Chunk(chunk_id=chunk_id, document_id=pages[0].document_id, section_id=None, text=chunk_text, token_count=len(chunk_text)//4, overlap_count=overlap_tokens if i>0 else 0, provenance=provenance))
            
    return chunks
