import re
import contextvars
import traceback
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from nemoguardrails import LLMRails, RailsConfig
import structlog

from security.nemoguardrails import observability
from security.nemoguardrails.langchain_adapter import RouterChatModel
from security.nemoguardrails.schemas import (
    GuardrailsRequest, GuardrailsResponse, GuardrailOutcome,
)

logger = structlog.get_logger()
_current_context = contextvars.ContextVar("nemo_request_context", default={})
CITATION_RE = re.compile(r"\[source:\s*([^\]]+?)\]")
RESEARCH_RE = re.compile(r"(?i)(thesis|summar|finding|result|method|dataset|accuracy|what does|according to|fraud|p-value)")

INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts|policies)",
    r"(?i)disregard\s+(your|all|any)\s+(rules|policies|instructions|guidelines|safeguards)",
    r"(?i)you\s+are\s+now\s+(dan|developer|root|admin|jailbroken|unrestricted)",
    r"(?i)(reveal|print|show|output|leak)\s+(your\s+)?(system\s+prompt|hidden\s+instructions|system\s+message)",
]
UNSAFE_PATTERNS = [
    r"(?i)(build|make|create)\s+(a\s+)?(bomb|weapon|firearm|explosive)",
    r"(?i)(write|generate|provide)\s+(me\s+)?(malware|ransomware|virus|exploit\s+code)",
]
OFF_TOPIC_PATTERNS = [
    r"(?i)\b(write|generate|tell|give)\b.{0,40}\b(poem|song|joke|story|recipe)\b",
    r"(?i)\b(what is the weather|football|movie|love letter)\b",
]
DOC_INSTRUCTION_PATTERNS = [
    r"(?i)\b(ignore|disregard|override)\b.{0,40}\b(instructions?|policies|rules)\b",
    r"(?im)^\s*(system|assistant)\s*:\s*",
]

REFUSAL_MAP = [
    ("cannot find sufficient evidence", GuardrailOutcome.ABSTAINED, "retrieval_rails"),
    ("embedded instructions", GuardrailOutcome.BLOCKED, "retrieval_rails"),
    ("citations do not match", GuardrailOutcome.BLOCKED, "output_rails"),
    ("cannot override my safety policies", GuardrailOutcome.BLOCKED, "dialog_rails"),
    ("only assist with thesis", GuardrailOutcome.BLOCKED, "dialog_rails"),
    ("not allowed", GuardrailOutcome.BLOCKED, "input_rails"),
    ("service issue", GuardrailOutcome.ERROR, "fallback_rails"),
    ("internal error", GuardrailOutcome.ERROR, "action_error"),
]


