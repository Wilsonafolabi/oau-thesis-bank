from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class GuardrailOutcome(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ABSTAINED = "abstained"
    FLAGGED = "flagged"
    ERROR = "error"

class EvidenceReference(BaseModel):
    document_id: str
    chunk_id: str
    text: str

class GuardrailsRequest(BaseModel):
    request_id: str
    user_input: str
    evidence: List[EvidenceReference] = Field(default_factory=list)

class GuardrailsResponse(BaseModel):
    request_id: str
    outcome: GuardrailOutcome
    flow: str
    reason: str
    answer: Optional[str] = None
    citations: List[str] = Field(default_factory=list)
