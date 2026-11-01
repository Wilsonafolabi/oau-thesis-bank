"""Tests for the RAGAS metric definitions module.

These tests work offline without RAGAS installed. They verify metric
definitions, availability checks, and metric lookup.
"""

import pytest

from oau_ai.evaluation.metrics import (
    METRIC_DEFINITIONS,
    MetricDefinition,
    available_metrics,
    is_available,
    metric_definition,
)


def test_metric_definitions_contain_expected_metrics():
    """METRIC_DEFINITIONS includes core RAGAS metrics."""
    expected = {"faithfulness", "answer_relevancy", "context_precision"}
    assert expected.issubset(set(METRIC_DEFINITIONS.keys()))


def test_faithfulness_definition():
    """Faithfulness metric definition has required fields."""
    m = METRIC_DEFINITIONS["faithfulness"]
    assert m.name == "faithfulness"
    assert "question" in m.required_fields
    assert "answer" in m.required_fields
    assert "contexts" in m.required_fields
    assert m.range == (0.0, 1.0)
    assert m.higher_is_better is True


def test_answer_relevancy_definition():
    """Answer relevancy metric definition."""
    m = METRIC_DEFINITIONS["answer_relevancy"]
    assert m.name == "answer_relevancy"
    assert "question" in m.required_fields
    assert "answer" in m.required_fields


def test_context_precision_definition():
    """Context precision metric definition requires ground_truth."""
    m = METRIC_DEFINITIONS["context_precision"]
    assert m.name == "context_precision"
    assert "question" in m.required_fields
    assert "contexts" in m.required_fields
    assert "ground_truth" in m.required_fields


def test_context_recall_definition():
    """Context recall metric definition."""
    m = METRIC_DEFINITIONS["context_recall"]
    assert m.name == "context_recall"
    assert "ground_truth" in m.required_fields


def test_answer_similarity_definition():
    """Answer similarity metric definition requires ground_truth."""
    m = METRIC_DEFINITIONS["answer_similarity"]
    assert m.name == "answer_similarity"
    assert "ground_truth" in m.required_fields


def test_metric_definition_lookup():
    """metric_definition returns the definition or None."""
    m = metric_definition("faithfulness")
    assert m is not None
    assert m.name == "faithfulness"

    assert metric_definition("nonexistent_metric") is None


def test_available_metrics_returns_list():
    """available_metrics returns a list (may be empty without RAGAS)."""
    result = available_metrics()
    assert isinstance(result, list)
    # All returned names should be in METRIC_DEFINITIONS
    for name in result:
        assert name in METRIC_DEFINITIONS


def test_is_available_returns_bool():
    """is_available returns a boolean."""
    result = is_available()
    assert isinstance(result, bool)


def test_metric_definition_is_frozen():
    """MetricDefinition is frozen (immutable)."""
    m = METRIC_DEFINITIONS["faithfulness"]
    with pytest.raises(Exception):
        m.name = "changed"


def test_all_metrics_have_required_fields():
    """Every metric definition has at least one required field."""
    for name, m in METRIC_DEFINITIONS.items():
        assert len(m.required_fields) > 0, (
            f"Metric {name} has no required fields"
        )
        assert "question" in m.required_fields, (
            f"Metric {name} should require 'question'"
        )


def test_all_metrics_have_valid_range():
    """Every metric definition has a valid 0-1 range."""
    for name, m in METRIC_DEFINITIONS.items():
        assert m.range == (0.0, 1.0), (
            f"Metric {name} has unexpected range {m.range}"
        )
