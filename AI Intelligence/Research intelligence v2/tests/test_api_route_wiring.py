"""Route-wiring regression tests for the P4/P5 endpoints.

These drive the real FastAPI application over ASGI. Service entry points are
stubbed, so the assertions are about what this file is defending:

* the endpoint function is actually reachable (no missing imports, no NameError
  at call time — the exact defect that made similarity and plagiarism return
  500 while every service-level test passed);
* the response is validated against the declared schema;
* the documented status codes are produced.

Database access is replaced with an inert session, so no live records are read.
"""

import os

os.environ.setdefault("BACKEND_API_INTERNAL_TOKEN", "test-token")

import httpx
import pytest

from oau_ai.ai_writing.service import AITextDetectionResult
from oau_ai.api import routes
from oau_ai.recommendations.service import RecommendationResponse
from oau_ai.research_gap.service import ResearchGapResponse
from oau_ai.similarity.service import PlagiarismAssessment, SimilarityResult
from oau_ai.topics.service import TopicAnalysis

HEADERS = {
    "Authorization": "Bearer test-token",
    "X-User-Id": "42",
    "X-Roles": "student",
    "X-Department": "Computer Science",
    "X-Trace-Id": "trace-test",
}


class _InertSession:
    """Async context manager that never touches a database."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def close(self):
        return None


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # The token is read from the environment per request, and other test
    # modules clear it. Set it here so this file is order-independent.
    monkeypatch.setenv("BACKEND_API_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(routes, "AsyncSessionLocal", lambda: _InertSession())


@pytest.mark.asyncio
async def test_similarity_route_is_wired(monkeypatch):
    async def fake_compare(self, actor, text, **kwargs):
        return SimilarityResult(
            input_mode="text",
            passages_scanned=1,
            chunks_scanned=0,
            matches=[],
            exact_matches=[],
            semantic_matches=[],
            limitations=[],
        )

    monkeypatch.setattr(
        "oau_ai.similarity.service.SimilarityService.compare_text", fake_compare
    )

    from oau_ai.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v2/similarity/check", json={"text": "some thesis text"}, headers=HEADERS
        )

    assert response.status_code == 200, response.text
    assert response.json()["input_mode"] == "text"


@pytest.mark.asyncio
async def test_plagiarism_route_is_wired(monkeypatch):
    async def fake_assess(self, actor, text, **kwargs):
        return PlagiarismAssessment(
            status="no_significant_overlap",
            passages=[],
            matched_source_count=0,
            limitations=[],
        )

    monkeypatch.setattr(
        "oau_ai.similarity.service.PlagiarismAssessmentService.assess", fake_assess
    )

    from oau_ai.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v2/plagiarism/assess", json={"text": "some thesis text"}, headers=HEADERS
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "no_significant_overlap"
    assert body["disclaimer"]


@pytest.mark.asyncio
async def test_topics_route_is_wired(monkeypatch):
    async def fake_analyze(self, actor, max_documents=200, max_topics=25):
        return TopicAnalysis(
            total_documents=0,
            analysed_documents=0,
            topics=[],
            departments=[],
            faculties=[],
            years=[],
            limitations=[],
        )

    monkeypatch.setattr("oau_ai.topics.service.TopicService.analyze", fake_analyze)

    from oau_ai.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v2/topics/analyze", json={"max_documents": 10}, headers=HEADERS
        )

    assert response.status_code == 200, response.text
    assert response.json()["topics"] == []


@pytest.mark.asyncio
async def test_recommendations_route_is_wired(monkeypatch):
    async def fake_recommend(self, actor, query=None, seed_thesis_id=None, top_k=5):
        return RecommendationResponse(
            context_source="none",
            query="",
            recommendations=[],
            insufficient_evidence=True,
            message="No research context was supplied.",
        )

    monkeypatch.setattr(
        "oau_ai.recommendations.service.RecommendationService.recommend", fake_recommend
    )

    from oau_ai.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v2/recommendations", json={}, headers=HEADERS)

    assert response.status_code == 200, response.text
    assert response.json()["insufficient_evidence"] is True


@pytest.mark.asyncio
async def test_ai_writing_route_returns_unavailable_as_503(monkeypatch):
    class _StubDetector:
        def detect(self, text):
            return AITextDetectionResult(
                status="unavailable",
                model_id="rasbt/ai-text-detector-modernbert",
                blocker="Weights are not present locally.",
            )

    monkeypatch.setattr(routes, "get_detection_service", lambda: _StubDetector())

    from oau_ai.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v2/ai-writing/detect", json={"text": "word " * 80}, headers=HEADERS
        )

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["code"] == "detector_unavailable"
    assert body["ai_probability"] is None
