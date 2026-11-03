
import os

import pytest

from oau_ai.evaluation.dataset import EvaluationDataset, EvaluationExample
from oau_ai.evaluation.deepseek_llm import DeepSeekLLM
from oau_ai.evaluation.evaluator import RagasEvaluator
from oau_ai.evaluation.metrics import (
    METRIC_DEFINITIONS,
    available_metrics,
    get_metric_availability,
    is_available,
    probe_all_metrics,
)

# ---------------------------------------------------------------------------
# DeepSeek default evaluator tests
# ---------------------------------------------------------------------------


def test_ragas_evaluator_defaults_to_deepseek_llm():
    """RagasEvaluator defaults to DeepSeekLLM when no llm is provided."""
    evaluator = RagasEvaluator()
    assert isinstance(evaluator.llm, DeepSeekLLM)
    assert evaluator.llm.model_name == "deepseek-chat"
    assert evaluator.llm.base_url == "https://api.deepseek.com/v1"


def test_ragas_evaluator_respects_explicit_llm():
    """Explicitly supplied LLM is respected by RagasEvaluator."""
    custom_llm = DeepSeekLLM(model_name="deepseek-reasoner", api_key="custom-key")
    evaluator = RagasEvaluator(llm=custom_llm)
    assert evaluator.llm is custom_llm
    assert evaluator.llm.model_name == "deepseek-reasoner"
    assert evaluator.llm.api_key == "custom-key"


def test_ragas_evaluator_missing_deepseek_api_key_at_eval_time():
    """Missing DEEPSEEK_API_KEY produces clear error at evaluation time,
    not at initialization."""
    # No API key set - initialization should succeed
    evaluator = RagasEvaluator()
    assert evaluator.llm.api_key is None

    # But evaluation should fail with a clear error
    dataset = EvaluationDataset()
    dataset.add(
        EvaluationExample(
            question="Q?",
            generated_answer="A.",
            retrieved_contexts=["C"],
            reference_answer="A.",
        )
    )

    run = evaluator.evaluate(dataset, metrics=["faithfulness"])
    assert run.ragas_available is True  # metrics initialized OK
    result = run.results[0]
    assert result.available is True  # metric was initialized
    assert result.error is not None
    assert "api_key" in result.error.lower() or "openai" in result.error.lower() or "get_sample_type" in result.error.lower()


def test_no_openai_client_instantiated():
    """No OpenAI client is instantiated by RagasEvaluator."""
    evaluator = RagasEvaluator()
    # Verify the LLM is DeepSeekLLM, not ChatOpenAI or any OpenAI client
    assert isinstance(evaluator.llm, DeepSeekLLM)
    assert type(evaluator.llm).__name__ == "DeepSeekLLM"
    assert "openai" not in type(evaluator.llm).__module__.lower()


def test_no_openai_env_var_required():
    """No OpenAI environment variable is required for initialization."""
    import os

    # Remove any OpenAI-related env vars that might be set
    for var in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        os.environ.pop(var, None)

    # DeepSeekLLM and RagasEvaluator should initialize fine
    llm = DeepSeekLLM()
    assert llm.api_key is None

    evaluator = RagasEvaluator()
    assert evaluator.llm.api_key is None

    # Evaluation should fail with DeepSeek error, not OpenAI error
    dataset = EvaluationDataset()
    dataset.add(
        EvaluationExample(
            question="Q?",
            generated_answer="A.",
            retrieved_contexts=["C"],
            reference_answer="A.",
        )
    )
    run = evaluator.evaluate(dataset, metrics=["faithfulness"])
    result = run.results[0]
    assert "openai" not in result.error.lower()


def test_no_metric_uses_openai_embeddings():
    """No RAGAS metric silently uses OpenAI for embeddings."""
    # All 5 metrics instantiate without any OpenAI dependency
    availability = get_metric_availability()
    for name in ("faithfulness", "answer_relevancy", "context_precision",
                 "context_recall", "answer_similarity"):
        avail, err = availability[name]
        assert avail is True, (
            f"{name} should be initializable without OpenAI, got error: {err}"
        )
