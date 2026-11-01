"""P1 regression tests — Django↔V2 ingestion contract.

Verifies that upstream V2 failures surface as meaningful HTTP statuses
instead of a blanket 502, and that forward_to_v2 preserves the upstream error
code instead of flattening it into a string.
"""

from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from ai_integration.services import AIServiceError, forward_to_v2
from theses.models import Thesis

PASSWORD = "pass-12345"


def _login(client, email):
    response = client.post(
        "/api/auth/login/", {"email": email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


def _fake_response(status_code, payload):
    response = MagicMock()
    response.ok = 200 <= status_code < 300
    response.status_code = status_code
    response.text = str(payload)
    response.json = MagicMock(return_value=payload)
    response.headers = {"content-type": "application/json"}
    return response


class ForwardToV2ErrorTests(APITestCase):
    """forward_to_v2 must surface upstream status and error code."""

    @override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
    def test_structured_error_is_preserved(self):
        actor = {"user_id": "1", "roles": "student", "department": "CS", "trace_id": "t"}
        with patch("ai_integration.services.requests.request") as request:
            request.return_value = _fake_response(
                400, {"code": "access_denied", "message": "You do not have access."}
            )
            with self.assertRaises(AIServiceError) as ctx:
                forward_to_v2(
                    method="GET",
                    path="/api/v2/documents/jobs/j1",
                    actor_context=actor,
                    internal_token="test-token",
                )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.code, "access_denied")
        self.assertEqual(ctx.exception.detail, "You do not have access.")

    @override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
    def test_error_without_json_body_still_raises(self):
        actor = {"user_id": "1", "roles": "student", "department": "CS", "trace_id": "t"}
        with patch("ai_integration.services.requests.request") as request:
            response = _fake_response(500, "boom")
            response.json = MagicMock(side_effect=ValueError("not json"))
            request.return_value = response
            with self.assertRaises(AIServiceError) as ctx:
                forward_to_v2(
                    method="GET",
                    path="/api/v2/health",
                    actor_context=actor,
                    internal_token="test-token",
                )

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIsNone(ctx.exception.code)


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class IngestionErrorMappingTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="p1-owner@test.local", password=PASSWORD, role="student", status="active"
        )
        self.thesis = Thesis.objects.create(
            title="Owned Thesis",
            author="A",
            owner=self.owner,
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PUBLIC,
        )
        _login(self.client, self.owner.email)

    def _upload(self):
        return self.client.post(
            "/api/ai/documents/upload/",
            {
                "backend_thesis_id": self.thesis.id,
                "file": SimpleUploadedFile(
                    "thesis.pdf", b"%PDF-1.4 test", content_type="application/pdf"
                ),
            },
            format="multipart",
        )

    def test_duplicate_upload_maps_to_409(self):
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=AIServiceError(
                "AI service error (400): already exists",
                status_code=400,
                code="document_already_exists",
                detail="Document already exists.",
            ),
        ):
            response = self._upload()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "document_already_exists")

    def test_access_denied_maps_to_403(self):
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=AIServiceError(
                "AI service error (400): access denied",
                status_code=400,
                code="access_denied",
                detail="You do not have access.",
            ),
        ):
            response = self._upload()
        self.assertEqual(response.status_code, 403)

    def test_unreachable_service_maps_to_503(self):
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=ValueError("AI service unavailable: connection refused"),
        ):
            response = self._upload()
        self.assertEqual(response.status_code, 503)

    def test_unknown_upstream_error_maps_to_502(self):
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=AIServiceError(
                "AI service error (500): internal", status_code=500
            ),
        ):
            response = self._upload()
        self.assertEqual(response.status_code, 502)

    def test_job_status_maps_structured_access_denied_to_403(self):
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=AIServiceError(
                "AI service error (400): access denied",
                status_code=400,
                code="access_denied",
            ),
        ):
            response = self.client.get("/api/ai/documents/jobs/job-1/")
        self.assertEqual(response.status_code, 403)

    def test_delete_maps_missing_document_to_404(self):
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=AIServiceError(
                "AI service error (400): document_not_found",
                status_code=400,
                code="document_not_found",
            ),
        ):
            response = self.client.delete(f"/api/ai/documents/{self.thesis.id}/")
        self.assertEqual(response.status_code, 404)
