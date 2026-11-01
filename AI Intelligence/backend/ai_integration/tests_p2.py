"""P2 regression tests — server-derived AI document access scope.

The upload endpoint must not let a caller widen the visibility of AI content:
the access level is derived from the thesis record, never from the request.
"""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from ai_integration.services import derive_access_level
from theses.models import Thesis

PASSWORD = "pass-12345"
V2_OK = {"document_id": "d1", "job_id": "j1", "status": "pending", "message": "queued"}


def _login(client, email):
    response = client.post(
        "/api/auth/login/", {"email": email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


def _file():
    return SimpleUploadedFile(
        "thesis.pdf", b"%PDF-1.4 test", content_type="application/pdf"
    )


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class AccessLevelDerivationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="p2-owner@test.local", password=PASSWORD, role="student", status="active"
        )
        self.other = User.objects.create_user(
            email="p2-other@test.local", password=PASSWORD, role="student", status="active"
        )
        self.admin = User.objects.create_user(
            email="p2-admin@test.local", password=PASSWORD, role="admin", status="active"
        )

    def _thesis(self, status=Thesis.Status.PUBLISHED, policy=Thesis.AccessPolicy.PUBLIC):
        return Thesis.objects.create(
            title="T",
            author="A",
            owner=self.owner,
            status=status,
            access_policy=policy,
        )

    def test_draft_is_stored_private(self):
        thesis = self._thesis(status=Thesis.Status.DRAFT, policy=Thesis.AccessPolicy.PUBLIC)
        self.assertEqual(derive_access_level(thesis.id, self.owner), "private")

    def test_published_public_is_public(self):
        thesis = self._thesis(policy=Thesis.AccessPolicy.PUBLIC)
        self.assertEqual(derive_access_level(thesis.id, self.owner), "public")

    def test_published_restricted_is_restricted(self):
        thesis = self._thesis(policy=Thesis.AccessPolicy.RESTRICTED)
        self.assertEqual(derive_access_level(thesis.id, self.owner), "restricted")

    def test_published_private_is_private(self):
        thesis = self._thesis(policy=Thesis.AccessPolicy.PRIVATE)
        self.assertEqual(derive_access_level(thesis.id, self.owner), "private")

    def test_non_owner_gets_no_level(self):
        thesis = self._thesis()
        self.assertIsNone(derive_access_level(thesis.id, self.other))

    def test_admin_gets_level_for_other_users_draft(self):
        thesis = self._thesis(status=Thesis.Status.DRAFT)
        self.assertEqual(derive_access_level(thesis.id, self.admin), "private")

    def test_missing_thesis_gets_no_level(self):
        self.assertIsNone(derive_access_level(999999, self.owner))

    def test_upload_ignores_client_supplied_access_level(self):
        """A draft upload that asks for 'public' is forwarded as 'private'."""
        thesis = self._thesis(
            status=Thesis.Status.DRAFT, policy=Thesis.AccessPolicy.PUBLIC
        )
        _login(self.client, self.owner.email)

        with patch(
            "ai_integration.views.forward_to_v2", return_value=V2_OK
        ) as forward:
            response = self.client.post(
                "/api/ai/documents/upload/",
                {
                    "backend_thesis_id": thesis.id,
                    "access_level": "public",
                    "file": _file(),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, 202)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"]["access_level"], "private")

    def test_upload_forwards_published_public_level(self):
        thesis = self._thesis(policy=Thesis.AccessPolicy.PUBLIC)
        _login(self.client, self.owner.email)

        with patch(
            "ai_integration.views.forward_to_v2", return_value=V2_OK
        ) as forward:
            response = self.client.post(
                "/api/ai/documents/upload/",
                {"backend_thesis_id": thesis.id, "file": _file()},
                format="multipart",
            )

        self.assertEqual(response.status_code, 202)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"]["access_level"], "public")


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class JobStatusVocabularyTests(APITestCase):
    """The public job-status vocabulary must match the polling contract."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="p2-job@test.local", password=PASSWORD, role="student", status="active"
        )
        _login(self.client, self.user.email)

    def _job(self, status):
        return {
            "job_id": "j1",
            "status": status,
            "stage": "complete",
            "message": "ok",
            "result": None,
            "error_message": None,
            "error_stage": None,
            "attempts": 1,
            "max_attempts": 3,
        }

    def test_success_is_reported_as_completed(self):
        with patch("ai_integration.views.forward_to_v2", return_value=self._job("success")):
            response = self.client.get("/api/ai/documents/jobs/j1/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "completed")

    def test_failed_is_preserved(self):
        with patch("ai_integration.views.forward_to_v2", return_value=self._job("failed")):
            response = self.client.get("/api/ai/documents/jobs/j1/")

        self.assertEqual(response.data["status"], "failed")

    def test_processing_is_preserved(self):
        with patch("ai_integration.views.forward_to_v2", return_value=self._job("processing")):
            response = self.client.get("/api/ai/documents/jobs/j1/")

        self.assertEqual(response.data["status"], "processing")
