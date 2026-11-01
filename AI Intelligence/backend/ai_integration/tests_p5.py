"""P5 regression tests — Django proxies for similarity, plagiarism, AI-writing."""

from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from ai_integration.services import AIServiceError

PASSWORD = "pass-12345"

SIMILARITY_PAYLOAD = {
    "input_mode": "text",
    "passages_scanned": 1,
    "chunks_scanned": 3,
    "matches": [],
    "exact_matches": [],
    "semantic_matches": [],
    "limitations": ["Semantic comparison unavailable; results are lexical only."],
}

PLAGIARISM_PAYLOAD = {
    "status": "review_required",
    "passages": [],
    "matched_source_count": 1,
    "limitations": [],
    "disclaimer": "Not a finding of plagiarism.",
}

AI_WRITING_UNAVAILABLE = {
    "status": "unavailable",
    "assessment": None,
    "ai_probability": None,
    "confidence": None,
    "segments": [],
    "model_id": "rasbt/ai-text-detector-modernbert",
    "model_version": "a6efd4bf",
    "limitations": ["No detection was performed, so no score is reported."],
    "blocker": "Weights are not present locally.",
    "disclaimer": "Not proof of AI authorship.",
}


def _login(client, email):
    response = client.post(
        "/api/auth/login/", {"email": email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class SimilarityEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="p5-sim@test.local", password=PASSWORD, role="student", status="active"
        )

    def test_requires_authentication(self):
        response = self.client.post("/api/ai/similarity/check/", {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_empty_text_is_rejected_before_forwarding(self):
        _login(self.client, self.user.email)
        with patch("ai_integration.views.forward_to_v2") as forward:
            response = self.client.post(
                "/api/ai/similarity/check/", {"text": "   "}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        forward.assert_not_called()

    def test_payload_is_forwarded(self):
        _login(self.client, self.user.email)
        with patch(
            "ai_integration.views.forward_to_v2", return_value=SIMILARITY_PAYLOAD
        ) as forward:
            response = self.client.post(
                "/api/ai/similarity/check/",
                {
                    "text": "some thesis text",
                    "min_score": 0.4,
                    "max_matches": 5,
                    "enable_semantic": False,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"]["min_score"], 0.4)
        self.assertEqual(kwargs["data"]["max_matches"], 5)
        self.assertFalse(kwargs["data"]["enable_semantic"])

    def test_empty_text_error_from_v2_maps_to_400(self):
        _login(self.client, self.user.email)
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=AIServiceError(
                "AI service error (400): empty_text",
                status_code=400,
                code="empty_text",
            ),
        ):
            response = self.client.post(
                "/api/ai/similarity/check/", {"text": "x"}, format="json"
            )
        self.assertEqual(response.status_code, 400)


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class PlagiarismEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="p5-plag@test.local", password=PASSWORD, role="student", status="active"
        )

    def test_requires_authentication(self):
        response = self.client.post("/api/ai/plagiarism/assess/", {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_assessment_is_returned_verbatim(self):
        _login(self.client, self.user.email)
        with patch(
            "ai_integration.views.forward_to_v2", return_value=PLAGIARISM_PAYLOAD
        ):
            response = self.client.post(
                "/api/ai/plagiarism/assess/", {"text": "thesis text"}, format="json"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "review_required")
        self.assertIn("disclaimer", response.data)


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class AIWritingEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="p5-aiw@test.local", password=PASSWORD, role="student", status="active"
        )

    def test_requires_authentication(self):
        response = self.client.post("/api/ai/ai-writing/detect/", {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_missing_detector_surfaces_as_503_not_success(self):
        _login(self.client, self.user.email)
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=AIServiceError(
                "AI service error (503): detector unavailable",
                status_code=503,
                code=None,
                detail="Weights are not present locally.",
            ),
        ):
            response = self.client.post(
                "/api/ai/ai-writing/detect/", {"text": "some text"}, format="json"
            )

        self.assertEqual(response.status_code, 503)

    def test_text_is_forwarded(self):
        _login(self.client, self.user.email)
        with patch(
            "ai_integration.views.forward_to_v2", return_value=AI_WRITING_UNAVAILABLE
        ) as forward:
            self.client.post(
                "/api/ai/ai-writing/detect/", {"text": "some text"}, format="json"
            )

        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"], {"text": "some text"})