class NeMoGuardrailsRuntime:
    def __init__(self, config_path: str = "security/nemoguardrails"):
        self.config_path = config_path
        self.rails = None
        self.langfuse_handler = observability.get_langfuse_handler()
        config = RailsConfig.from_path(self.config_path)
        
        llm = RouterChatModel()
        self.rails = LLMRails(config, llm=llm)
        self._register_actions()
        logger.info("nemoguardrails_initialized", config_path=self.config_path,
                    langfuse_enabled=observability.langfuse_enabled())

    def _register_actions(self):
        self.rails.register_action(self.check_off_topic, "check_off_topic")
        self.rails.register_action(self.check_input_safety, "check_input_safety")
        self.rails.register_action(self.check_injection, "check_injection")
        self.rails.register_action(self.scan_retrieved_content, "scan_retrieved_content")
        self.rails.register_action(self.require_evidence, "require_evidence")
        self.rails.register_action(self.check_output_safety, "check_output_safety")
        self.rails.register_action(self.check_citations, "check_citations")
        self.rails.register_action(self.check_provider_status, "check_provider_status")

    def check_off_topic(self):
        text = _current_context.get().get("user_input", "")
        return any(re.search(p, text) for p in OFF_TOPIC_PATTERNS)

    def check_input_safety(self):
        text = _current_context.get().get("user_input", "")
        return any(re.search(p, text) for p in UNSAFE_PATTERNS)

    def check_injection(self):
        text = _current_context.get().get("user_input", "")
        return any(re.search(p, text) for p in INJECTION_PATTERNS)

    def scan_retrieved_content(self, relevant_chunks=None):
        chunks = relevant_chunks if relevant_chunks is not None else _current_context.get().get("evidence_texts", [])
        for chunk in chunks:
            text = chunk if isinstance(chunk, str) else str(chunk)
            if any(re.search(p, text) for p in DOC_INSTRUCTION_PATTERNS):
                return True
        return False

    def require_evidence(self, relevant_chunks=None):
        ctx = _current_context.get()
        chunks = relevant_chunks if relevant_chunks is not None else ctx.get("evidence_texts", [])
        
        # If no evidence is provided yet (e.g., during initial input classification), 
        # do not block. Only enforce the check if evidence was actually retrieved.
        if len(chunks) == 0:
            return True
            
        if not RESEARCH_RE.search(ctx.get("user_input", "")):
            return True
        return len(chunks) > 0

    def check_output_safety(self, bot_message=""):
        return not any(re.search(p, bot_message or "") for p in UNSAFE_PATTERNS)

    def check_citations(self, bot_message="", evidence_ids=None):
        ctx = _current_context.get()
        ids = list(evidence_ids if evidence_ids is not None else ctx.get("evidence_ids", []))
        ids += [str(i + 1) for i in range(len(ids))]
        for cit in CITATION_RE.findall(bot_message or ""):
            if cit.strip() not in ids:
                return False
        return True

    def check_provider_status(self):
        from llm_config import get_settings
        return bool(get_settings().enabled_order())

    async def run(self, request: GuardrailsRequest) -> GuardrailsResponse:
        if not self.rails:
            return GuardrailsResponse(request_id=request.request_id, outcome=GuardrailOutcome.ERROR,
                                      flow="init", reason="guardrails_uninitialized")
        ctx = {
            "request_id": request.request_id,
            "user_input": request.user_input,
            "evidence_texts": [e.text for e in request.evidence],
            "evidence_ids": [e.document_id for e in request.evidence],
            "relevant_chunks": [e.text for e in request.evidence],
        }
        token = _current_context.set(ctx)
        try:
            with observability.trace_span("nemoguardrails.run",
                                          {"request_id": request.request_id, "n_evidence": len(request.evidence)}):
                try:
                    # Newer NeMo Guardrails uses `messages` instead of `prompt`
                    response = await self.rails.generate_async(
                        messages=[{"role": "user", "content": request.user_input}]
                    )
                    if isinstance(response, dict):
                        response = response.get("content", "")
                    elif isinstance(response, list) and response:
                        response = response[-1].get("content", "") if isinstance(response[-1], dict) else str(response[-1])
                    else:
                        response = str(response or "")
                except Exception as exc:
                    print("\n=== FULL TRACEBACK ===\n" + traceback.format_exc() + "\n=== END TRACEBACK ===\n")
                    logger.error("nemoguardrails_execution_failed", error=type(exc).__name__,
                                 request_id=request.request_id)
                    return GuardrailsResponse(
                        request_id=request.request_id, outcome=GuardrailOutcome.ERROR,
                        flow="fallback_rails", reason=f"execution_error:{type(exc).__name__}",
                        answer="I am currently unable to process your request due to a service issue. Please try again later.")

            answer = response or ""
            low = answer.lower()
            outcome, flow, reason = GuardrailOutcome.ALLOWED, "dialog_rails", "processed"
            for marker, oc, fl in REFUSAL_MAP:
                if marker in low:
                    outcome, flow, reason = oc, fl, marker.replace(" ", "_")
                    break

            citations = CITATION_RE.findall(answer)
            if citations and outcome == GuardrailOutcome.ALLOWED:
                allowed = set(ctx["evidence_ids"]) | {str(i + 1) for i in range(len(request.evidence))}
                if any(c.strip() not in allowed for c in citations):
                    outcome, flow, reason = GuardrailOutcome.BLOCKED, "grounding_validation", "citation_not_in_sources"

            logger.info("security.guardrail", flow=flow, outcome=outcome.value, reason=reason,
                        request_id=request.request_id, content_len=len(answer))
            return GuardrailsResponse(request_id=request.request_id, outcome=outcome, flow=flow,
                                      reason=reason, answer=answer, citations=citations)
        finally:
            _current_context.reset(token)


_runtime = None
def get_runtime() -> NeMoGuardrailsRuntime:
    global _runtime
    if _runtime is None:
        _runtime = NeMoGuardrailsRuntime()
    return _runtime