import re
import unicodedata

class TextCleaner:
    def clean(self, text: str) -> str:
        if not text:
            return ""
        # NFC preserves Yoruba diacritics better than NFKC
        text = unicodedata.normalize("NFC", text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text.strip()