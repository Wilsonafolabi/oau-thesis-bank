"""Telemetry core — structured event emission with trace propagation.

Implements §1.2 (Telemetry Contract) and §3.7 (Telemetry Schema) of the
frozen contract. Provides ContextVar-based trace_id propagation and a
bounded metrics tracker to prevent cardinality explosion.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# Context variables for correlation across components.
trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
actor_context_var: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "actor_context", default=None
)


class Redactor:
    """Redacts sensitive data from telemetry payloads."""

    PATTERNS = [
        (
            re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
            "Bearer [REDACTED]",
        ),
        (
            re.compile(r'api[_-]?key["\s:=]+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE),
            "api_key=[REDACTED]",
        ),
        (
            re.compile(
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            ),
            "[EMAIL_REDACTED]",
        ),
        (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[IP_REDACTED]"),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        if not isinstance(text, str):
            return text
        for pattern, replacement in cls.PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    @classmethod
    def redact_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        safe_data: Dict[str, Any] = {}
        for k, v in data.items():
            key_lower = k.lower()
            if any(
                s in key_lower
                for s in [
                    "password",
                    "secret",
                    "token",
                    "authorization",
                    "api_key",
                    "auth",
                ]
            ):
                safe_data[k] = "[REDACTED]"
            elif isinstance(v, str):
                safe_data[k] = cls.redact(v)
            elif isinstance(v, dict):
                safe_data[k] = cls.redact_dict(v)
            else:
                safe_data[k] = v
        return safe_data


def generate_trace_id() -> str:
    """Generate a UUIDv4 trace id (§1.2 L13)."""
    return str(uuid.uuid4())


@dataclass
class TelemetryEvent:
    """TelemetryEvent schema (§3.7 of the frozen contract)."""

    trace_id: str
    component: str
    event_type: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: Optional[float] = None
    model_provider: Optional[str] = None
    llm_tier: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "component": self.component,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "model_provider": self.model_provider,
            "llm_tier": self.llm_tier,
        }


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "trace_id": trace_id_var.get(),
        }
        for key in [
            "operation",
            "status",
            "duration_ms",
            "provider",
            "model",
            "fallback_reason",
            "error_category",
            "tokens_input",
            "tokens_output",
            "estimated_cost",
        ]:
            if hasattr(record, key):
                val = getattr(record, key)
                log_data[key] = val if val is not None else "unavailable"
        if hasattr(record, "safe_payload"):
            log_data["payload"] = Redactor.redact_dict(record.safe_payload)
        return json.dumps(log_data, default=str)


def setup_telemetry(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("phase3_telemetry_v2")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


class BoundedMetrics:
    """Tracks metrics with strictly bounded labels to prevent cardinality explosion."""

    ALLOWED_OPERATIONS = {
        "api_request",
        "document_ingestion",
        "embedding_job",
        "search_rerank",
        "rag_generation",
        "nemoguardrails_check",
        "jev_decision",
        "provider_call",
        "research_gap",
        "similarity_job",
        "evaluation_run",
    }
    ALLOWED_STATUSES = {"success", "error", "timeout", "blocked", "fallback"}

    def __init__(self) -> None:
        self.counters: Dict[str, int] = {}
        self.latencies: Dict[str, float] = {}

    def record(self, operation: str, status: str, duration_ms: float) -> None:
        op = operation if operation in self.ALLOWED_OPERATIONS else "unknown"
        stat = status if status in self.ALLOWED_STATUSES else "unknown"
        key = f"{op}:{stat}"
        self.counters[key] = self.counters.get(key, 0) + 1
        self.latencies[key] = self.latencies.get(key, 0.0) + duration_ms

    def get_summary(self) -> Dict[str, Any]:
        return {
            "counters": self.counters,
            "avg_latencies": {
                k: self.latencies[k] / self.counters[k]
                for k in self.counters
                if self.counters[k] > 0
            },
        }


metrics = BoundedMetrics()


@contextmanager
def telemetry_context(
    component: str,
    event_type: str,
    trace_id: Optional[str] = None,
    model_provider: Optional[str] = None,
    llm_tier: Optional[int] = None,
):
    """Context manager emitting a TelemetryEvent on entry/exit (§4 directive 4).

    Every component wraps execution in a telemetry context manager. The
    event records duration, provider, and tier, and always carries trace_id.
    """
    tid = trace_id or generate_trace_id()
    token = trace_id_var.set(tid)
    start = time.perf_counter()
    try:
        yield TelemetryEvent(
            trace_id=tid,
            component=component,
            event_type=event_type,
            model_provider=model_provider,
            llm_tier=llm_tier,
        )
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
        trace_id_var.reset(token)
        metrics.record(component, event_type, duration_ms)
