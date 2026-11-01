"""P0.1 regression tests: account privilege escalation via PATCH /api/auth/me/."""

from rest_framework.test import APITestCase

from accounts.models import User

PASSWORD = "pass-12345"


class MePrivilegeEscalationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="p0-owner@test.local",
            password=PASSWORD,
            role="student",
            status="active",
        )
        login = self.client.post(
            "/api/auth/login/",
            {"email": self.user.email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    def test_cannot_escalate_role_to_admin_via_me(self):
        response = self.client.patch("/api/auth/me/", {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "student")

    def test_cannot_change_status_via_me(self):
        response = self.client.patch("/api/auth/me/", {"status": "suspended"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, "active")

    def test_legitimate_profile_update_still_works(self):
        response = self.client.patch(
            "/api/auth/me/",
            {"department": "Physics", "faculty": "Science", "avatar": "ZZ"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.department, "Physics")
        self.assertEqual(self.user.faculty, "Science")
        self.assertEqual(self.user.avatar, "ZZ")
