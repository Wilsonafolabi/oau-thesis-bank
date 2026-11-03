"""Telemetry module — §1.2 and §3.7 of the frozen contract.

Every AI call must be observable via TelemetryEvent. Every request must
generate a trace_id (UUIDv4) passed through all components.
"""
