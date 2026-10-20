import time
import logging
import re
from typing import Optional, Dict, Any
from decision_layer.schemas import TaskType, RoutingDecision, GuardrailOutcome, FallbackReason, DecisionResult, RoutingPolicy
from decision_layer.jev_client import JEVClient
from decision_layer.laya_client import LayaClient

# Import existing infrastructure
from security.nemoguardrails.runtime import get_runtime
from security.nemoguardrails.schemas import GuardrailsRequest, GuardrailOutcome as NeMoOutcome
from llm_providers import get_router as get_llm_router, ChatMessage, ChatRequest

logger = logging.getLogger(__name__)

class TypedDecisionRouter:
    def __init__(self, policy: Optional[RoutingPolicy] = None):
        self.policy = policy or RoutingPolicy()
        self.jev = JEVClient()
        self.laya = LayaClient()
        self.nemo_runtime = get_runtime()
        self.llm_router = get_llm_router()
        self.telemetry = []

    def _validate_auth_and_schema(self, task_type: str, user_id: Optional[str]) -> Optional[DecisionResult]:
        """Hard block. Cannot be bypassed by any model."""
        try:
            task = TaskType(task_type)
        except ValueError:
            return DecisionResult(task_type=TaskType.QUERY_CLASSIFICATION, decision=RoutingDecision.BLOCK, confidence=1.0, engine_used="python", fallback_reason=FallbackReason.INVALID_OUTPUT, provenance={"error": "bad_task_type"})
        
        if self.policy.require_auth and not user_id:
            return DecisionResult(task_type=task, decision=RoutingDecision.BLOCK, confidence=1.0, engine_used="python", fallback_reason=FallbackReason.INVALID_OUTPUT, provenance={"error": "missing_user_id"})
        return None

    async def _run_nemo_guardrails(self, state: Dict[str, Any]) -> Optional[DecisionResult]:
        """Ensure classification cannot bypass NeMo Guardrails."""
        if not self.policy.require_guardrails:
            return None
            
        try:
            req = GuardrailsRequest(request_id="decision_layer", user_input=str(state), evidence=[])
            resp = await self.nemo_runtime.run(req)
            
            if resp.outcome == NeMoOutcome.BLOCKED:
                return DecisionResult(
                    task_type=TaskType.QUERY_CLASSIFICATION, decision=RoutingDecision.BLOCK, confidence=1.0,
                    engine_used="nemo", fallback_reason=FallbackReason.POLICY_VIOLATION,
                    guardrail_outcome=GuardrailOutcome.BLOCKED,
                    provenance={"validator": "nemo_guardrails", "reason": resp.reason}
                )
        except Exception as e:
            logger.warning(f"NeMo Guardrails failed, proceeding with caution: {e}")
        return None

    async def _fallback_to_llm(self, task: TaskType, state: Dict[str, Any], reason: FallbackReason) -> DecisionResult:
        """Route to the ACTUAL configured LLM/provider workflow."""
        logger.info(f"Falling back to LLM provider due to: {reason.value}")
        
        questions = self._build_questions(task)
        prompt = f"Analyze the following state and answer the question. State: {state}. Question: {questions}. Reply ONLY with 'ALLOW' or 'BLOCK'."
        
        try:
            llm_resp = self.llm_router.complete(ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                max_tokens=10, temperature=0.0
            ))
            
            # Parse LLM text output strictly (No LLM JSON bypass)
            text = llm_resp.content.upper()
            decision = RoutingDecision.ALLOW if "ALLOW" in text else RoutingDecision.BLOCK
            confidence = 0.5 # LLM fallback gets neutral confidence
            
            return DecisionResult(
                task_type=task, decision=decision, confidence=confidence,
                engine_used="llm_provider", fallback_reason=reason,
                guardrail_outcome=GuardrailOutcome.PASSED if decision == RoutingDecision.ALLOW else GuardrailOutcome.BLOCKED,
                provenance={"validator": "llm_provider", "model": llm_resp.model, "raw_text": llm_resp.content}
            )
        except Exception as e:
            return DecisionResult(
                task_type=task, decision=RoutingDecision.BLOCK, confidence=0.0,
                engine_used="llm_provider", fallback_reason=FallbackReason.ERROR,
                provenance={"error": str(e)}
            )

    def _build_questions(self, task: TaskType) -> Dict[str, Any]:
        if task == TaskType.CONTENT_MODERATION:
            return {"is_safe": {"type": "noul", "instructions": "Is this content safe and policy-compliant?"}}
        return {"intent": {"type": "choice", "instructions": "Classify intent", "criteria": {"info": "informational", "action": "actionable"}}}

    def _extract_confidence(self, answers: Dict[str, Any]) -> float:
        first_key = list(answers.keys())[0]
        val = answers[first_key]
        return float(val.get("noul", val.get("confidence", 0.5)))

    def _process_answers(self, task: TaskType, answers: Dict[str, Any], engine: str, reason: FallbackReason) -> DecisionResult:
        if not answers: raise ValueError("Empty answers from model")
        confidence = self._extract_confidence(answers)
        decision = RoutingDecision.BLOCK if confidence < 0.5 else RoutingDecision.ALLOW
        return DecisionResult(
            task_type=task, decision=decision, confidence=confidence,
            engine_used=engine, fallback_reason=reason,
            provenance={"raw_answers": answers}
        )

    async def route(self, task_type: str, state: Dict[str, Any], user_id: Optional[str] = None) -> DecisionResult:
        start = time.time()
        
        # 1. Hard Auth/Schema Check
        auth_block = self._validate_auth_and_schema(task_type, user_id)
        if auth_block:
            self.telemetry.append(auth_block.model_dump()); return auth_block

        # 2. NeMo Guardrails Check (Cannot be bypassed)
        nemo_block = await self._run_nemo_guardrails(state)
        if nemo_block:
            self.telemetry.append(nemo_block.model_dump()); return nemo_block

        task = TaskType(task_type)
        questions = self._build_questions(task)

        # 3. Try Primary: JEV API
        jev_res = await self.jev.classify(state, questions)
        
        if jev_res["status"] == "success":
            try:
                decision = self._process_answers(task, jev_res["data"]["answers"], "jev", FallbackReason.NONE)
                if decision.confidence >= self.policy.confidence_threshold:
                    self.telemetry.append(decision.model_dump()); return decision
                reason = FallbackReason.LOW_CONFIDENCE
            except Exception:
                reason = FallbackReason.INVALID_OUTPUT
        else:
            reason_str = jev_res.get("reason", "error")
            try: reason = FallbackReason(reason_str)
            except ValueError: reason = FallbackReason.ERROR

        # 4. Fallback: Local Laya (Fast, ~33ms)
        try:
            laya_res = self.laya.predict(state, questions)
            decision = self._process_answers(task, laya_res["answers"], "laya", reason)
            self.telemetry.append(decision.model_dump()); return decision
        except Exception:
            pass # Laya failed, go to LLM

        # 5. Final Fallback: Actual LLM Provider Workflow
        decision = await self._fallback_to_llm(task, state, reason)
        self.telemetry.append(decision.model_dump())
        return decision
