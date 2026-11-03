"""RAGAS evaluation package for Phase 3 V2.

Provides a repeatable evaluation harness for grounded RAG quality:
faithfulness, answer relevancy, and context precision.

RAGAS is an optional dependency. When not installed, the package degrades
gracefully: dataset loading and metric definitions work offline, but actual
RAGAS evaluation runs require `pip install ragas`.

Important distinction: RAGAS being *importable* is not the same as RAGAS
metrics being *initializable*. Use :func:`is_available` to check whether at
least one metric class can be instantiated, and :func:`get_metric_availability`
for per-metric details.
"""

from .dataset import EvaluationDataset, EvaluationExample, load_dataset_from_csv
from .deepseek_llm import DeepSeekLLM, create_deepseek_llm
from .metrics import (
    METRIC_DEFINITIONS,
    available_metrics,
    get_metric_availability,
    is_available,
    metric_definition,
    probe_all_metrics,
)
from .evaluator import (
    EvaluationRun,
    EvaluationResult,
    RagasEvaluator,
    evaluate_rag_response,
)

__all__ = [
    "EvaluationDataset",
    "EvaluationExample",
    "load_dataset_from_csv",
    "DeepSeekLLM",
    "create_deepseek_llm",
    "METRIC_DEFINITIONS",
    "available_metrics",
    "get_metric_availability",
    "is_available",
    "probe_all_metrics",
    "metric_definition",
    "EvaluationRun",
    "EvaluationResult",
    "RagasEvaluator",
    "evaluate_rag_response",
]
