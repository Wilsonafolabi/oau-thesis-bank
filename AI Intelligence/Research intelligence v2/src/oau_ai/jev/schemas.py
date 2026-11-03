"""JEV decision schemas — full specification.

These schemas mirror the V1 decision_layer/schemas.py and preserve the
complete JEV routing/decision contract.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    CONTENT_MODERATION = "content_moderation"
    QUERY_CLASSIFICATION = "query_classification"
    RESEARCH_GAP_ANALYSIS = "research_gap_analysis"


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
    engine_used: str
    fallback_reason: FallbackReason = FallbackReason.NONE
    guardrail_outcome: GuardrailOutcome = GuardrailOutcome.PASSED
    provenance: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


class RoutingPolicy(BaseModel):
    confidence_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    require_auth: bool = True
    require_guardrails: bool = True
