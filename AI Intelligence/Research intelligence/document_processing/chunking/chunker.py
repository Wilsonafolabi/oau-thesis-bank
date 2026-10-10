from transformers import AutoTokenizer
import structlog

logger = structlog.get_logger()

class TokenChunker:
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5", chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def chunk_text(self, text: str) -> list[tuple[str, int, int, int]]:
        if not text.strip():
            return []
        
        # Use the project tokenizer to determine token boundaries and character offsets
        encodings = self.tokenizer(text, return_offsets_mapping=True, add_special_tokens=False)
        tokens = encodings['input_ids']
        offsets = encodings['offset_mapping']
        
        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            
            # Get valid character offsets for the current token window
            # (Some special tokens have (0,0) offsets, so we filter them out)
            valid_offsets = [o for o in offsets[start:end] if o != (0, 0)]
            if not valid_offsets:
                start += self.chunk_size - self.overlap
                continue
                
            char_start = valid_offsets[0][0]
            char_end = valid_offsets[-1][1]
            
            # CRITICAL FIX: Slice the original text directly. 
            # Do NOT use tokenizer.decode(), as the English BGE tokenizer 
            # strips out-of-vocabulary characters like Yoruba diacritics.
            chunk_text = text[char_start:char_end]
            token_count = end - start
            
            chunks.append((chunk_text, token_count, char_start, char_end))
            
            if end >= len(tokens):
                break
            start += self.chunk_size - self.overlap
            
        return chunks