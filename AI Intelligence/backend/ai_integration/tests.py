"""Django integration tests for the AI Integration app.

These tests use Django's test framework with mocked outbound requests to the
V2 AI service. They verify:
- Authentication is required (no JWT → 401)
- Thesis permissions are enforced (owner/admin only)
- Actor context is forwarded to V2 (user_id, roles, department, trace_id)
- User JWT is NOT forwarded to V2
- Service-to-service token is forwarded

Live integration tests (against a running V2 service) are NOT included here
because they require external credentials and a running V2 instance.
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import User
from theses.models import Thesis, AccessRequest


class AIIntegrationAuthTests(TestCase):
    """Authentication and permission tests."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="user@example.com",
            password="testpass123",
            role="student",
            department="Computer Science",
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="adminpass123",
            role="admin",
            department="Administration",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="otherpass123",
            role="student",
            department="Physics",
        )

        self.thesis = Thesis.objects.create(
            title="Test Thesis",
            author="Test Author",
            owner=self.user,
            department="Computer Science",
            faculty="Science",
            year=2024,
            abstract="Test abstract.",
            supervisor="Dr. Supervisor",
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PUBLIC,
        )

        self.private_thesis = Thesis.objects.create(
            title="Private Thesis",
            author="Private Author",
            owner=self.user,
            department="Computer Science",
            faculty="Science",
            year=2024,
            abstract="Private abstract.",
            supervisor="Dr. Supervisor",
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PRIVATE,
        )

    def test_health_requires_authentication(self):
        """Unauthenticated requests to AI health return 401."""
        url = reverse("ai-health")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_health_authenticated_user_can_access(self):
        """Authenticated users can access the AI health endpoint."""
        self.client.force_authenticate(user=self.user)
        url = reverse("ai-health")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {"status": "ok"}
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify actor context was passed
        call_args = mock_forward.call_args
        self.assertEqual(call_args[1]["actor_context"]["user_id"], str(self.user.id))
        self.assertEqual(call_args[1]["actor_context"]["roles"], "student")
        self.assertEqual(call_args[1]["actor_context"]["department"], "Computer Science")
        self.assertIsNotNone(call_args[1]["actor_context"]["trace_id"])

    def test_user_jwt_not_forwarded_to_v2(self):
        """The user's JWT Authorization header is NOT forwarded to V2."""
        self.client.force_authenticate(user=self.user)
        url = reverse("ai-health")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {"status": "ok"}
            self.client.get(url, HTTP_AUTHORIZATION="Bearer fake-user-jwt")
        call_args = mock_forward.call_args
        # forward_to_v2 builds headers internally from actor_context + internal_token.
        # Verify the internal token is passed (not the user JWT).
        internal_token = call_args[1]["internal_token"]
        self.assertNotIn("fake-user-jwt", internal_token)
        self.assertTrue(len(internal_token) > 0)

    def test_internal_service_token_forwarded(self):
        """The internal service token is forwarded to V2."""
        self.client.force_authenticate(user=self.user)
        url = reverse("ai-health")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {"status": "ok"}
            self.client.get(url)
        call_args = mock_forward.call_args
        headers = call_args[1]["headers"]
        self.assertTrue(
            headers["Authorization"].startswith("Bearer "),
            f"Expected Bearer token, got: {headers.get('Authorization')}",
        )

    def test_trace_id_propagated(self):
        """A UUIDv4 trace_id is generated and propagated."""
        self.client.force_authenticate(user=self.user)
        url = reverse("ai-health")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {"status": "ok"}
            self.client.get(url)
        call_args = mock_forward.call_args
        trace_id = call_args[1]["actor_context"]["trace_id"]
        # UUIDv4 format: 8-4-4-4-12 hex chars
        import re
        self.assertRegex(trace_id, r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')

    def test_upload_requires_thesis_ownership_or_admin(self):
        """Upload requires thesis ownership or admin role."""
        self.client.force_authenticate(user=self.other_user)
        url = reverse("ai-document-upload")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {"document_id": "doc-1", "job_id": "job-1", "status": "pending"}
            response = self.client.post(
                url,
                {
                    "file": None,  # Will be handled by test client
                    "backend_thesis_id": str(self.private_thesis.id),
                    "backend_user_id": str(self.other_user.id),
                    "access_level": "private",
                },
                format="multipart",
            )
        # other_user doesn't own private_thesis and is not admin → 403
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_upload_for_any_thesis(self):
        """Admins can upload for any thesis."""
        self.client.force_authenticate(user=self.admin)
        url = reverse("ai-document-upload")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {"document_id": "doc-1", "job_id": "job-1", "status": "pending"}
            response = self.client.post(
                url,
                {
                    "backend_thesis_id": str(self.private_thesis.id),
                    "backend_user_id": str(self.user.id),
                    "access_level": "private",
                },
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_rag_requires_document_access(self):
        """RAG requests require access to all referenced documents."""
        self.client.force_authenticate(user=self.other_user)
        url = reverse("ai-rag-ask")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {
                "answer": "Test answer",
                "citations": [],
                "confidence": 0.9,
                "decision_engine": "deepseek",
                "llm_tier": 1,
                "trace_id": "trace-123",
                "request_id": "req-123",
            }
            response = self.client.post(
                url,
                {
                    "question": "What is this about?",
                    "document_ids": [str(self.private_thesis.id)],
                },
                format="json",
            )
        # other_user doesn't have access to private_thesis → 403
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rag_owner_can_access_own_document(self):
        """Document owners can RAG-query their own documents."""
        self.client.force_authenticate(user=self.user)
        url = reverse("ai-rag-ask")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {
                "answer": "Test answer",
                "citations": [],
                "confidence": 0.9,
                "decision_engine": "deepseek",
                "llm_tier": 1,
                "trace_id": "trace-123",
                "request_id": "req-123",
            }
            response = self.client.post(
                url,
                {
                    "question": "What is this about?",
                    "document_ids": [str(self.private_thesis.id)],
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class AIIntegrationPermissionTests(TestCase):
    """Cross-user access denial tests."""

    def setUp(self):
        self.client = APIClient()
        self.user_a = User.objects.create_user(
            email="usera@example.com",
            password="pass123",
            role="student",
            department="CS",
        )
        self.user_b = User.objects.create_user(
            email="userb@example.com",
            password="pass123",
            role="student",
            department="CS",
        )

        self.thesis_a = Thesis.objects.create(
            title="Thesis A",
            author="Author A",
            owner=self.user_a,
            department="CS",
            faculty="Science",
            year=2024,
            abstract="Abstract A.",
            supervisor="Dr. A",
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PRIVATE,
        )

    def test_user_b_cannot_access_user_a_private_thesis(self):
        """User B cannot perform operations on User A's private thesis."""
        self.client.force_authenticate(user=self.user_b)

        # Delete should be denied
        url = reverse("ai-document-delete", kwargs={"backend_thesis_id": str(self.thesis_a.id)})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_public_thesis_accessible_to_anyone(self):
        """Public published theses are accessible to any authenticated user."""
        public_thesis = Thesis.objects.create(
            title="Public Thesis",
            author="Author",
            owner=self.user_a,
            department="CS",
            faculty="Science",
            year=2024,
            abstract="Public abstract.",
            supervisor="Dr. S",
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PUBLIC,
        )

        self.client.force_authenticate(user=self.user_b)
        url = reverse("ai-rag-ask")
        with patch("ai_integration.services.forward_to_v2") as mock_forward:
            mock_forward.return_value = {
                "answer": "Answer",
                "citations": [],
                "confidence": 0.9,
                "decision_engine": "deepseek",
                "llm_tier": 1,
                "trace_id": "trace-123",
                "request_id": "req-123",
            }
            response = self.client.post(
                url,
                {
                    "question": "Question?",
                    "document_ids": [str(public_thesis.id)],
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
