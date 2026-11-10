from django.core.files.base import ContentFile
from django.contrib import admin
from django.test import RequestFactory, override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from accounts.models import User
from admin_panel.models import AuditEvent, ModerationItem
from theses.models import Thesis


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class AdminPanelTestCase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin.test@oau.local",
            password="test-pass-123",
            role="admin",
            first_name="Ada",
            last_name="Admin",
        )
        self.student = User.objects.create_user(
            email="student.test@oau.local",
            password="test-pass-123",
            role="student",
            first_name="Sam",
            last_name="Student",
        )
        self.faculty = User.objects.create_user(
            email="faculty.test@oau.local",
            password="test-pass-123",
            role="faculty",
            first_name="Fat",
            last_name="Faculty",
        )
        self.thesis = Thesis.objects.create(
            title="Impact of Open Data on Research",
            author="Sam Student",
            owner=self.student,
            department="Computer Science",
            faculty="Technology",
            year=2024,
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.RESTRICTED,
            file=ContentFile("%PDF-1.4 test", "p2p.pdf"),
        )

    def auth(self, user):
        self.client.force_authenticate(user)

    def test_unauthenticated_and_non_admin_blocked(self):
        for path in (
            "/api/admin/summary/",
            "/api/admin/moderation/",
            "/api/admin/users/",
            "/api/admin/activity/",
            "/api/admin/health/",
        ):
            self.client.force_authenticate(user=None)
            response = self.client.get(path)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, msg=path)
            for user in (self.student, self.faculty):
                self.auth(user)
                response = self.client.get(path)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=path)
            self.client.force_authenticate(user=None)

    def test_summary_shape(self):
        self.auth(self.admin)
        response = self.client.get("/api/admin/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in (
            "total_theses",
            "published_theses",
            "draft_theses",
            "restricted_theses",
            "total_users",
            "active_users",
            "suspended_users",
            "pending_moderation",
            "pending_access_requests",
            "moderation_by_type",
            "health",
            "recent_activity",
        ):
            self.assertIn(key, response.data)
        self.assertEqual(response.data["total_theses"], 1)
        self.assertEqual(response.data["health"]["db"], "ok")

    def test_admin_can_index_existing_published_pdf(self):
        from io import BytesIO

        from theses.admin import ThesisAdmin

        request = RequestFactory().post("/")
        request.user = self.admin
        model_admin = ThesisAdmin(Thesis, admin.site)
        queryset = Thesis.objects.filter(pk=self.thesis.pk)

        with (
            patch("theses.admin.get_internal_service_token", return_value="internal"),
            patch("theses.admin.forward_to_v2", return_value={"job_id": "job-123"}) as forward,
            patch.object(ThesisAdmin, "message_user") as message_user,
            patch.object(self.thesis.file, "open", return_value=BytesIO(b"%PDF-1.4 test")),
        ):
            model_admin.index_with_ai(request, queryset)

        kwargs = forward.call_args.kwargs
        self.assertEqual(kwargs["path"], "/api/v2/documents/upload")
        self.assertEqual(kwargs["data"]["backend_thesis_id"], str(self.thesis.id))
        self.assertEqual(kwargs["data"]["backend_user_id"], str(self.student.id))
        self.assertEqual(kwargs["actor_context"]["user_id"], str(self.student.id))
        self.assertEqual(
            kwargs["files"]["file"][0],
            self.thesis.file.name.rsplit("/", 1)[-1],
        )
        self.assertEqual(kwargs["files"]["file"][2], "application/pdf")
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.processing_status, Thesis.ProcessingStatus.QUEUED)
        self.assertEqual(self.thesis.ai_job_id, "job-123")
        message_user.assert_called_once()

    def test_admin_can_refresh_ai_index_status(self):
        from theses.admin import ThesisAdmin

        self.thesis.ai_job_id = "job-123"
        self.thesis.processing_status = Thesis.ProcessingStatus.QUEUED
        self.thesis.save(update_fields=["ai_job_id", "processing_status"])
        request = RequestFactory().post("/")
        request.user = self.admin
        model_admin = ThesisAdmin(Thesis, admin.site)
        queryset = Thesis.objects.filter(pk=self.thesis.pk)

        with (
            patch("theses.admin.get_internal_service_token", return_value="internal"),
            patch(
                "theses.admin.forward_to_v2",
                return_value={"job_id": "job-123", "status": "success"},
            ) as forward,
            patch.object(ThesisAdmin, "message_user") as message_user,
        ):
            model_admin.refresh_ai_index_status(request, queryset)

        self.assertEqual(
            forward.call_args.kwargs["path"],
            "/api/v2/documents/jobs/job-123",
        )
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.processing_status, Thesis.ProcessingStatus.COMPLETED)
        message_user.assert_called_once()

    def test_flag_thesis_creates_moderation_item(self):
        self.auth(self.faculty)
        response = self.client.post(
            f"/api/theses/{self.thesis.id}/flag/",
            {"flag_type": "high_similarity", "similarity_score": 0.93, "note": "Matches another thesis."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["flag_type"], "high_similarity")
        item = ModerationItem.objects.get(pk=response.data["id"])
        self.assertEqual(item.status, ModerationItem.Status.PENDING)
        self.assertEqual(item.reporter, self.faculty)
        self.assertTrue(AuditEvent.objects.filter(action="moderation.flagged").exists())

    def test_owner_cannot_flag_and_duplicate_flagged(self):
        self.auth(self.student)
        response = self.client.post(
            f"/api/theses/{self.thesis.id}/flag/", {"flag_type": "metadata"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.auth(self.faculty)
        self.client.post(
            f"/api/theses/{self.thesis.id}/flag/", {"flag_type": "metadata"}, format="json"
        )
        response = self.client.post(
            f"/api/theses/{self.thesis.id}/flag/", {"flag_type": "standard_review"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_flag_type_rejected(self):
        self.auth(self.faculty)
        response = self.client.post(
            f"/api/theses/{self.thesis.id}/flag/", {"flag_type": "spam"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_moderation_review_flow(self):
        item = ModerationItem.objects.create(
            thesis=self.thesis, flag_type="standard_review", reporter=self.faculty
        )
        self.auth(self.admin)
        listing = self.client.get("/api/admin/moderation/")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data["results"]), 1)
        response = self.client.patch(
            f"/api/admin/moderation/{item.id}/review/", {"decision": "approved"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.status, ModerationItem.Status.APPROVED)
        self.assertEqual(item.reviewer, self.admin)
        self.assertIsNotNone(item.reviewed_at)
        self.assertTrue(AuditEvent.objects.filter(action="moderation.reviewed").exists())
        listing = self.client.get("/api/admin/moderation/?status=pending")
        self.assertEqual(len(listing.data["results"]), 0)

    def test_moderation_search_and_filter(self):
        ModerationItem.objects.create(
            thesis=self.thesis, flag_type="high_similarity", reporter=self.faculty
        )
        self.auth(self.admin)
        response = self.client.get("/api/admin/moderation/?q=Open%20Data&flag_type=high_similarity")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        response = self.client.get("/api/admin/moderation/?q=Unrelated")
        self.assertEqual(len(response.data["results"]), 0)

    def test_user_list_search_and_filters(self):
        self.auth(self.admin)
        response = self.client.get("/api/admin/users/?role=student")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["email"], self.student.email)
        response = self.client.get("/api/admin/users/?search=Ada")
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.admin.id)

    def test_update_user_role_and_status(self):
        self.auth(self.admin)
        response = self.client.patch(
            f"/api/admin/users/{self.student.id}/update_access/",
            {"role": "researcher", "status": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "researcher")
        self.assertEqual(self.student.status, "suspended")
        self.assertTrue(AuditEvent.objects.filter(action="user.updated").exists())

    def test_guards_cannot_change_own_role_or_suspend_self(self):
        self.auth(self.admin)
        response = self.client.patch(
            f"/api/admin/users/{self.admin.id}/update_access/", {"role": "student"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.patch(
            f"/api/admin/users/{self.admin.id}/update_access/",
            {"status": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "admin")
        self.assertEqual(self.admin.status, "active")

    def test_second_admin_can_manage_first(self):
        second_admin = User.objects.create_user(
            email="admin2.test@oau.local", password="test-pass-123", role="admin"
        )
        self.auth(second_admin)
        response = self.client.patch(
            f"/api/admin/users/{self.admin.id}/update_access/",
            {"status": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.status, "suspended")

    def test_activity_and_health(self):
        self.auth(self.admin)
        response = self.client.get("/api/admin/activity/?limit=5")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get("/api/admin/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["checks"]["db"], "ok")

    def test_thesis_upload_creates_audit_event(self):
        self.auth(self.student)
        response = self.client.post(
            "/api/theses/",
            {"title": "New Thesis", "author": "Sam Student", "department": "CS", "status": "draft"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertTrue(
            AuditEvent.objects.filter(action="thesis.uploaded", subject_id=response.data["id"]).exists()
        )