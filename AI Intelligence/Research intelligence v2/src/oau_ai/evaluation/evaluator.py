"""RAGAS evaluation runner for Phase 3 V2.

Provides a repeatable evaluation harness for grounded RAG quality using
the RAGAS framework. When RAGAS is not installed, or when RAGAS metrics
cannot be initialized, the evaluator degrades gracefully: dataset loading,
metric definitions, and example preparation work offline, but actual
metric computation requires a working RAGAS installation with
initializable metric classes.

All evaluation runs produce structured output with run metadata including
timestamp, dataset size, model/provider configuration, and per-metric scores.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .dataset import EvaluationDataset, EvaluationExample
from .deepseek_llm import DeepSeekLLM, create_deepseek_llm
from .metrics import (
    METRIC_DEFINITIONS,
    _DEEPSEEK_LLM,
    available_metrics,
    get_metric_availability,
    is_available,
)

try:
    import ragas  # type: ignore[import-not-found]
    from ragas import evaluate as ragas_evaluate  # type: ignore[import-not-found]
    from ragas.dataset_schema import SingleTurnSample  # type: ignore[import-not-found]

    _RAGAS_IMPORTED = True
except ImportError:  # pragma: no cover - depends on environment
    _RAGAS_IMPORTED = False


@dataclass
class EvaluationResult:
    """Result of a single metric evaluation.

    Attributes:
        metric_name: Name of the metric (e.g., "faithfulness").
        score: The computed score (0.0-1.0), or None if not computable.
        error: Error message if computation failed, None otherwise.
        available: Whether the metric was computable in this run.
    """

    metric_name: str
    score: float | None = None
    error: str | None = None
    available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "score": self.score,
            "error": self.error,
            "available": self.available,
        }


@dataclass
class EvaluationRun:
    """Metadata and results for a complete evaluation run.

    Attributes:
        run_id: Unique identifier for this evaluation run.
        timestamp: ISO-8601 timestamp when the run started.
        dataset_size: Number of examples evaluated.
        dataset_source: Path or identifier of the dataset source.
        model_provider: LLM provider used for answer generation.
        model_model: Model name used for answer generation.
        metrics_requested: List of metric names that were requested.
        results: List of per-metric results.
        ragas_available: Whether RAGAS metrics were initialized during this run.
        notes: Additional notes about the run (e.g., degradation warnings).
    """

    run_id: str
    timestamp: str
    dataset_size: int
    dataset_source: str
    model_provider: str
    model_model: str
    metrics_requested: list[str]
    results: list[EvaluationResult] = field(default_factory=list)
    ragas_available: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "dataset_size": self.dataset_size,
            "dataset_source": self.dataset_source,
            "model_provider": self.model_provider,
            "model_model": self.model_model,
            "metrics_requested": self.metrics_requested,
            "results": [r.to_dict() for r in self.results],
            "ragas_available": self.ragas_available,
            "notes": self.notes,
        }

    def summary(self) -> dict[str, Any]:
        """Return a summary of the run with scores by metric."""
        scores: dict[str, float | None] = {}
        for r in self.results:
            if r.available:
                scores[r.metric_name] = r.score
        return {
            "run_id": self.run_id,
            "dataset_size": self.dataset_size,
            "ragas_available": self.ragas_available,
            "scores": scores,
            "notes": self.notes,
        }


class RagasEvaluator:
    """RAGAS evaluation runner.

    Evaluates RAG response quality using RAGAS metrics. When RAGAS is not
    installed, or when RAGAS metric classes cannot be initialized, all
    methods return results with `available=False` and descriptive errors.

    Usage:
        evaluator = RagasEvaluator(model_provider="deepseek", model_model="deepseek-chat")
        run = evaluator.evaluate(dataset, metrics=["faithfulness", "answer_relevancy"])
        print(run.summary())
    """

    def __init__(
        self,
        model_provider: str = "deepseek",
        model_model: str = "deepseek-chat",
        llm: Optional[Any] = None,
    ) -> None:
        self.model_provider = model_provider
        self.model_model = model_model
        self.llm = llm or DeepSeekLLM()

    def evaluate(
        self,
        dataset: EvaluationDataset,
        metrics: list[str] | None = None,
        run_id: str | None = None,
    ) -> EvaluationRun:
        """Run RAGAS evaluation on a dataset.

        Args:
            dataset: The evaluation dataset with examples.
            metrics: List of metric names to compute. Defaults to all
                available (initializable) metrics.
            run_id: Optional unique run identifier. Generated if not provided.

        Returns:
            EvaluationRun with per-metric results and run metadata.
        """
        import uuid

        if run_id is None:
            run_id = str(uuid.uuid4())

        timestamp = datetime.now(timezone.utc).isoformat()

        if metrics is None:
            metrics = available_metrics()

        # Validate metric names against definitions.
        unknown = [m for m in metrics if m not in METRIC_DEFINITIONS]
        if unknown:
            raise ValueError(
                f"Unknown metric(s): {unknown}. "
                f"Available: {list(METRIC_DEFINITIONS.keys())}"
            )

        # Probe metric initialization to determine per-metric availability.
        availability = get_metric_availability()
        ragas_available = any(avail for avail, _ in availability.values())

        results: list[EvaluationResult] = []
        notes = ""

        if not ragas_available:
            notes = (
                "RAGAS metrics could not be initialized. Metric computation "
                "is unavailable. Install or fix RAGAS. Dataset loading and "
                "metric definitions work offline."
            )
            for metric_name in metrics:
                avail, err = availability.get(metric_name, (False, "not_probed"))
                results.append(
                    EvaluationResult(
                        metric_name=metric_name,
                        score=None,
                        error=err or "metric_initialization_failed",
                        available=avail,
                    )
                )
            return EvaluationRun(
                run_id=run_id,
                timestamp=timestamp,
                dataset_size=dataset.total_examples,
                dataset_source=dataset.source_file or "unknown",
                model_provider=self.model_provider,
                model_model=self.model_model,
                metrics_requested=metrics,
                results=results,
                ragas_available=False,
                notes=notes,
            )

        # RAGAS metrics are available - run actual evaluation.
        try:
            samples = self._to_ragas_samples(dataset, metrics)
            if not samples:
                notes = "No examples with sufficient data for RAGAS evaluation."
                for metric_name in metrics:
                    avail, err = availability.get(metric_name, (True, None))
                    results.append(
                        EvaluationResult(
                            metric_name=metric_name,
                            score=None,
                            error="no_suitable_examples",
                            available=avail,
                        )
                    )
                return EvaluationRun(
                    run_id=run_id,
                    timestamp=timestamp,
                    dataset_size=dataset.total_examples,
                    dataset_source=dataset.source_file or "unknown",
                    model_provider=self.model_provider,
                    model_model=self.model_model,
                    metrics_requested=metrics,
                    results=results,
                    ragas_available=True,
                    notes=notes,
                )

            # Map metric names to RAGAS metric classes (instantiated instances).
            ragas_metric_instances = self._map_metrics(metrics)

            # Filter metrics to only those that could be instantiated.
            computable_metrics = [
                m
                for m in metrics
                if any(
                    inst.__class__.__name__
                    == METRIC_DEFINITIONS[m].ragas_metric_name
                    for inst in ragas_metric_instances
                )
            ]

            # Run RAGAS evaluation.
            eval_result = ragas_evaluate(
                dataset=samples,
                metrics=ragas_metric_instances,
                llm=self.llm,
            )

            # Parse results - RAGAS returns a Result object or dict.
            result_data = self._parse_ragas_result(eval_result, computable_metrics)

            for metric_name in metrics:
                if metric_name in result_data:
                    score, error = result_data[metric_name]
                    results.append(
                        EvaluationResult(
                            metric_name=metric_name,
                            score=score,
                            error=error,
                            available=error is None,
                        )
                    )
                else:
                    avail, err = availability.get(metric_name, (True, None))
                    results.append(
                        EvaluationResult(
                            metric_name=metric_name,
                            score=None,
                            error=err or "no_result_returned",
                            available=avail,
                        )
                    )

            notes = f"RAGAS evaluation completed for {len(samples)} samples."

        except Exception as exc:  # noqa: BLE001
            notes = f"RAGAS evaluation failed: {exc}"
            for metric_name in metrics:
                avail, err = availability.get(metric_name, (True, None))
                results.append(
                    EvaluationResult(
                        metric_name=metric_name,
                        score=None,
                        error=str(exc),
                        available=avail,
                    )
                )

        return EvaluationRun(
            run_id=run_id,
            timestamp=timestamp,
            dataset_size=dataset.total_examples,
            dataset_source=dataset.source_file or "unknown",
            model_provider=self.model_provider,
            model_model=self.model_model,
            metrics_requested=metrics,
            results=results,
            ragas_available=ragas_available,
            notes=notes,
        )

    def _to_ragas_samples(
        self,
        dataset: EvaluationDataset,
        metrics: list[str],
    ) -> list[Any]:
        """Convert evaluation examples to RAGAS sample objects.

        Only includes examples that have the fields required by the
        requested metrics. Examples without generated answers are skipped
        for metrics that require an answer.
        """
        if not _RAGAS_IMPORTED:
            return []

        # Determine which fields are needed.
        needed_fields: set[str] = set()
        for metric_name in metrics:
            definition = METRIC_DEFINITIONS[metric_name]
            needed_fields.update(definition.required_fields)

        samples: list[Any] = []
        for example in dataset.examples:
            # Skip examples without generated answers if any metric needs one.
            if "answer" in needed_fields and not example.generated_answer:
                continue
            if "ground_truth" in needed_fields and not example.reference_answer:
                continue

            sample = SingleTurnSample(
                question=example.question,
                answer=example.generated_answer or "",
                contexts=example.retrieved_contexts,
                ground_truth=example.reference_answer or "",
            )
            samples.append(sample)

        return samples

    def _map_metrics(self, metrics: list[str]) -> list[Any]:
        """Map metric names to instantiated RAGAS metric objects.

        Only returns instances for metrics that can be successfully
        initialized. Metrics that fail initialization are excluded from
        the returned list but remain in `metrics_requested` for reporting.

        Uses the deprecated ragas.metrics path (not collections) because
        collections metrics require InstructorLLM (OpenAI-specific).
        AnswerSimilarity does not accept an llm argument; all other metrics
        receive llm=_DEEPSEEK_LLM.
        """
        if not _RAGAS_IMPORTED:
            return []

        metric_instances: list[Any] = []

        for metric_name in metrics:
            definition = METRIC_DEFINITIONS[metric_name]
            ragas_class_name = definition.ragas_metric_name
            if ragas_class_name is None:
                continue

            instance = None

            # Use deprecated ragas.metrics path (collections requires
            # InstructorLLM which is OpenAI-specific).
            try:
                from ragas.metrics import (  # type: ignore[import-not-found]
                    Faithfulness,
                    AnswerRelevancy,
                    ContextPrecision,
                    ContextRecall,
                    AnswerSimilarity,
                )

                deprecated_map = {
                    "Faithfulness": Faithfulness,
                    "AnswerRelevancy": AnswerRelevancy,
                    "ContextPrecision": ContextPrecision,
                    "ContextRecall": ContextRecall,
                    "AnswerSimilarity": AnswerSimilarity,
                }
                cls = deprecated_map.get(ragas_class_name)
                if cls is not None:
                    if ragas_class_name == "AnswerSimilarity":
                        instance = cls()
                    else:
                        instance = cls(llm=_DEEPSEEK_LLM)
                    metric_instances.append(instance)
            except Exception:  # noqa: BLE001
                pass

        return metric_instances

    def _parse_ragas_result(
        self,
        result: Any,
        metrics: list[str],
    ) -> dict[str, tuple[float | None, str | None]]:
        """Parse RAGAS evaluation result into per-metric scores.

        RAGAS result formats vary by version. This handles both dict-like
        and object-like results.
        """
        output: dict[str, tuple[float | None, str | None]] = {}

        # Try to extract scores from various result formats.
        result_dict: dict[str, Any] = {}

        if hasattr(result, "to_dict"):
            try:
                result_dict = result.to_dict()
            except Exception:
                result_dict = {}
        elif hasattr(result, "__getitem__"):
            try:
                result_dict = dict(result)
            except Exception:
                result_dict = {}
        elif isinstance(result, dict):
            result_dict = result

        # RAGAS may nest scores under metric names or under a "scores" key.
        scores_container = result_dict
        if "scores" in result_dict and isinstance(result_dict["scores"], dict):
            scores_container = result_dict["scores"]

        for metric_name in metrics:
            definition = METRIC_DEFINITIONS[metric_name]
            ragas_name = definition.ragas_metric_name or metric_name

            score = None
            error = None

            # Try multiple key formats.
            for key in (metric_name, ragas_name, metric_name.lower()):
                if key in scores_container:
                    val = scores_container[key]
                    if isinstance(val, (int, float)):
                        score = float(val)
                        break
                    elif isinstance(val, dict) and "score" in val:
                        score = float(val["score"])
                        break

            if score is None:
                error = f"no score found for metric {metric_name}"

            output[metric_name] = (score, error)

        return output


def evaluate_rag_response(
    question: str,
    answer: str,
    contexts: list[str],
    reference_answer: str | None = None,
    model_provider: str = "deepseek",
    model_model: str = "deepseek-chat",
    metrics: list[str] | None = None,
) -> EvaluationRun:
    """Convenience function to evaluate a single RAG response.

    Creates a single-example dataset and runs evaluation. Useful for
    quick checks without managing a full dataset.

    Args:
        question: The user question.
        answer: The generated answer.
        contexts: Retrieved context chunks.
        reference_answer: Optional ground-truth answer.
        model_provider: LLM provider name.
        model_model: Model name.
        metrics: Metrics to compute.

    Returns:
        EvaluationRun with per-metric results.
    """
    example = EvaluationExample(
        question=question,
        reference_answer=reference_answer,
        retrieved_contexts=contexts,
        generated_answer=answer,
    )
    dataset = EvaluationDataset(examples=[example])
    evaluator = RagasEvaluator(
        model_provider=model_provider,
        model_model=model_model,
    )
    return evaluator.evaluate(dataset, metrics=metrics)
