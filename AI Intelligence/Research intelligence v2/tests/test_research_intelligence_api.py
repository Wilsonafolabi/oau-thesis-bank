"""Tests for the Research Intelligence API surface.

Covers the agent endpoint and the newly exposed memory / entity /
relationship (researcher-network) endpoints. Heavy dependencies (agent graph,
DeepSeek, entity extraction) are mocked at the service boundary; auth,
validation, and response shape are exercised through the real router.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from oau_ai.agent.state import AgentState
from oau_ai.main import app

AUTH_HEADERS = {
    "Authorization": "Bearer test-internal-token-123",
    "x-user-id": "user-123",
    "x-roles": "student,researcher",
    "x-department": "Computer Science",
    "x-trace-id": "trace-abc-123",
}


@pytest.fixture(autouse=True)
def set_internal_token():
    os.environ["BACKEND_API_INTERNAL_TOKEN"] = "test-internal-token-123"
    yield
    del os.environ["BACKEND_API_INTERNAL_TOKEN"]


def _mock_session():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def _patch_session():
    return patch("oau_ai.api.routes.AsyncSessionLocal", return_value=_mock_session())


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def test_agent_ask_requires_service_token():
    client = TestClient(app)
    resp = client.post("/api/v2/agent/ask", json={"question": "Hello"})
    assert resp.status_code == 401


def test_agent_ask_empty_question_returns_422():
    client = TestClient(app)
    resp = client.post(
        "/api/v2/agent/ask",
        json={"question": ""},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422


def test_agent_ask_success():
    state = AgentState(question="q", actor_context={}, trace_id="trace-abc-123")
    state["final_answer"] = "grounded answer"
    state["citations"] = [{"chunk_id": "c1", "document_id": "d1"}]
    state["confidence"] = 0.9
    state["insufficient_evidence"] = False
    state["status"] = "complete"
    state["iteration_count"] = 2
    state["error"] = None

    with patch("oau_ai.api.routes.run_agent", new=AsyncMock(return_value=state)):
        client = TestClient(app)
        resp = client.post(
            "/api/v2/agent/ask",
            json={"question": "What is machine learning?"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "grounded answer"
    assert data["confidence"] == 0.9
    assert data["status"] == "complete"
    assert data["iteration_count"] == 2


# ---------------------------------------------------------------------------
# Working memory
# ---------------------------------------------------------------------------


def test_add_working_memory_requires_service_token():
    client = TestClient(app)
    resp = client.post(
        "/api/v2/memory/working",
        json={"exchange_type": "user_message", "content": "hello"},
    )
    assert resp.status_code == 401


def test_add_working_memory_success():
    with _patch_session(), patch(
        "oau_ai.api.routes.MemoryService.add_working_memory_exchange",
        new=AsyncMock(return_value="exchange-1"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v2/memory/working",
            json={
                "exchange_type": "user_message",
                "content": "I am researching ML fairness.",
                "unresolved_questions": ["which metric?"],
            },
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["exchange_id"] == "exchange-1"
    assert data["user_id"] == "user-123"


def test_get_working_memory_context_success():
    with _patch_session(), patch(
        "oau_ai.api.routes.MemoryService.get_working_memory_context",
        new=AsyncMock(return_value="[user_message] I am researching ML fairness."),
    ):
        client = TestClient(app)
        resp = client.get("/api/v2/memory/working/context", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "user-123"
    assert "ML fairness" in data["context"]


# ---------------------------------------------------------------------------
# Entities and relationships (researcher network)
# ---------------------------------------------------------------------------


def test_extract_entities_requires_service_token():
    client = TestClient(app)
    resp = client.post("/api/v2/memory/entities/extract", json={"text": "ML"})
    assert resp.status_code == 401


def test_extract_entities_empty_text_returns_422():
    client = TestClient(app)
    resp = client.post(
        "/api/v2/memory/entities/extract",
        json={"text": ""},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422


def test_extract_entities_success():
    extracted = [
        {
            "id": "e1",
            "entity_type": "topic",
            "entity_name": "Machine Learning",
            "normalized_name": "machine learning",
            "confidence": 0.8,
            "action": "created",
        }
    ]
    with _patch_session(), patch(
        "oau_ai.api.routes.MemoryService.extract_entities",
        new=AsyncMock(return_value=extracted),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v2/memory/entities/extract",
            json={"text": "I study machine learning fairness."},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entities"][0]["entity_name"] == "Machine Learning"


def test_list_entities_success():
    entity = SimpleNamespace(
        id="e1",
        user_id="user-123",
        entity_type="topic",
        entity_name="Machine Learning",
        normalized_name="machine learning",
        description="A field of AI",
        confidence="0.8",
        occurrence_count=2,
    )
    with _patch_session(), patch(
        "oau_ai.api.routes.MemoryService.list_entities",
        new=AsyncMock(return_value=[entity]),
    ):
        client = TestClient(app)
        resp = client.get("/api/v2/memory/entities", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entities"][0]["entity_name"] == "Machine Learning"


def test_add_relationship_success():
    with _patch_session(), patch(
        "oau_ai.api.routes.MemoryService.add_entity_relationship",
        new=AsyncMock(return_value="rel-1"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v2/memory/relationships",
            json={
                "source_entity_id": "e1",
                "target_entity_id": "e2",
                "relationship_type": "relates_to",
                "confidence": 0.7,
            },
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200
    assert resp.json()["relationship_id"] == "rel-1"


def test_list_relationships_success():
    rel = SimpleNamespace(
        id="rel-1",
        user_id="user-123",
        source_entity_id="e1",
        target_entity_id="e2",
        relationship_type="relates_to",
        confidence="0.7",
    )
    with _patch_session(), patch(
        "oau_ai.api.routes.MemoryService.list_relationships",
        new=AsyncMock(return_value=[rel]),
    ):
        client = TestClient(app)
        resp = client.get("/api/v2/memory/relationships", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["relationships"][0]["relationship_type"] == "relates_to"


# ---------------------------------------------------------------------------
# General-knowledge assistant
# ---------------------------------------------------------------------------


class _FakeRouter:
    async def acomplete_deepseek(self, request):
        return SimpleNamespace(content="Hello from general chat")

    async def acomplete_groq_designated(self, request, designation):
        return SimpleNamespace(content="Hello from Groq")


def test_assistant_chat_requires_service_token():
    client = TestClient(app)
    resp = client.post(
        "/api/v2/assistant/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


def test_assistant_chat_invalid_provider_returns_400():
    client = TestClient(app)
    resp = client.post(
        "/api/v2/assistant/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "provider": "openai"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


def test_assistant_chat_success_deepseek():
    with patch(
        "oau_ai.api.routes._assistant_blocked_by_safety",
        new=AsyncMock(return_value=False),
    ), patch("oau_ai.api.routes.get_router", return_value=_FakeRouter()):
        client = TestClient(app)
        resp = client.post(
            "/api/v2/assistant/chat",
            json={"messages": [{"role": "user", "content": "What is ML?"}]},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Hello from general chat"
    assert data["mode"] == "general"
    assert data["provider"] == "deepseek"


def test_assistant_chat_groq_selected():
    with patch(
        "oau_ai.api.routes._assistant_blocked_by_safety",
        new=AsyncMock(return_value=False),
    ), patch("oau_ai.api.routes.get_router", return_value=_FakeRouter()):
        client = TestClient(app)
        resp = client.post(
            "/api/v2/assistant/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "provider": "groq"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["provider"] == "groq"
    assert resp.json()["answer"] == "Hello from Groq"


def test_assistant_chat_blocked_by_safety():
    with patch(
        "oau_ai.api.routes._assistant_blocked_by_safety",
        new=AsyncMock(return_value=True),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v2/assistant/chat",
            json={"messages": [{"role": "user", "content": "disallowed request"}]},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["message"] == "blocked_by_safety"
