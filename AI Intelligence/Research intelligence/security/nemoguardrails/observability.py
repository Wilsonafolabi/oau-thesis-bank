"""Optional Langfuse observability. Degrades to no-op when disabled or unavailable."""
import os
import re
import contextlib

CallbackHandler = None
_import_error = None
try:
    from langfuse.langchain import CallbackHandler as _CB
    CallbackHandler = _CB
except Exception as e1:
    try:
        from langfuse.callback import CallbackHandler as _CB2
        CallbackHandler = _CB2
    except Exception as e2:
        _import_error = e2

_SECRET_RE = re.compile(r"(?i)(gsk_[A-Za-z0-9]+|sk-[A-Za-z0-9]+|Bearer\s+[A-Za-z0-9._-]+|api[_-]?key\s*[:=]\s*\S+)")


def redact(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text or "")


def langfuse_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY") and CallbackHandler is not None)


_handler = None
def get_langfuse_handler():
    global _handler
    if not langfuse_enabled():
        return None
    if _handler is None:
        try:
            _handler = CallbackHandler()
        except Exception:
            _handler = None
    return _handler


@contextlib.contextmanager
def trace_span(name: str, metadata: dict = None):
    if not langfuse_enabled():
        yield None
        return
    try:
        from langfuse import get_client
        client = get_client()
        safe_meta = {k: redact(str(v)) for k, v in (metadata or {}).items()}
        with client.start_as_current_span(name=name, metadata=safe_meta) as span:
            yield span
    except Exception:
        yield None
