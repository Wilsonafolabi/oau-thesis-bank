import json
import logging
import re
import uuid
import time
from contextvars import ContextVar
from typing import Optional, Dict, Any, Union

# --- Context Variables for Correlation ---
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

# --- Sensitive Data Redactor ---
class Redactor:
    PATTERNS = [
        (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), 'Bearer [REDACTED]'),
        (re.compile(r'api[_-]?key["\s:=]+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), 'api_key=[REDACTED]'),
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL_REDACTED]'),
        (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '[IP_REDACTED]'),
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
        safe_data = {}
        for k, v in data.items():
            key_lower = k.lower()
            if any(s in key_lower for s in ['password', 'secret', 'token', 'authorization', 'api_key', 'auth', 'auth']):
                safe_data[k] = '[REDACTED]'
            elif isinstance(v, str):
                safe_data[k] = cls.redact(v)
            elif isinstance(v, dict):
                safe_data[k] = cls.redact_dict(v)
            else:
                safe_data[k] = v
        return safe_data

# --- Structured JSON Formatter ---
class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "trace_id": trace_id_var.get(),
        }
        
        # Add extra fields safely
        for key in ['operation', 'status', 'duration_ms', 'provider', 'model', 
                    'fallback_reason', 'error_category', 'tokens_input', 'tokens_output', 
                    'estimated_cost']:
            if hasattr(record, key):
                val = getattr(record, key)
                # Distinguish unavailable (None) from zero (0)
                log_data[key] = val if val is not None else "unavailable"
                
        # Redact any extra dict passed in 'extra'
        if hasattr(record, 'safe_payload'):
            log_data["payload"] = Redactor.redact_dict(record.safe_payload)
            
        return json.dumps(log_data, default=str)

# --- Logger Setup ---
def setup_telemetry(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("phase3_telemetry")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger

# --- Bounded Metrics Tracker ---
class BoundedMetrics:
    """Tracks metrics with strictly bounded labels to prevent cardinality explosion."""
    ALLOWED_OPERATIONS = {
        "api_request", "document_ingestion", "embedding_job", "search_rerank", 
        "rag_generation", "nemoguardrails_check", "jev_decision", "provider_call", 
        "research_gap", "similarity_job", "evaluation_run"
    }
    ALLOWED_STATUSES = {"success", "error", "timeout", "blocked", "fallback"}

    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.latencies: Dict[str, float] = {}

    def record(self, operation: str, status: str, duration_ms: float):
        op = operation if operation in self.ALLOWED_OPERATIONS else "unknown"
        stat = status if status in self.ALLOWED_STATUSES else "unknown"
        key = f"{op}:{stat}"
        
        self.counters[key] = self.counters.get(key, 0) + 1
        self.latencies[key] = self.latencies.get(key, 0.0) + duration_ms

    def get_summary(self) -> Dict[str, Any]:
        return {"counters": self.counters, "avg_latencies": {
            k: self.latencies[k] / self.counters[k] for k in self.counters if self.counters[k] > 0
        }}

metrics = BoundedMetrics()


