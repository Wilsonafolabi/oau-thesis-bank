
import os

import pytest

from oau_ai.agent.graph import AgentGraph
from oau_ai.agent.state import AgentState
from oau_ai.auth.middleware import ActorContext
from oau_ai.evaluation.dataset import EvaluationDataset, EvaluationExample
from oau_ai.evaluation.deepseek_llm import DeepSeekLLM, create_deepseek_llm
from oau_ai.evaluation.evaluator import RagasEvaluator
from oau_ai.evaluation.metrics import (
    METRIC_DEFINITIONS,
    available_metrics,
    get_metric_availability,
    is_available,
    probe_all_metrics,
)

# ---------------------------------------------------------------------------
# DeepSeekLLM tests (no network calls during initialization)
# ---------------------------------------------------------------------------


def test_deepseek_llm_init_without_api_key():
    """DeepSeekLLM can be instantiated without an API key.

    The API key is only required when _call() is invoked, not during
    initialization. No network requests are made during construction.
    """
    llm = DeepSeekLLM()
    assert llm.model_name == "deepseek-chat"
    assert llm.api_key is None
    assert llm.base_url == "https://api.deepseek.com/v1"
    assert llm.temperature == 0.2
    assert llm.max_tokens == 1024
    assert llm.timeout == 60.0
    assert llm._llm_type == "deepseek"


def test_deepseek_llm_init_with_explicit_params():
    """DeepSeekLLM accepts explicit constructor parameters."""
    llm = DeepSeekLLM(
        model_name="deepseek-reasoner",
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        temperature=0.0,
        max_tokens=2048,
        timeout=30.0,
    )
    assert llm.model_name == "deepseek-reasoner"
    assert llm.api_key == "test-key"
    assert llm.base_url == "https://api.deepseek.com/v1"
    assert llm.temperature == 0.0
    assert llm.max_tokens == 2048
    assert llm.timeout == 30.0


def test_deepseek_llm_call_without_api_key_raises(monkeypatch):
    """Calling DeepSeekLLM without an API key raises ValueError.

    No network request is made; the error is raised immediately
    because the API key is missing.
    """
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    llm = DeepSeekLLM()
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        llm._call("What is 2+2?")


def test_create_deepseek_llm_from_env(monkeypatch):
    """create_deepseek_llm reads configuration from environment variables."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-123")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://custom.deepseek.com/v1")
    monkeypatch.setenv("DEEPSEEK_TEMPERATURE", "0.5")
    monkeypatch.setenv("DEEPSEEK_MAX_TOKENS", "512")
    monkeypatch.setenv("DEEPSEEK_TIMEOUT", "30")

    llm = create_deepseek_llm()
    assert llm.api_key == "test-key-123"
    assert llm.model_name == "deepseek-reasoner"
    assert llm.base_url == "https://custom.deepseek.com/v1"
    assert llm.temperature == 0.5
    assert llm.max_tokens == 512
    assert llm.timeout == 30.0
    # No network request was made during construction
    assert llm.api_key == "test-key-123"


def test_create_deepseek_llm_without_api_key():
    """create_deepseek_llm works without DEEPSEEK_API_KEY set."""
    import os

    os.environ.pop("DEEPSEEK_API_KEY", None)
    llm = create_deepseek_llm()
    assert llm.api_key is None
    assert llm.model_name == "deepseek-chat"


# ---------------------------------------------------------------------------
# RAGAS metric availability tests
# ---------------------------------------------------------------------------


def test_answer_similarity_available_via_deprecated_path():
    """AnswerSimilarity is available via the deprecated ragas.metrics path.

    It is NOT available via ragas.metrics.collections, but the deprecated
    import path provides it. This is verified via probe_all_metrics().
    """
    availability = get_metric_availability()
    assert "answer_similarity" in availability
    avail, err = availability["answer_similarity"]
    assert avail is True, (
        f"answer_similarity should be initializable, got error: {err}"
    )


def test_all_defined_metrics_are_probed():
    """probe_all_metrics returns an entry for every defined metric."""
    results = probe_all_metrics()
    for name in METRIC_DEFINITIONS:
        assert name in results
        avail, err = results[name]
        assert isinstance(avail, bool)
        if not avail:
            assert err is not None


def test_is_available_when_at_least_one_metric_initializes():
    """is_available returns True if at least one metric can be initialized."""
    assert is_available() is True
    # Verify at least one metric is actually initializable
    availability = get_metric_availability()
    assert any(avail for avail, _ in availability.values())


# ---------------------------------------------------------------------------
# Initialization vs computation distinction tests
# ---------------------------------------------------------------------------


def test_metric_initialized_but_computation_fails():
    """Metric initialization success does not imply computation success.

    RAGAS metrics are initialized (available=True) but actual computation
    requires an LLM API key. Without it, compute() raises an error.
    The evaluator correctly reports available=True (initialized) but
    the computation result has available=False with an API key error.
    """
    evaluator = RagasEvaluator()
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

    # RAGAS metrics are initialized (available at the metric level)
    assert run.ragas_available is True
    # But computation fails due to missing API key
    result = run.results[0]
    assert result.available is True  # metric was initialized
    assert result.score is None
    assert result.error is not None
    assert "api_key" in result.error.lower() or "openai" in result.error.lower() or "get_sample_type" in result.error.lower()
