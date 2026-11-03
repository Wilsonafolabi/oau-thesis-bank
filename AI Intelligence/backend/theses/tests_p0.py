"""P0.3 regression tests: save/flag must not touch unviewable (draft/private) theses."""

from rest_framework.test import APITestCase

from accounts.models import User
from theses.models import Thesis

PASSWORD = "pass-12345"


class SaveFlagAccessTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="p0-t-owner@test.local", password=PASSWORD, role="researcher", status="active"
        )
        self.viewer = User.objects.create_user(
            email="p0-t-viewer@test.local", password=PASSWORD, role="student", status="active"
        )
        self.draft = Thesis.objects.create(
            title="Private Draft",
            author="A",
            owner=self.owner,
            status=Thesis.Status.DRAFT,
            access_policy=Thesis.AccessPolicy.PRIVATE,
        )
        self.public = Thesis.objects.create(
            title="Public Thesis",
            author="A",
            owner=self.owner,
            status=Thesis.Status.PUBLISHED,
            access_policy=Thesis.AccessPolicy.PUBLIC,
        )
        login = self.client.post(
            "/api/auth/login/",
            {"email": self.viewer.email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    def test_cannot_save_unviewable_draft(self):
        response = self.client.post(f"/api/theses/{self.draft.id}/save/")
        self.assertEqual(response.status_code, 403)

    def test_cannot_flag_unviewable_draft(self):
        response = self.client.post(
            f"/api/theses/{self.draft.id}/flag/",
            {"flag_type": "standard_review"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_can_flag_viewable_public_thesis(self):
        response = self.client.post(
            f"/api/theses/{self.public.id}/flag/",
            {"flag_type": "standard_review"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
