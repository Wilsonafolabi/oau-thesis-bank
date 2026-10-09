"""Evidence verification via the shared provider-routing layer (no local training)."""
import json
import logging
from typing import Any, Dict, Optional

from llm_providers import ChatMessage, ChatRequest, get_router

logger = logging.getLogger(__name__)

_LABELS = {"supported", "contradicted", "not_mentioned"}


class EvidenceVerifier:
    def __init__(self, router=None):
        self.router = router or get_router()

    def _prompt(self, passage: str, claim: str) -> str:
        return (
            "You are an expert academic fact-checker. Decide whether the claim is "
            "'supported', 'contradicted', or 'not_mentioned' by the passage.\n"
            f"Passage: {passage}\nClaim: {claim}\n"
            'Reply with ONLY valid JSON: {"label": "...", "confidence": 0.0, "reason": "..."}'
        )

    @staticmethod
    def _strip_fences(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            text = text[3:]
            if text.startswith("json"):
                text = text[4:]
            if text.endswith("```"):
                text = text[:-3]
        return text.strip()

    async def verify_claim(self, passage: str, claim: str) -> Dict[str, Any]:
        request = ChatRequest(
            messages=[
                ChatMessage("system", "You are a strict academic fact-checker. Output ONLY valid JSON."),
                ChatMessage("user", self._prompt(passage, claim)),
            ],
            temperature=0.1,
            json_mode=True,
        )
        response = await self.router.acomplete(request)
        try:
            parsed = json.loads(self._strip_fences(response.content))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Verifier provider {response.provider} returned non-JSON verdict") from exc
        label = str(parsed.get("label", "")).strip().lower()
        if label not in _LABELS:
            raise ValueError(f"Verifier received invalid label {label!r} from {response.provider}")
        return {
            "label": label,
            "confidence": float(parsed.get("confidence") or 0.0),
            "reason": str(parsed.get("reason", "")),
            "provider": response.provider,
            "model": response.model,
        }
