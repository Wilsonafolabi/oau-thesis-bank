"""Tests for the RAGAS evaluation runner.

These tests work with the installed RAGAS package. They verify that the
evaluator correctly reports metric availability based on actual metric
class instantiation (not just package import), and handles both available
and unavailable metric scenarios.
"""

import pytest

from oau_ai.evaluation.dataset import EvaluationDataset, EvaluationExample
from oau_ai.evaluation.evaluator import (
    EvaluationResult,
    EvaluationRun,
    RagasEvaluator,
    evaluate_rag_response,
)
from oau_ai.evaluation.metrics import (
    METRIC_DEFINITIONS,
    available_metrics,
    get_metric_availability,
    is_available,
    probe_all_metrics,
)


def test_evaluator_initialization():
    """RagasEvaluator can be initialized with model metadata."""
    evaluator = RagasEvaluator(
        model_provider="deepseek",
        model_model="deepseek-chat",
    )
    assert evaluator.model_provider == "deepseek"
    assert evaluator.model_model == "deepseek-chat"


def test_evaluator_default_model():
    """RagasEvaluator defaults to deepseek provider."""
    evaluator = RagasEvaluator()
    assert evaluator.model_provider == "deepseek"
    assert evaluator.model_model == "deepseek-chat"


def test_is_available_matches_ragas_import():
    """is_available returns True when RAGAS metrics can be initialized."""
    # RAGAS is installed in this environment and metrics can be initialized.
    assert is_available() is True


def test_ragas_imported():
    """RAGAS package is importable in this environment."""
    import ragas

    assert ragas.__version__ == "0.4.3"


def test_get_metric_availability_returns_all_metrics():
    """get_metric_availability returns status for all defined metrics."""
    availability = get_metric_availability()
    assert isinstance(availability, dict)
    for name in METRIC_DEFINITIONS:
        assert name in availability
        avail, err = availability[name]
        assert isinstance(avail, bool)
        if not avail:
            assert err is not None, f"Metric {name} unavailable but no error"


def test_available_metrics_returns_initializable_metrics():
    """available_metrics returns only metrics that can be initialized."""
    availables = available_metrics()
    assert isinstance(availables, list)
    for name in availables:
        assert name in METRIC_DEFINITIONS
        # Verify each returned metric is actually initializable
        avail, err = get_metric_availability()[name]
        assert avail is True, f"Metric {name} in available_metrics but not initializable: {err}"


def test_probe_all_metrics():
    """probe_all_metrics returns availability for every defined metric."""
    results = probe_all_metrics()
    assert isinstance(results, dict)
    for name in METRIC_DEFINITIONS:
        assert name in results
        avail, err = results[name]
        assert isinstance(avail, bool)


def test_evaluate_with_ragas_available():
    """When RAGAS metrics are initialized, run.ragas_available is True.

    Note: actual metric computation may fail due to missing LLM API key,
    in which case result.available is False with an error message about
    the missing key. The important distinction is that ragas_available
    reflects successful metric initialization, not successful computation.
    """
    evaluator = RagasEvaluator()
    dataset = EvaluationDataset()
    dataset.add(EvaluationExample(question="Q?", generated_answer="A."))

    run = evaluator.evaluate(dataset, metrics=["faithfulness"])

    assert run.ragas_available is True
    assert len(run.results) == 1
    result = run.results[0]
    assert result.metric_name == "faithfulness"
    assert result.score is None
    assert result.error is not None
    assert "api_key" in result.error.lower() or "openai" in result.error.lower() or "get_sample_type" in result.error.lower()


def test_evaluate_unknown_metric_raises():
    """Evaluating with unknown metric names raises ValueError."""
    evaluator = RagasEvaluator()
    dataset = EvaluationDataset()
    dataset.add(EvaluationExample(question="Q?"))

    with pytest.raises(ValueError, match="Unknown metric"):
        evaluator.evaluate(dataset, metrics=["nonexistent_metric"])


def test_evaluate_empty_dataset():
    """Evaluating an empty dataset produces results for requested metrics."""
    evaluator = RagasEvaluator()
    dataset = EvaluationDataset()

    run = evaluator.evaluate(dataset, metrics=["faithfulness"])

    assert run.dataset_size == 0
    assert len(run.results) == 1
    assert run.results[0].metric_name == "faithfulness"
    # Metrics are initialized (available=True); just no data to evaluate
    assert run.results[0].available is True


def test_evaluation_run_to_dict():
    """EvaluationRun.to_dict produces a complete serializable dict."""
    evaluator = RagasEvaluator()
    dataset = EvaluationDataset()
    dataset.add(EvaluationExample(question="Q?", generated_answer="A."))

    run = evaluator.evaluate(dataset, metrics=["faithfulness"])
    d = run.to_dict()

    assert d["run_id"]
    assert d["timestamp"]
    assert d["dataset_size"] == 1
    assert d["model_provider"] == "deepseek"
    assert d["model_model"] == "deepseek-chat"
    assert d["metrics_requested"] == ["faithfulness"]
    assert d["ragas_available"] is True
    assert len(d["results"]) == 1


def test_evaluation_run_summary():
    """EvaluationRun.summary returns a compact summary."""
    evaluator = RagasEvaluator()
    dataset = EvaluationDataset()
    dataset.add(EvaluationExample(question="Q?", generated_answer="A."))

    run = evaluator.evaluate(dataset, metrics=["faithfulness"])
    summary = run.summary()

    assert summary["run_id"] == run.run_id
    assert summary["dataset_size"] == 1
    assert summary["ragas_available"] is True
    assert "scores" in summary


def test_evaluate_rag_response_convenience():
    """evaluate_rag_response creates a single-example evaluation."""
    run = evaluate_rag_response(
        question="What is X?",
        answer="X is Y.",
        contexts=["Context about X"],
        reference_answer="X is Y.",
    )

    assert isinstance(run, EvaluationRun)
    assert run.dataset_size == 1
    assert run.metrics_requested == available_metrics()


def test_evaluate_rag_response_with_metrics():
    """evaluate_rag_response accepts custom metrics."""
    run = evaluate_rag_response(
        question="Q?",
        answer="A.",
        contexts=["C"],
        metrics=["answer_relevancy"],
    )
    assert run.metrics_requested == ["answer_relevancy"]


def test_evaluation_result_to_dict():
    """EvaluationResult.to_dict is complete and serializable."""
    r = EvaluationResult(
        metric_name="faithfulness",
        score=0.85,
        error=None,
        available=True,
    )
    d = r.to_dict()
    assert d == {
        "metric_name": "faithfulness",
        "score": 0.85,
        "error": None,
        "available": True,
    }


def test_evaluation_result_unavailable():
    """EvaluationResult for unavailable metric has score=None."""
    r = EvaluationResult(
        metric_name="faithfulness",
        score=None,
        error="metric_initialization_failed",
        available=False,
    )
    assert r.score is None
    assert r.available is False
    assert r.error == "metric_initialization_failed"
