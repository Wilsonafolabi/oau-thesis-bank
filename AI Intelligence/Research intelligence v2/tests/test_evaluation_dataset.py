"""Tests for the RAGAS evaluation dataset module.

These tests work offline without RAGAS installed. They verify dataset
schema, CSV loading, example creation, and seed dataset correctness.
"""

import os
from unittest.mock import patch

import pytest

from oau_ai.evaluation.dataset import (
    DEFAULT_CSV_PATH,
    EvaluationDataset,
    EvaluationExample,
    load_dataset_from_csv,
    seed_dataset,
)


def test_evaluation_example_creation():
    """EvaluationExample can be created with required fields."""
    ex = EvaluationExample(
        question="What is X?",
        reference_answer="X is Y.",
        retrieved_contexts=["Context about X"],
        generated_answer="X is Y based on the evidence.",
        source_ids=[("chunk-1", "doc-1", "thesis-1")],
        metadata={"thesis_title": "Thesis X"},
    )
    assert ex.question == "What is X?"
    assert ex.reference_answer == "X is Y."
    assert len(ex.retrieved_contexts) == 1
    assert ex.generated_answer == "X is Y based on the evidence."
    assert len(ex.source_ids) == 1
    assert ex.metadata["thesis_title"] == "Thesis X"


def test_evaluation_example_to_ragas_dict():
    """to_ragas_dict returns RAGAS-compatible keys."""
    ex = EvaluationExample(
        question="Q?",
        reference_answer="A.",
        retrieved_contexts=["C1", "C2"],
        generated_answer="G.",
        source_ids=[],
    )
    d = ex.to_ragas_dict()
    assert d["question"] == "Q?"
    assert d["answer"] == "G."
    assert d["contexts"] == ["C1", "C2"]
    assert d["ground_truth"] == "A."


def test_evaluation_example_to_ragas_dict_missing_values():
    """to_ragas_dict handles missing values with empty strings."""
    ex = EvaluationExample(
        question="Q?",
        reference_answer=None,
        retrieved_contexts=[],
        generated_answer=None,
        source_ids=[],
    )
    d = ex.to_ragas_dict()
    assert d["answer"] == ""
    assert d["contexts"] == []
    assert d["ground_truth"] == ""


def test_evaluation_dataset_add_and_count():
    """EvaluationDataset tracks example count correctly."""
    ds = EvaluationDataset()
    assert ds.total_examples == 0

    ex = EvaluationExample(question="Q1?")
    ds.add(ex)
    assert ds.total_examples == 1

    ex2 = EvaluationExample(question="Q2?", reference_answer="A2")
    ds.add(ex2)
    assert ds.total_examples == 2


def test_evaluation_dataset_examples_with_references():
    """examples_with_references filters correctly."""
    ds = EvaluationDataset()
    ds.add(EvaluationExample(question="Q1?", reference_answer="A1"))
    ds.add(EvaluationExample(question="Q2?", reference_answer=None))
    ds.add(EvaluationExample(question="Q3?", reference_answer="A3"))

    with_refs = ds.examples_with_references()
    assert len(with_refs) == 2
    assert all(ex.reference_answer for ex in with_refs)

    without_refs = ds.examples_without_references()
    assert len(without_refs) == 1
    assert without_refs[0].question == "Q2?"


def test_evaluation_dataset_to_ragas_dataset():
    """to_ragas_dataset converts all examples to RAGAS dicts."""
    ds = EvaluationDataset()
    ds.add(
        EvaluationExample(
            question="Q1?",
            reference_answer="A1",
            retrieved_contexts=["C1"],
            generated_answer="G1",
        )
    )
    ds.add(EvaluationExample(question="Q2?"))

    ragas_ds = ds.to_ragas_dataset()
    assert len(ragas_ds) == 2
    assert ragas_ds[0]["question"] == "Q1?"
    assert ragas_ds[0]["answer"] == "G1"
    assert ragas_ds[1]["answer"] == ""


def test_seed_dataset_has_examples():
    """Seed dataset returns a non-empty list of curated examples."""
    ds = seed_dataset()
    assert ds.total_examples > 0
    assert ds.source_file == "curated-seed"

    for ex in ds.examples:
        assert ex.question
        assert ex.reference_answer
        assert len(ex.retrieved_contexts) > 0
        assert len(ex.source_ids) > 0
        assert ex.metadata.get("thesis_title")


def test_seed_dataset_answers_verifiable():
    """Seed dataset answers are verifiable against context text."""
    ds = seed_dataset()
    for ex in ds.examples:
        # Each example should have a reference answer that appears in
        # at least one of its contexts (verifiable provenance).
        context_text = " ".join(ex.retrieved_contexts).lower()
        answer_words = ex.reference_answer.lower().split()
        # At least one content word from the answer should appear in context.
        content_words = [w for w in answer_words if len(w) > 3]
        assert any(w in context_text for w in content_words), (
            f"Answer not verifiable: {ex.reference_answer}"
        )


def test_load_dataset_from_csv_returns_dataset():
    """load_dataset_from_csv returns an EvaluationDataset."""
    ds = load_dataset_from_csv(max_examples=5)
    assert isinstance(ds, EvaluationDataset)
    assert ds.total_examples <= 5
    assert ds.source_file == DEFAULT_CSV_PATH


def test_load_dataset_from_csv_missing_file_falls_back_to_seed():
    """Missing CSV falls back to curated seed dataset."""
    ds = load_dataset_from_csv(csv_path="/nonexistent/path.csv", max_examples=10)
    assert isinstance(ds, EvaluationDataset)
    assert ds.source_file == "curated-seed"
    assert ds.total_examples > 0


def test_load_dataset_from_csv_examples_have_contexts():
    """Examples loaded from CSV have non-empty contexts."""
    ds = load_dataset_from_csv(max_examples=10)
    for ex in ds.examples[:5]:
        assert len(ex.retrieved_contexts) > 0
        assert ex.retrieved_contexts[0].strip() != ""


def test_load_dataset_from_csv_respects_max_examples():
    """max_examples limits the number of loaded examples."""
    ds = load_dataset_from_csv(max_examples=3)
    assert ds.total_examples <= 3


def test_default_csv_path_exists():
    """The default CSV path points to an existing file."""
    assert os.path.exists(DEFAULT_CSV_PATH), (
        f"Default CSV not found at {DEFAULT_CSV_PATH}"
    )


def test_evaluation_example_source_ids_format():
    """source_ids contains (chunk_id, document_id, backend_thesis_id) tuples."""
    ex = EvaluationExample(
        question="Q?",
        source_ids=[("chunk-abc", "doc-def", "thesis-xyz")],
    )
    assert len(ex.source_ids) == 1
    cid, did, tid = ex.source_ids[0]
    assert cid == "chunk-abc"
    assert did == "doc-def"
    assert tid == "thesis-xyz"
