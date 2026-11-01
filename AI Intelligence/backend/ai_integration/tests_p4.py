"""P4 regression tests — Django proxies for topic analysis and recommendations."""

from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from theses.models import Thesis

PASSWORD = "pass-12345"

TOPIC_PAYLOAD = {
    "total_documents": 2,
    "analysed_documents": 2,
    "topics": [{"name": "rotation", "document_count": 2, "thesis_ids": ["1", "2"]}],
    "departments": [],
    "faculties": [],
    "years": [{"year": 2023, "document_count": 2}],
    "limitations": [],
}

REC_PAYLOAD = {
    "context_source": "request",
    "query": "soil",
    "recommendations": [],
    "insufficient_evidence": True,
    "message": "No accessible repository evidence matches this context.",
    "limitations": [],
}


def _login(client, email):
    response = client.post(
        "/api/auth/login/", {"email": email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class TopicAnalysisEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="p4-topic@test.local", password=PASSWORD, role="student", status="active"
        )

    def test_requires_authentication(self):
        response = self.client.post("/api/ai/topics/analyze/", {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_student_can_run_analysis(self):
        _login(self.client, self.user.email)
        with patch(
            "ai_integration.views.forward_to_v2", return_value=TOPIC_PAYLOAD
        ) as forward:
            response = self.client.post(
                "/api/ai/topics/analyze/", {"max_documents": 50}, format="json"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["topics"][0]["name"], "rotation")
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"]["max_documents"], 50)

    def test_actor_is_server_derived(self):
        _login(self.client, self.user.email)
        with patch(
            "ai_integration.views.forward_to_v2", return_value=TOPIC_PAYLOAD
        ) as forward:
            self.client.post(
                "/api/ai/topics/analyze/", {"user_id": "999"}, format="json"
            )

        _, kwargs = forward.call_args
        self.assertNotIn("user_id", kwargs["data"])
        self.assertEqual(
            kwargs["actor_context"]["user_id"], str(self.user.id)
        )


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class RecommendationEndpointTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="p4-owner@test.local", password=PASSWORD, role="student", status="active"
        )
        self.other = User.objects.create_user(
            email="p4-other@test.local", password=PASSWORD, role="student", status="active"
        )

    def test_requires_authentication(self):
        response = self.client.post("/api/ai/recommendations/", {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_query_is_forwarded(self):
        _login(self.client, self.owner.email)
        with patch(
            "ai_integration.views.forward_to_v2", return_value=REC_PAYLOAD
        ) as forward:
            response = self.client.post(
                "/api/ai/recommendations/",
                {"query": "crop rotation", "top_k": 3},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"], {"query": "crop rotation", "top_k": 3})

    def test_private_seed_thesis_is_denied(self):
        private = Thesis.objects.create(
            title="Private",
            author="A",
            owner=self.owner,
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PRIVATE,
        )
        _login(self.client, self.other.email)

        with patch("ai_integration.views.forward_to_v2") as forward:
            response = self.client.post(
                "/api/ai/recommendations/",
                {"seed_thesis_id": str(private.id)},
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        forward.assert_not_called()

    def test_public_seed_thesis_is_allowed(self):
        public = Thesis.objects.create(
            title="Public",
            author="A",
            owner=self.owner,
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PUBLIC,
        )
        _login(self.client, self.other.email)

        with patch(
            "ai_integration.views.forward_to_v2", return_value=REC_PAYLOAD
        ) as forward:
            response = self.client.post(
                "/api/ai/recommendations/",
                {"seed_thesis_id": str(public.id)},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        forward.assert_called_once()
