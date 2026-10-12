import pytest
import logging
import json
from telemetry.core import (
    setup_telemetry, Redactor, request_id_var, trace_id_var, 
    BoundedMetrics, metrics
)
from telemetry.health import health_manager

# --- Test Redaction ---
def test_redactor_masks_sensitive_data():
    assert Redactor.redact("Bearer abc123") == "Bearer [REDACTED]"
    assert Redactor.redact("api_key=sk-12345") == "api_key=[REDACTED]"
    assert Redactor.redact("user@test.com") == "[EMAIL_REDACTED]"
    
    payload = {"authorization": "secret123", "query": "hello world", "nested": {"auth_token": "xyz"}}
    safe = Redactor.redact_dict(payload)
    assert safe["authorization"] == "[REDACTED]"
    assert safe["nested"]["auth_token"] == "[REDACTED]"
    assert safe["query"] == "hello world"

# --- Test Correlation IDs ---
def test_correlation_ids_in_logs(caplog):
    logger = setup_telemetry("INFO")
    
    # Set context
    request_id_var.set("req-123")
    trace_id_var.set("trace-456")
    
    with caplog.at_level(logging.INFO, logger="phase3_telemetry"):
        logger.info("Test message", extra={"operation": "api_request", "status": "success"})
        
    assert len(caplog.records) == 1
    
    # Test the formatter directly for exact JSON structure
    formatter = logger.handlers[0].formatter
    formatted = formatter.format(caplog.records[0])
    parsed = json.loads(formatted)
    
    assert parsed["request_id"] == "req-123"
    assert parsed["trace_id"] == "trace-456"
    assert parsed["operation"] == "api_request"
    assert parsed["status"] == "success"

# --- Test Token Usage Distinction ---
def test_token_usage_unavailable_vs_zero():
    logger = setup_telemetry("INFO")
    formatter = logger.handlers[0].formatter
    
    record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
    record.tokens_input = 0
    record.tokens_output = None # Unavailable
    
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    
    assert parsed["tokens_input"] == 0
    assert parsed["tokens_output"] == "unavailable"

# --- Test Bounded Metrics ---
def test_bounded_metrics_prevent_cardinality_explosion():
    m = BoundedMetrics()
    m.record("api_request", "success", 100.0)
    m.record("api_request", "success", 200.0)
    m.record("invalid_op_xyz", "success", 50.0) # Should be bounded to "unknown"
    
    summary = m.get_summary()
    assert summary["counters"]["api_request:success"] == 2
    assert summary["counters"]["unknown:success"] == 1
    assert summary["avg_latencies"]["api_request:success"] == 150.0

# --- Test Health Checks ---
@pytest.mark.asyncio
async def test_health_and_readiness_checks():
    async def mock_db_healthy(): return True
    async def mock_jev_unhealthy(): return False
    
    health_manager.register_dependency("database", mock_db_healthy)
    health_manager.register_dependency("jev_api", mock_jev_unhealthy)
    
    result = await health_manager.check_health()
    
    assert result["status"] == "healthy"
    assert result["readiness"] == "not_ready" # Because JEV is unhealthy
    assert result["dependencies"]["database"] == "healthy"
    assert result["dependencies"]["jev_api"] == "unhealthy"

# --- Test Guardrail & Fallback Events ---
def test_guardrail_and_fallback_logging(caplog):
    logger = setup_telemetry("WARNING")
    formatter = logger.handlers[0].formatter
    
    # Simulate Guardrail Block
    rec1 = logging.LogRecord("test", logging.WARNING, "", 0, "Blocked by NeMo", (), None)
    rec1.operation = "nemoguardrails_check"
    rec1.status = "blocked"
    rec1.fallback_reason = "policy_violation"
    
    # Simulate Provider Fallback
    rec2 = logging.LogRecord("test", logging.WARNING, "", 0, "Falling back to Laya", (), None)
    rec2.operation = "provider_call"
    rec2.status = "fallback"
    rec2.provider = "jev"
    rec2.fallback_reason = "timeout"
    
    log1 = json.loads(formatter.format(rec1))
    log2 = json.loads(formatter.format(rec2))
    
    assert log1["status"] == "blocked"
    assert log1["fallback_reason"] == "policy_violation"
    assert log2["provider"] == "jev"
    assert log2["fallback_reason"] == "timeout"
