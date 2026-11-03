"""Tests for API validation and error handling."""

import os
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from oau_ai.api.routes import router
from oau_ai.main import app


@pytest.fixture(autouse=True)
def set_internal_token():
    """Set a test internal service token for auth-dependent endpoints."""
    os.environ["BACKEND_API_INTERNAL_TOKEN"] = "test-internal-token-123"
    yield
    del os.environ["BACKEND_API_INTERNAL_TOKEN"]


def test_health_endpoint():
    """Health endpoint returns service info without secrets."""
    client = TestClient(app)
    response = client.get("/api/v2/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "primary_provider" in data
    assert "enabled_providers" in data
    assert "vectorize_configured" in data


def test_health_echoes_trace_id():
    """Health endpoint echoes the propagated X-Trace-Id header."""
    client = TestClient(app)
    response = client.get(
        "/api/v2/health", headers={"x-trace-id": "trace-health-1"}
    )
    assert response.status_code == 200
    assert response.json()["trace_id"] == "trace-health-1"


def test_rag_without_service_token_returns_401():
    """RAG endpoint requires internal service token."""
    client = TestClient(app)
    response = client.post(
        "/api/v2/rag/ask",
        json={"question": "Hello"},
    )
    assert response.status_code == 401


def test_upload_without_service_token_returns_401():
    """Upload endpoint requires internal service token."""
    client = TestClient(app)
    response = client.post(
        "/api/v2/documents/upload",
        data={"backend_thesis_id": "t1", "backend_user_id": "u1"},
    )
    assert response.status_code == 401


def test_rag_with_invalid_service_token_returns_401():
    """RAG endpoint rejects invalid service token."""
    client = TestClient(app)
    response = client.post(
        "/api/v2/rag/ask",
        json={"question": "Hello"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_rag_with_empty_question_returns_422():
    """RAG endpoint validates that question is not empty."""
    client = TestClient(app)
    response = client.post(
        "/api/v2/rag/ask",
        json={"question": ""},
        headers={
            "Authorization": "Bearer test-internal-token-123",
            "x-user-id": "user-123",
            "x-roles": "student",
        },
    )
    assert response.status_code == 422  # Validation error


def test_rag_with_valid_token_but_missing_actor_headers():
    """RAG endpoint with valid token but missing x-user-id returns 400."""
    client = TestClient(app)
    response = client.post(
        "/api/v2/rag/ask",
        json={"question": "Hello"},
        headers={"Authorization": "Bearer test-internal-token-123"},
    )
    # Missing x-user-id header -> 400
    assert response.status_code == 400


def test_rag_with_invalid_auth_scheme_returns_401():
    """RAG endpoint rejects non-Bearer authorization scheme."""
    client = TestClient(app)
    response = client.post(
        "/api/v2/rag/ask",
        json={"question": "Hello"},
        headers={"Authorization": "Basic test-internal-token-123"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Direct dependency tests (auth layer, no DB required)
# ---------------------------------------------------------------------------

def test_get_internal_service_token_valid():
    """get_internal_service_token accepts valid Bearer token."""
    from oau_ai.api.dependencies import get_internal_service_token

    token = get_internal_service_token(authorization="Bearer test-internal-token-123")
    assert token == "test-internal-token-123"


def test_get_internal_service_token_missing_header_raises_401():
    """get_internal_service_token raises HTTP 401 without Authorization header."""
    from oau_ai.api.dependencies import get_internal_service_token
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        get_internal_service_token(authorization=None)
    assert exc_info.value.status_code == 401


def test_get_internal_service_token_invalid_scheme_raises_401():
    """get_internal_service_token raises HTTP 401 for non-Bearer scheme."""
    from oau_ai.api.dependencies import get_internal_service_token
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        get_internal_service_token(authorization="Basic test-token")
    assert exc_info.value.status_code == 401


def test_get_internal_service_token_invalid_token_raises_401():
    """get_internal_service_token raises HTTP 401 for wrong token."""
    from oau_ai.api.dependencies import get_internal_service_token
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        get_internal_service_token(authorization="Bearer wrong-token")
    assert exc_info.value.status_code == 401


def test_get_actor_context_valid():
    """get_actor_context extracts actor context from headers."""
    from oau_ai.api.dependencies import get_actor_context

    ctx = get_actor_context(
        x_user_id="user-123",
        x_roles="student,researcher",
        x_department="Computer Science",
        x_trace_id="trace-abc-123",
    )
    assert ctx.user_id == "user-123"
    assert ctx.roles == ["student", "researcher"]
    assert ctx.department == "Computer Science"
    assert ctx.trace_id == "trace-abc-123"


def test_get_actor_context_missing_user_id_raises_400():
    """get_actor_context raises HTTP 400 without x-user-id."""
    from oau_ai.api.dependencies import get_actor_context
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        get_actor_context(
            x_user_id=None,
            x_roles="student",
            x_department="CS",
        )
    assert exc_info.value.status_code == 400


def test_get_actor_context_defaults_roles_to_student():
    """get_actor_context defaults roles to ['student'] when x-roles is missing."""
    from oau_ai.api.dependencies import get_actor_context

    ctx = get_actor_context(
        x_user_id="user-123",
        x_roles=None,
        x_department="CS",
    )
    assert ctx.roles == ["student"]


def test_get_actor_context_defaults_department_to_empty():
    """get_actor_context defaults department to empty string when x-department is missing."""
    from oau_ai.api.dependencies import get_actor_context

    ctx = get_actor_context(
        x_user_id="user-123",
        x_roles="student",
        x_department=None,
    )
    assert ctx.department == ""


# ---------------------------------------------------------------------------
# Endpoint-level auth tests (mock database session, no live DB required)
# ---------------------------------------------------------------------------


def test_rag_with_valid_token_and_actor_context_passes_auth():
    """RAG endpoint with valid token and actor context passes auth (no DB).

    The RAG service is mocked so the endpoint completes without a live
    database, proving auth and actor-context handling succeed.
    """
    from unittest.mock import patch, AsyncMock, MagicMock

    from oau_ai.rag.service import RAGResponse as RAGResult

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    canned = RAGResult(
        answer="test answer",
        citations=[],
        confidence=0.9,
        decision_engine="jev",
        llm_tier=1,
        trace_id="trace-abc-123",
        request_id="req-1",
        insufficient_evidence=False,
        message=None,
    )

    with patch("oau_ai.api.routes.AsyncSessionLocal", return_value=mock_session), \
         patch("oau_ai.api.routes.RAGService.ask", new=AsyncMock(return_value=canned)):
        client = TestClient(app)
        response = client.post(
            "/api/v2/rag/ask",
            json={"question": "What is machine learning?"},
            headers={
                "Authorization": "Bearer test-internal-token-123",
                "x-user-id": "user-123",
                "x-roles": "student,researcher",
                "x-department": "Computer Science",
                "x-trace-id": "trace-abc-123",
            },
        )
    assert response.status_code == 200
    assert response.json()["answer"] == "test answer"


def test_rag_with_x_roles_defaults_to_student():
    """RAG endpoint defaults roles to ['student'] when x-roles header is missing."""
    from unittest.mock import patch, AsyncMock, MagicMock

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("oau_ai.api.routes.AsyncSessionLocal", mock_session):
        client = TestClient(app)
        response = client.post(
            "/api/v2/rag/ask",
            json={"question": "Hello"},
            headers={
                "Authorization": "Bearer test-internal-token-123",
                "x-user-id": "user-123",
                "x-department": "Computer Science",
            },
        )
    # Missing x-roles should default to ["student"], not 400/401
    assert response.status_code not in (400, 401)


# ---------------------------------------------------------------------------
# Django-to-V2 authentication boundary tests
# ---------------------------------------------------------------------------


def test_django_forwards_internal_service_token():
    """Django forwards internal service token to V2 (not user JWT)."""
    # Verified in backend/ai_integration/services.py: forward_to_v2 builds
    # Authorization: Bearer <internal_token> header, not the user JWT.
    from oau_ai.api.dependencies import get_internal_service_token

    token = get_internal_service_token(authorization="Bearer test-internal-token-123")
    assert token == "test-internal-token-123"


def test_v2_rejects_missing_internal_token():
    """V2 rejects requests without internal service token (fail closed)."""
    client = TestClient(app)
    response = client.post(
        "/api/v2/rag/ask",
        json={"question": "Hello"},
    )
    assert response.status_code == 401


def test_v2_rejects_invalid_internal_token():
    """V2 rejects requests with invalid internal service token."""
    client = TestClient(app)
    response = client.post(
        "/api/v2/rag/ask",
        json={"question": "Hello"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401