import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TelemetryClient:
    def __init__(self):
        self.langfuse = None
        self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        
        if self.public_key and self.secret_key:
            try:
                from langfuse import Langfuse
                self.langfuse = Langfuse(
                    public_key=self.public_key,
                    secret_key=self.secret_key,
                    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
                )
                logger.info("Langfuse telemetry initialized successfully.")
            except ImportError:
                logger.warning("Langfuse package not installed. Falling back to structured logging.")
        else:
            logger.info("Langfuse credentials not found. Operating in structured logging mode (Graceful Degradation per Section 7.10).")

    def trace_generation(self, name: str, input_text: str, output_text: str, metadata: Optional[Dict[str, Any]] = None):
        if self.langfuse:
            self.langfuse.generation(name=name, input=input_text, output=output_text, metadata=metadata or {})
        else:
            logger.info(f"[TELEMETRY] Generation: {name} | Input Len: {len(input_text)} | Output Len: {len(output_text)}")

    def trace_event(self, event_name: str, metadata: Optional[Dict[str, Any]] = None):
        if self.langfuse:
            self.langfuse.span(name=event_name, metadata=metadata or {})
        else:
            logger.info(f"[TELEMETRY] Event: {event_name} | Metadata: {metadata}")

telemetry = TelemetryClient()