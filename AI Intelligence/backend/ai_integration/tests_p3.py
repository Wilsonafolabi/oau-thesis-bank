"""P3 regression tests — Django pass-through for generated thesis summaries.

The Django layer must not invent summary content; it only forwards the
generation request for a thesis the caller may access.
"""

from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from theses.models import Thesis

PASSWORD = "pass-12345"
V2_SUMMARY = {
    "document_id": "doc-1",
    "backend_thesis_id": "1",
    "user_id": "1",
    "title": "Soil",
    "abstract_summary": "Research problem: low yields",
    "research_questions": [],
    "objectives": [],
    "methodology": None,
    "findings": [],
    "limitations": [],
    "key_entities": [],
    "confidence": 0.11,
    "missing_sections": ["objectives", "methodology"],
}


def _login(client, email):
    response = client.post(
        "/api/auth/login/", {"email": email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class ThesisSummaryPassthroughTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="p3-owner@test.local", password=PASSWORD, role="student", status="active"
        )
        self.other = User.objects.create_user(
            email="p3-other@test.local", password=PASSWORD, role="student", status="active"
        )
        self.thesis = Thesis.objects.create(
            title="Soil",
            author="A",
            owner=self.owner,
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PUBLIC,
        )

    def test_generate_flag_is_forwarded_without_content(self):
        _login(self.client, self.owner.email)

        with patch(
            "ai_integration.views.forward_to_v2", return_value=V2_SUMMARY
        ) as forward:
            response = self.client.post(
                "/api/ai/memory/thesis-summaries/",
                {
                    "backend_thesis_id": str(self.thesis.id),
                    "generate": True,
                    "findings": ["invented finding"],
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        _, kwargs = forward.call_args
        self.assertTrue(kwargs["data"]["generate"])
        self.assertNotIn("findings", kwargs["data"])
        self.assertEqual(response.data["missing_sections"], ["objectives", "methodology"])

    def test_without_generate_no_generate_key_is_sent(self):
        _login(self.client, self.owner.email)

        with patch(
            "ai_integration.views.forward_to_v2", return_value=V2_SUMMARY
        ) as forward:
            self.client.post(
                "/api/ai/memory/thesis-summaries/",
                {
                    "backend_thesis_id": str(self.thesis.id),
                    "findings": ["A finding"],
                },
                format="json",
            )

        _, kwargs = forward.call_args
        self.assertNotIn("generate", kwargs["data"])
        self.assertEqual(kwargs["data"]["findings"], ["A finding"])

    def test_summary_requires_thesis_access(self):
        _login(self.client, self.other.email)
        private = Thesis.objects.create(
            title="Private",
            author="A",
            owner=self.owner,
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PRIVATE,
        )

        with patch("ai_integration.views.forward_to_v2") as forward:
            response = self.client.post(
                "/api/ai/memory/thesis-summaries/",
                {"backend_thesis_id": str(private.id), "generate": True},
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        forward.assert_not_called()
