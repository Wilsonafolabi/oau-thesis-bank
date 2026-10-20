from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class TaskType(str, Enum):
    CONTENT_MODERATION = "content_moderation"
    QUERY_CLASSIFICATION = "query_classification"

class RoutingDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"

class GuardrailOutcome(str, Enum):
    PASSED = "passed"
    BLOCKED = "blocked"
    FLAGGED = "flagged"

class FallbackReason(str, Enum):
    NONE = "none"
    MISSING_API_KEY = "missing_api_key"
    TIMEOUT = "timeout"
    ERROR = "error"
    LOW_CONFIDENCE = "low_confidence"
    INVALID_OUTPUT = "invalid_output"
    POLICY_VIOLATION = "policy_violation"

class DecisionResult(BaseModel):
    task_type: TaskType
    decision: RoutingDecision
    confidence: float = Field(ge=0.0, le=1.0)
    engine_used: str  # "jev", "laya", "nemo", "llm_provider", or "python"
    fallback_reason: FallbackReason
    guardrail_outcome: GuardrailOutcome = GuardrailOutcome.PASSED
    provenance: Dict[str, Any] = Field(default_factory=dict)

class RoutingPolicy(BaseModel):
    confidence_threshold: float = Field(default=0.80)
    require_auth: bool = Field(default=True)
    require_guardrails: bool = Field(default=True)
