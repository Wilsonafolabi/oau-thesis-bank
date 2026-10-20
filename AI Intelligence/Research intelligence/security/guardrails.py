import re
import logging
from typing import Tuple, List, Dict, Any
from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Initialize rate limiter (Section 7.9: Prevent API abuse)
limiter = Limiter(key_func=get_remote_address)

class SecurityGuardrails:
    """
    Dedicated security module (Section 7.9) that works jointly with RAG guardrails (e.g., Laya) 
    to constrain retrieved content and prevent API abuse or data leakage.
    """
    def __init__(self):
        # Basic prompt injection patterns (Defense-in-depth alongside Laya)
        self.injection_patterns = [
            r'ignore\s+previous\s+instructions',
            r'act\s+as\s+a\s+system\s+administrator',
            r'system\s+prompt',
            r'jailbreak',
            r'dan\s+mode',
            r'ignore\s+all\s+rules'
        ]
        # PII patterns to redact before logging or external processing
        self.pii_patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b',
            'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        }

    def sanitize_input(self, text: str) -> Tuple[str, bool]:
        """Checks for prompt injection. Returns sanitized text + is_safe flag."""
        text_lower = text.lower()
        for pattern in self.injection_patterns:
            if re.search(pattern, text_lower):
                logger.warning(f"Prompt injection attempt detected and blocked: {text[:50]}...")
                return text, False # Block the request
        return text, True

    def filter_restricted_chunks(self, retrieved_chunks: List[Dict[str, Any]], user_role: str) -> List[Dict[str, Any]]:
        """
        Section 7.9: Prevents leaking restricted content.
        Filters out thesis chunks that the user's role is not authorized to see.
        """
        allowed_chunks = []
        for chunk in retrieved_chunks:
            access_level = chunk.get('access_level', 'public') # 'public', 'restricted', 'department_only'
            
            if access_level == 'public':
                allowed_chunks.append(chunk)
            elif access_level == 'restricted' and user_role in ['faculty', 'admin']:
                allowed_chunks.append(chunk)
            elif access_level == 'department_only' and user_role in ['faculty', 'admin']:
                # In production, add department ID matching here
                allowed_chunks.append(chunk)
            else:
                logger.info(f"Filtered out restricted chunk (ID: {chunk.get('id')}) for role: {user_role}")
                
        return allowed_chunks

    def mask_pii(self, text: str) -> str:
        """Masks PII in text before sending to external services or logs."""
        for pii_type, pattern in self.pii_patterns.items():
            text = re.sub(pattern, f'[REDACTED_{pii_type.upper()}]', text)
        return text

guardrails = SecurityGuardrails()