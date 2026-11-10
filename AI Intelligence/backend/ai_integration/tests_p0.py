"""P0.2 / P0.3 / P0.4 regression tests for ai_integration."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import Resolver404, resolve
from rest_framework.test import APITestCase

from accounts.models import User
from ai_integration.views import (
    AIMemoryListCreateView,
    AIMemoryPreferencesView,
    AIMemoryThesisSummaryView,
)
from theses.models import Thesis

PASSWORD = "pass-12345"
V2_UPLOAD_OK = {"document_id": "d1", "job_id": "j1", "status": "pending", "message": "queued"}


def _login(client, email):
    response = client.post(
        "/api/auth/login/", {"email": email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class LegacyProxyRemovedTests(APITestCase):
    def test_legacy_proxy_route_removed(self):
        with self.assertRaises(Resolver404):
            resolve("/api/ai/legacy-endpoint")

    def test_unauthenticated_legacy_proxy_returns_404(self):
        response = self.client.get("/api/ai/legacy-endpoint")
        self.assertEqual(response.status_code, 404)


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class DocumentAuthorizationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="p0-a-owner@test.local", password=PASSWORD, role="student", status="active"
        )
        self.other = User.objects.create_user(
            email="p0-a-other@test.local", password=PASSWORD, role="student", status="active"
        )
        self.admin = User.objects.create_user(
            email="p0-a-admin@test.local", password=PASSWORD, role="admin", status="active"
        )
        self.thesis = Thesis.objects.create(
            title="Public Published",
            author="A",
            owner=self.owner,
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PUBLIC,
        )

    def _file(self):
        return SimpleUploadedFile("thesis.pdf", b"%PDF-1.4 test", content_type="application/pdf")

    def test_unrelated_user_cannot_upload_for_public_thesis(self):
        _login(self.client, self.other.email)
        with patch("ai_integration.views.forward_to_v2") as forward:
            response = self.client.post(
                "/api/ai/documents/upload/",
                {"backend_thesis_id": self.thesis.id, "file": self._file()},
                format="multipart",
            )
        self.assertEqual(response.status_code, 403)
        forward.assert_not_called()

    def test_owner_can_upload_and_identity_is_server_derived(self):
        _login(self.client, self.owner.email)
        with patch("ai_integration.views.forward_to_v2", return_value=V2_UPLOAD_OK) as forward:
            response = self.client.post(
                "/api/ai/documents/upload/",
                {
                    "backend_thesis_id": self.thesis.id,
                    "backend_user_id": "99999",
                    "file": self._file(),
                },
                format="multipart",
            )
        self.assertEqual(response.status_code, 202)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"]["backend_user_id"], str(self.owner.id))
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.ai_job_id, "j1")
        self.assertEqual(
            self.thesis.processing_status, Thesis.ProcessingStatus.QUEUED
        )

    def test_owner_can_upload_temporary_pdf_without_thesis_access(self):
        _login(self.client, self.owner.email)
        temporary_id = "tmp-pdf-00000000-0000-4000-8000-000000000001"
        with patch("ai_integration.views.forward_to_v2", return_value=V2_UPLOAD_OK) as forward:
            response = self.client.post(
                "/api/ai/documents/upload/",
                {"backend_thesis_id": temporary_id, "file": self._file()},
                format="multipart",
            )

        self.assertEqual(response.status_code, 202)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"]["backend_thesis_id"], temporary_id)
        self.assertEqual(kwargs["data"]["backend_user_id"], str(self.owner.id))
        self.assertEqual(kwargs["data"]["access_level"], "private")

    def test_temporary_upload_ignores_client_user_and_access_level(self):
        _login(self.client, self.other.email)
        with patch("ai_integration.views.forward_to_v2", return_value=V2_UPLOAD_OK) as forward:
            response = self.client.post(
                "/api/ai/documents/upload/",
                {
                    "backend_thesis_id": "tmp-pdf-00000000-0000-4000-8000-000000000002",
                    "backend_user_id": str(self.owner.id),
                    "access_level": "public",
                    "file": self._file(),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, 202)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["data"]["backend_user_id"], str(self.other.id))
        self.assertEqual(kwargs["data"]["access_level"], "private")

    def test_admin_can_upload(self):
        _login(self.client, self.admin.email)
        with patch("ai_integration.views.forward_to_v2", return_value=V2_UPLOAD_OK):
            response = self.client.post(
                "/api/ai/documents/upload/",
                {"backend_thesis_id": self.thesis.id, "file": self._file()},
                format="multipart",
            )
        self.assertEqual(response.status_code, 202)

    def test_unrelated_user_cannot_delete(self):
        _login(self.client, self.other.email)
        with patch(
            "ai_integration.views.resolve_document_to_thesis",
            return_value=str(self.thesis.id),
        ), patch("ai_integration.views.forward_to_v2") as forward:
            response = self.client.delete(f"/api/ai/documents/{self.thesis.id}/")
        self.assertEqual(response.status_code, 403)
        forward.assert_not_called()

    def test_temporary_document_delete_is_forwarded_for_v2_owner_check(self):
        _login(self.client, self.owner.email)
        with patch(
            "ai_integration.views.resolve_document_to_thesis",
            return_value="tmp-pdf-00000000-0000-4000-8000-000000000001",
        ), patch("ai_integration.views.forward_to_v2", return_value={"detail": "deleted"}) as forward:
            response = self.client.delete("/api/ai/documents/document-uuid/")

        self.assertEqual(response.status_code, 200)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["path"], "/api/v2/documents/document-uuid")
        self.assertEqual(kwargs["actor_context"]["user_id"], str(self.owner.id))

    def test_job_status_forwards_authenticated_actor(self):
        _login(self.client, self.other.email)
        with patch(
            "ai_integration.views.forward_to_v2",
            return_value={"job_id": "j", "status": "pending", "stage": "extraction", "message": "x"},
        ) as forward:
            self.client.get("/api/ai/documents/jobs/j1/")
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["actor_context"]["user_id"], str(self.other.id))

    def test_job_status_maps_access_error_to_403(self):
        _login(self.client, self.other.email)
        with patch(
            "ai_integration.views.forward_to_v2",
            side_effect=ValueError("AI service error (403): access denied"),
        ):
            response = self.client.get("/api/ai/documents/jobs/j2/")
        self.assertEqual(response.status_code, 403)


@override_settings(BACKEND_API_INTERNAL_TOKEN="test-token", AI_SERVICE_URL="http://test-v2")
class MemoryRoutingTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="p0-m@test.local", password=PASSWORD, role="student", status="active"
        )
        self.thesis = Thesis.objects.create(
            title="Owned",
            author="A",
            owner=self.user,
            status=Thesis.Status.DRAFT,
            access_policy=Thesis.AccessPolicy.PRIVATE,
        )
        _login(self.client, self.user.email)

    def test_memory_root_resolves_to_list_create(self):
        match = resolve("/api/ai/memory/")
        self.assertEqual(match.func.view_class, AIMemoryListCreateView)

    def test_thesis_summaries_resolves_to_summary_view(self):
        match = resolve("/api/ai/memory/thesis-summaries/")
        self.assertEqual(match.func.view_class, AIMemoryThesisSummaryView)

    def test_preferences_resolves_to_preferences_view(self):
        match = resolve("/api/ai/memory/preferences/")
        self.assertEqual(match.func.view_class, AIMemoryPreferencesView)

    def test_post_memory_creates_instead_of_405(self):
        with patch("ai_integration.views.forward_to_v2", return_value={"id": "m1"}) as forward:
            response = self.client.post(
                "/api/ai/memory/", {"key": "k", "value": "v"}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["path"], "/api/v2/memory/")

    def test_post_thesis_summary_creates_instead_of_405(self):
        with patch("ai_integration.views.forward_to_v2", return_value={"id": "s1"}) as forward:
            response = self.client.post(
                "/api/ai/memory/thesis-summaries/",
                {"backend_thesis_id": self.thesis.id},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        _, kwargs = forward.call_args
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["path"], "/api/v2/memory/thesis-summaries")
