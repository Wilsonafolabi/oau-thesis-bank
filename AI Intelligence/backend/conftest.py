import django
import pytest
from typing import Any, Dict

django.setup()

from rest_framework.test import APIClient

from accounts.models import User
from theses.models import Tag, Thesis

PASSWORD = "test-password-123"


@pytest.fixture
def local_media_root(settings, tmp_path_factory):
    """Keep uploads on a temporary filesystem.

    `.env` may point the default storage at MinIO or R2, but the test suite
    must not depend on a running object store.
    """
    media_root = tmp_path_factory.mktemp("media")
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.MEDIA_ROOT = media_root
    return media_root


@pytest.fixture
def password():
    return PASSWORD


def _make_user(email=None, role="student", **kwargs):
    email = email or f"{role}@test.local"
    user = User.objects.create_user(email=email, password=PASSWORD, role=role, **kwargs)
    return user


@pytest.fixture
def make_user():
    return _make_user


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def student(make_user):
    return make_user(email="student@test.local", role="student")


@pytest.fixture
def researcher(make_user):
    return make_user(email="researcher@test.local", role="researcher")


@pytest.fixture
def faculty(make_user):
    return make_user(email="faculty@test.local", role="faculty")


@pytest.fixture
def admin(make_user):
    return make_user(email="admin@test.local", role="admin")


@pytest.fixture
def api_client():
    return APIClient()


def _jwt_headers(client, user):
    response = client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200, response.data
    return {"HTTP_AUTHORIZATION": f"Bearer {response.data['access']}"}


@pytest.fixture
def auth_client(api_client, user):
    api_client.credentials(**_jwt_headers(api_client, user))
    return api_client


@pytest.fixture
def admin_client(api_client, admin):
    api_client.credentials(**_jwt_headers(api_client, admin))
    return api_client


@pytest.fixture
def make_thesis():
    def _make(owner=None, **kwargs):
        thesis = Thesis.objects.create(
            title=kwargs.get("title", "A Test Thesis"),
            author=kwargs.get("author", "Some Author"),
            owner=owner or _make_user(),
            department=kwargs.get("department", "Computer Science"),
            faculty=kwargs.get("faculty", "Science"),
            year=kwargs.get("year", 2024),
            abstract=kwargs.get("abstract", "Abstract text here."),
            supervisor=kwargs.get("supervisor", "Dr. Smith"),
            status=kwargs.get("status", Thesis.Status.PUBLISHED),
            access_policy=kwargs.get("access_policy", Thesis.AccessPolicy.PUBLIC),
        )
        for tag_name in kwargs.get("tags", ()):
            thesis.tags.add(Tag.objects.get_or_create(name=tag_name)[0])
        return thesis

    return _make


@pytest.fixture
def published_thesis(make_thesis, researcher):
    return make_thesis(owner=researcher, tags=["Machine Learning", "NLP"])


@pytest.fixture
def your_thesis(make_thesis, user):
    return make_thesis(owner=user, title="Your Own Thesis")


@pytest.fixture
def draft_thesis(make_thesis, researcher):
    return make_thesis(owner=researcher, title="Private Draft Thesis", status=Thesis.Status.DRAFT)


# ---------------------------------------------------------------------------
# Stage 3.5.5 diagnostics reporting (non-secret facts only)
# ---------------------------------------------------------------------------
class _Stage355Diagnostics:
    """Mutable diagnostics store shared between test modules and the conftest
    hookwrapper. Never contains credentials, JWTs, passwords, API keys, or
    environment-variable values."""

    def __init__(self) -> None:
        self.entries: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.entries[key] = value

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.entries)


_STAGE355_DIAG = _Stage355Diagnostics()


@pytest.fixture
def stage355_diag() -> _Stage355Diagnostics:
    """Provide the Stage 3.5.5 diagnostics store to test functions."""
    return _STAGE355_DIAG


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach a non-secret STAGE 3.5.5 diagnostics section to each test report.

    This hook lives in conftest.py (a supported pytest hook location) rather
    than in a test module, so pytest discovers and executes it for every test.
    """
    outcome = yield
    report = outcome.get_result()
    if call.when == "call" and _STAGE355_DIAG.entries:
        lines = []
        for key in (
            "sequence",
            "public_thesis_id",
            "private_thesis_id",
            "public_document_id",
            "private_document_id",
            "public_job_status",
            "private_job_status",
            "public_text_total_pages",
            "rag_status",
            "rag_detail",
            "cross_encoder_status",
            "duplicate_upload_status",
            "public_similarity_matching",
            "private_text_user_b_status",
            "private_rag_user_b_status",
            "cleanup_all_clean",
            "cleanup_errors",
            "outstanding_resources",
            "storage_provider",
            "r2_object_deleted",
            "report_generated",
        ):
            if key in _STAGE355_DIAG.entries:
                lines.append(f"{key}={_STAGE355_DIAG.entries[key]}")
        if lines:
            report.sections.append(("STAGE 3.5.5 Diagnostics", "\n".join(lines)))
