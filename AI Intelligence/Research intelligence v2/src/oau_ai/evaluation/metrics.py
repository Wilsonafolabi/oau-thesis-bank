"""RAGAS metric definitions for Phase 3 V2 evaluation.

Defines the RAG quality dimensions evaluated by the harness, including
faithfulness, answer relevancy, and context precision. When RAGAS is not
installed, metric definitions are still available for documentation and
offline validation, but actual metric computation requires `pip install ragas`.

Important distinction: RAGAS being *importable* is not the same as RAGAS
metrics being *initializable*. This module probes actual metric class
instantiation to report accurate availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import ragas  # type: ignore[import-not-found]

    _RAGAS_IMPORTED = True
except ImportError:  # pragma: no cover - depends on environment
    _RAGAS_IMPORTED = False

try:
    from .deepseek_llm import DeepSeekLLM

    _DEEPSEEK_LLM = DeepSeekLLM()
except ImportError:  # pragma: no cover - depends on environment
    _DEEPSEEK_LLM = None

# Cache of metric initialization probes: metric_name -> (available, error)
_METRIC_INIT_CACHE: dict[str, tuple[bool, Optional[str]]] = {}


@dataclass(frozen=True)
class MetricDefinition:
    """Definition of a single RAGAS metric.

    Attributes:
        name: Metric name (e.g., "faithfulness").
        description: Human-readable description of what the metric measures.
        ragas_metric_name: The RAGAS metric class name, or None if not
            available in the installed RAGAS version.
        required_fields: RAGAS input fields required by this metric.
        range: (min, max) score range.
        higher_is_better: Whether higher scores indicate better quality.
    """

    name: str
    description: str
    ragas_metric_name: Optional[str]
    required_fields: tuple[str, ...]
    range: tuple[float, float] = (0.0, 1.0)
    higher_is_better: bool = True


# Metric definitions for Phase 3 V2 evaluation.
# These map to RAGAS built-in metrics when RAGAS is installed.
METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "faithfulness": MetricDefinition(
        name="faithfulness",
        description=(
            "Measures whether the generated answer is factually consistent "
            "with the retrieved contexts. A faithful answer contains only "
            "information supported by the evidence."
        ),
        ragas_metric_name="Faithfulness",
        required_fields=("question", "answer", "contexts"),
    ),
    "answer_relevancy": MetricDefinition(
        name="answer_relevancy",
        description=(
            "Measures how relevant the generated answer is to the user "
            "question. Higher scores indicate the answer directly addresses "
            "the question without extraneous information."
        ),
        ragas_metric_name="AnswerRelevancy",
        required_fields=("question", "answer"),
    ),
    "context_precision": MetricDefinition(
        name="context_precision",
        description=(
            "Measures whether the retrieved contexts are relevant to the "
            "question. Higher scores indicate that relevant chunks are "
            "ranked higher and irrelevant chunks are excluded."
        ),
        ragas_metric_name="ContextPrecision",
        required_fields=("question", "contexts", "ground_truth"),
    ),
    "context_recall": MetricDefinition(
        name="context_recall",
        description=(
            "Measures whether the retrieved contexts contain all the "
            "information needed to answer the question. Higher scores "
            "indicate the retrieval captured the full evidence."
        ),
        ragas_metric_name="ContextRecall",
        required_fields=("question", "contexts", "ground_truth"),
    ),
    "answer_similarity": MetricDefinition(
        name="answer_similarity",
        description=(
            "Measures semantic similarity between the generated answer and "
            "the reference answer. Requires a reference answer to be available."
        ),
        ragas_metric_name="AnswerSimilarity",
        required_fields=("question", "answer", "ground_truth"),
    ),
}


def _probe_metric_initialization(metric_name: str) -> tuple[bool, Optional[str]]:
    """Try to instantiate a RAGAS metric class.

    Returns (True, None) if the metric class can be imported and
    instantiated, or (False, error_message) if initialization fails.

    Tries the non-deprecated `ragas.metrics.collections` path first,
    then falls back to the deprecated `ragas.metrics` path.
    """
    if metric_name in _METRIC_INIT_CACHE:
        return _METRIC_INIT_CACHE[metric_name]

    if not _RAGAS_IMPORTED:
        _METRIC_INIT_CACHE[metric_name] = (False, "ragas_not_installed")
        return _METRIC_INIT_CACHE[metric_name]

    definition = METRIC_DEFINITIONS.get(metric_name)
    if definition is None or definition.ragas_metric_name is None:
        _METRIC_INIT_CACHE[metric_name] = (False, "no_ragas_class_mapping")
        return _METRIC_INIT_CACHE[metric_name]

    ragas_class_name = definition.ragas_metric_name

    # Try deprecated ragas.metrics path first (collections path requires
    # InstructorLLM which is OpenAI-specific; we use DeepSeekLLM instead).
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
        if cls is not None and _DEEPSEEK_LLM is not None:
            # AnswerSimilarity does not accept an llm argument; others do.
            if ragas_class_name == "AnswerSimilarity":
                cls()  # type: ignore[call-arg]
            else:
                cls(llm=_DEEPSEEK_LLM)  # type: ignore[call-arg]
            _METRIC_INIT_CACHE[metric_name] = (True, None)
            return _METRIC_INIT_CACHE[metric_name]
        _METRIC_INIT_CACHE[metric_name] = (
            False,
            f"metric_class_{ragas_class_name}_not_found",
        )
        return _METRIC_INIT_CACHE[metric_name]
    except Exception as exc:  # noqa: BLE001 - report initialization failure
        _METRIC_INIT_CACHE[metric_name] = (False, f"init_failed: {exc}")
        return _METRIC_INIT_CACHE[metric_name]


def probe_all_metrics() -> dict[str, tuple[bool, Optional[str]]]:
    """Probe initialization of all defined metrics.

    Returns a dict mapping metric_name -> (available, error_message).
    """
    results: dict[str, tuple[bool, Optional[str]]] = {}
    for name in METRIC_DEFINITIONS:
        results[name] = _probe_metric_initialization(name)
    return results


def available_metrics() -> list[str]:
    """Return the list of metric names that can be computed.

    A metric is included only if RAGAS is installed AND its metric class
    can be successfully instantiated. Metric definitions remain available
    for documentation even when initialization fails.
    """
    return [
        name
        for name in METRIC_DEFINITIONS
        if _probe_metric_initialization(name)[0]
    ]


def get_metric_availability() -> dict[str, tuple[bool, Optional[str]]]:
    """Return availability status for all defined metrics.

    Returns a dict mapping metric_name -> (available, error_message).
    Useful for callers that need per-metric availability details.
    """
    return probe_all_metrics()


def metric_definition(name: str) -> Optional[MetricDefinition]:
    """Return the definition for a metric by name, or None if unknown."""
    return METRIC_DEFINITIONS.get(name)


def is_available() -> bool:
    """Return True if at least one RAGAS metric can be initialized.

    This is stricter than checking whether the `ragas` package is
    importable: it verifies that at least one metric class can be
    instantiated, which is required for actual metric computation.
    """
    return any(
        available for available, _ in probe_all_metrics().values()
    )
