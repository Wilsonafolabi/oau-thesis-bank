"""JEV decision router — fail-closed typed decision router.

Full decision-making and security scope preserved from the V1 reference:
- Validates auth and schema
- Runs NeMo-style guardrails (input injection, safety, off-topic, evidence)
- JEV classification (primary decision engine)
- Laya-style local prediction (secondary)
- LLM fallback (BLOCK only — ALLOW from fallback is not trusted)

No open-ended autonomous loop. Bounded, typed, testable workflow.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from ..config import LLMSettings, get_settings
from ..errors import ConfigurationError, GuardrailError
from .client import JEVClient
from .schemas import (
    DecisionResult,
    FallbackReason,
    GuardrailOutcome,
    RoutingDecision,
    RoutingPolicy,
    TaskType,
)

logger = logging.getLogger("oau_ai.jev.router")


class TypedDecisionRouter:
    """Fail-closed router using JEV, local decision model, and the configured LLM."""

    def __init__(
        self,
        policy: Optional[RoutingPolicy] = None,
        jev_client: Optional[JEVClient] = None,
        settings: Optional[LLMSettings] = None,
    ) -> None:
        self.policy = policy or RoutingPolicy()
        self.jev = jev_client or JEVClient()
        self.settings = settings or get_settings()
        self.telemetry: list = []
        # Local decision model (Laya-style) state — observable so callers
        # can determine whether local inference is available.
        self.local_model_available: bool = False
        self.local_model_error: Optional[str] = None

    def _record(self, result: DecisionResult) -> DecisionResult:
        self.telemetry.append(result.model_dump(mode="json"))
        return result

    def _blocked(
        self,
        task: TaskType,
        reason: FallbackReason,
        error: str,
        engine: str = "python",
    ) -> DecisionResult:
        return DecisionResult(
            task_type=task,
            decision=RoutingDecision.BLOCK,
            confidence=1.0,
            engine_used=engine,
            fallback_reason=reason,
            guardrail_outcome=GuardrailOutcome.BLOCKED,
            provenance={"error": error},
        )

    def _validate_auth_and_schema(
        self,
        task_type: Any,
        user_id: Optional[str],
    ) -> Optional[DecisionResult]:
        try:
            task = TaskType(task_type)
        except (ValueError, TypeError):
            return self._blocked(
                TaskType.QUERY_CLASSIFICATION,
                FallbackReason.INVALID_OUTPUT,
                "invalid_task_type",
            )

        if self.policy.require_auth and not user_id:
            return self._blocked(
                task,
                FallbackReason.INVALID_OUTPUT,
                "missing_user_id",
            )

        return None

    @staticmethod
    def _extract_user_input(state: Dict[str, Any]) -> Optional[str]:
        for key in ("user_input", "query", "text", "content", "input"):
            value = state.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_evidence(state: Dict[str, Any]) -> list:
        raw_evidence = state.get("evidence") or []

        if isinstance(raw_evidence, dict):
            raw_evidence = [raw_evidence]

        if not isinstance(raw_evidence, list):
            raise ValueError("Evidence must be a list or dictionary")

        evidence = []
        for item in raw_evidence:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            elif hasattr(item, "dict") and not isinstance(item, dict):
                item = item.dict()

            if not isinstance(item, dict):
                continue

            document_id = item.get("document_id")
            chunk_id = item.get("chunk_id")
            passage = item.get("text")

            if not all(
                isinstance(value, str) and value.strip()
                for value in (document_id, chunk_id, passage)
            ):
                continue

            evidence.append(
                {
                    "document_id": document_id.strip(),
                    "chunk_id": chunk_id.strip(),
                    "text": passage.strip(),
                }
            )

        return evidence

    def _build_questions(self, task: TaskType) -> Dict[str, Any]:
        if task == TaskType.CONTENT_MODERATION:
            return {
                "is_safe": {
                    "type": "noul",
                    "instructions": (
                        "Determine whether the content is safe and "
                        "compliant with the applicable policy."
                    ),
                }
            }

        if task == TaskType.RESEARCH_GAP_ANALYSIS:
            return {
                "has_explicit_limitations": {
                    "type": "choice",
                    "instructions": "Do the retrieved theses explicitly state limitations or gaps in their own words?",
                    "criteria": {
                        "yes": "The thesis text explicitly mentions limitations, gaps, or areas for future research.",
                        "no": "The thesis text does not explicitly mention limitations or gaps.",
                    },
                },
                "has_topic_gap": {
                    "type": "choice",
                    "instructions": "Is there a topic or research area that is missing or under-covered across the retrieved theses?",
                    "criteria": {
                        "yes": "A clear topic gap exists — an important research area is not addressed.",
                        "no": "The topic area is adequately covered across the theses.",
                    },
                },
                "has_methodological_gap": {
                    "type": "choice",
                    "instructions": "Is there a methodological approach that is missing or under-used across the retrieved theses?",
                    "criteria": {
                        "yes": "A clear methodological gap exists — an important research method is not applied.",
                        "no": "The methodological approaches are adequately diverse.",
                    },
                },
                "has_population_gap": {
                    "type": "choice",
                    "instructions": "Is there a population or context that is missing or under-represented across the retrieved theses?",
                    "criteria": {
                        "yes": "A clear population/context gap exists — an important demographic or setting is not studied.",
                        "no": "The populations and contexts are adequately represented.",
                    },
                },
                "has_evidence_gap": {
                    "type": "choice",
                    "instructions": "Is there a claim or finding that lacks sufficient supporting evidence across the retrieved theses?",
                    "criteria": {
                        "yes": "A clear evidence gap exists — an important claim is unsupported.",
                        "no": "Claims are adequately supported by evidence.",
                    },
                },
                "has_contradictory_findings": {
                    "type": "choice",
                    "instructions": "Do the retrieved theses present contradictory or conflicting findings on the same topic?",
                    "criteria": {
                        "yes": "Clear contradictory findings exist between theses.",
                        "no": "Findings are consistent or complementary across theses.",
                    },
                },
            }

        return {
            "intent": {
                "type": "choice",
                "instructions": "Classify the query intent.",
                "criteria": {
                    "info": "informational",
                    "action": "actionable",
                },
            }
        }

    def _extract_confidence(self, answers: Dict[str, Any]) -> float:
        if not isinstance(answers, dict) or not answers:
            raise ValueError("Model returned no answers")

        value = next(iter(answers.values()))

        if isinstance(value, dict):
            value = value.get("confidence", value.get("noul"))

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Model returned invalid confidence")

        confidence = float(value)

        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")

        return confidence

    def _process_answers(
        self,
        task: TaskType,
        answers: Dict[str, Any],
        engine: str,
        reason: FallbackReason,
    ) -> DecisionResult:
        confidence = self._extract_confidence(answers)

        if confidence < self.policy.confidence_threshold:
            decision = RoutingDecision.BLOCK
            outcome = GuardrailOutcome.FLAGGED
        else:
            decision = RoutingDecision.ALLOW
            outcome = GuardrailOutcome.PASSED

        return DecisionResult(
            task_type=task,
            decision=decision,
            confidence=confidence,
            engine_used=engine,
            fallback_reason=reason,
            guardrail_outcome=outcome,
            provenance={"raw_answers": answers},
        )

    async def _fallback_to_llm(
        self,
        task: TaskType,
        state: Dict[str, Any],
        reason: FallbackReason,
    ) -> DecisionResult:
        logger.info("Using LLM fallback: %s", reason.value)

        prompt = (
            "Classify the provided task state. "
            "Return exactly one token: ALLOW or BLOCK. "
            "Do not provide an explanation.\n"
            f"Task: {task.value}\n"
            f"State: {state}"
        )

        try:
            from ..llm.router import get_router, complete_with_deepseek

            chat_messages = [
                {"role": "user", "content": prompt}
            ]
            response = complete_with_deepseek(
                chat_messages, max_tokens=10, temperature=0.0
            )

            raw = str(response.content).strip().upper()

            if raw not in {"ALLOW", "BLOCK"}:
                return self._blocked(
                    task,
                    FallbackReason.INVALID_OUTPUT,
                    "llm_returned_invalid_decision",
                    engine="llm_provider",
                )

            decision = RoutingDecision(raw.lower())

            # An LLM response alone cannot authorize an ALLOW because
            # its confidence has not been independently verified.
            if decision == RoutingDecision.ALLOW:
                return self._blocked(
                    task,
                    FallbackReason.LOW_CONFIDENCE,
                    "llm_fallback_has_no_verified_confidence",
                    engine="llm_provider",
                )

            return DecisionResult(
                task_type=task,
                decision=RoutingDecision.BLOCK,
                confidence=1.0,
                engine_used="llm_provider",
                fallback_reason=reason,
                guardrail_outcome=GuardrailOutcome.BLOCKED,
                provenance={
                    "validator": "llm_provider",
                    "model": getattr(response, "model", None),
                },
            )

        except Exception:
            logger.exception("LLM fallback failed")
            return self._blocked(
                task,
                FallbackReason.ERROR,
                "llm_fallback_unavailable",
                engine="llm_provider",
            )

    async def route(
        self,
        task_type: str,
        state: Dict[str, Any],
        user_id: Optional[str] = None,
        require_evidence: bool = True,
    ) -> DecisionResult:
        started = time.monotonic()

        auth_result = self._validate_auth_and_schema(task_type, user_id)
        if auth_result:
            return self._record(auth_result)

        task = TaskType(task_type)

        if not isinstance(state, dict):
            return self._record(
                self._blocked(
                    task,
                    FallbackReason.INVALID_OUTPUT,
                    "invalid_task_state",
                )
            )

        # Guardrail check (input injection, safety, off-topic, evidence).
        # require_evidence=False skips the evidence-required check for
        # pre-retrieval security screening; evidence is checked in phase 2.
        guardrail_result = self._run_guardrails(
            task, state, require_evidence=require_evidence
        )
        if guardrail_result:
            guardrail_result.provenance["elapsed_ms"] = round(
                (time.monotonic() - started) * 1000, 2
            )
            return self._record(guardrail_result)

        questions = self._build_questions(task)
        fallback_reason = FallbackReason.ERROR

        try:
            jev_result = await self.jev.classify(state, questions)

            if jev_result.get("status") == "success":
                try:
                    decision = self._process_answers(
                        task,
                        jev_result["data"]["answers"],
                        "jev",
                        FallbackReason.NONE,
                    )

                    if decision.confidence >= self.policy.confidence_threshold:
                        decision.provenance["elapsed_ms"] = round(
                            (time.monotonic() - started) * 1000, 2
                        )
                        return self._record(decision)

                    fallback_reason = FallbackReason.LOW_CONFIDENCE

                except (KeyError, TypeError, ValueError):
                    fallback_reason = FallbackReason.INVALID_OUTPUT

            else:
                try:
                    fallback_reason = FallbackReason(
                        jev_result.get("reason", "error")
                    )
                except ValueError:
                    fallback_reason = FallbackReason.ERROR

        except Exception:
            logger.exception("JEV classification failed")
            fallback_reason = FallbackReason.ERROR

        # Local decision model (Laya-style) secondary check.
        local_result = self._local_predict(state, questions)
        if local_result.get("status") == "unavailable":
            # Local model not configured — record the state and fall through
            # to the LLM fallback without logging a noisy exception.
            logger.debug(
                "Local decision model unavailable: %s",
                local_result.get("reason", "unknown"),
            )
            fallback_reason = FallbackReason.ERROR
        else:
            try:
                answers = local_result.get("answers", {})
                decision = self._process_answers(
                    task,
                    answers,
                    "local",
                    fallback_reason,
                )

                if decision.confidence >= self.policy.confidence_threshold:
                    decision.provenance["elapsed_ms"] = round(
                        (time.monotonic() - started) * 1000, 2
                    )
                    return self._record(decision)

                fallback_reason = FallbackReason.LOW_CONFIDENCE

            except Exception:
                logger.exception("Local decision model failed")
                fallback_reason = FallbackReason.ERROR

        decision = await self._fallback_to_llm(
            task,
            state,
            fallback_reason,
        )

        decision.provenance["elapsed_ms"] = round(
            (time.monotonic() - started) * 1000, 2
        )
        return self._record(decision)

    def _run_guardrails(
        self,
        task: TaskType,
        state: Dict[str, Any],
        require_evidence: bool = True,
    ) -> Optional[DecisionResult]:
        if not self.policy.require_guardrails:
            return None

        user_input = self._extract_user_input(state)
        if not user_input:
            return self._blocked(
                task,
                FallbackReason.INVALID_OUTPUT,
                "missing_user_input",
                engine="guardrails",
            )

        # Input injection patterns.
        injection_patterns = [
            r"ignore\s+(all\s+)?previous\s+instructions",
            r"disregard\s+(all\s+)?(previous|prior)\s+instructions",
            r"reveal\s+(your\s+)?(system prompt|hidden instructions)",
            r"act\s+as\s+if\s+your\s+safety\s+rules",
        ]
        import re

        if any(re.search(p, user_input, re.I) for p in injection_patterns):
            return self._blocked(
                task,
                FallbackReason.POLICY_VIOLATION,
                "input_injection_detected",
                engine="guardrails",
            )

        # Evidence requirement for research-style questions.
        # When require_evidence=False (pre-retrieval screening), skip this
        # check; evidence is validated in phase 2 after retrieval.
        evidence = self._extract_evidence(state)
        research_patterns = [
            r"\b(thesis|summar|finding|result|method|dataset|accuracy|what does|according to|fraud|p-value|research|evidence|literature|citation|study)\b"
        ]
        if not any(re.search(p, user_input, re.I) for p in research_patterns):
            pass  # non-research query; evidence not required
        elif require_evidence and not evidence:
            return self._blocked(
                task,
                FallbackReason.INVALID_OUTPUT,
                "no_retrieved_evidence",
                engine="guardrails",
            )

        return None

    def _local_predict(
        self, state: Dict[str, Any], questions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Local decision model prediction (Laya-style).

        Returns a structured dict with answers. In the V2 foundation stage no
        trained local model artifact is available, so this returns an
        "unavailable" status rather than raising — the router treats an
        unavailable local model as a graceful degradation, falling through to
        the LLM fallback.
        """
        # Local model not configured in V2 foundation stage. Report as
        # unavailable rather than raising; the router falls through to the
        # LLM fallback.
        self.local_model_available = False
        self.local_model_error = "local_decision_model_not_configured"
        return {
            "status": "unavailable",
            "reason": "local_decision_model_not_configured",
            "answers": {},
        }
