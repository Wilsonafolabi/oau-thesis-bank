"""Database session initialization tests.

Verifies that the database session module (src/oau_ai/db/session.py)
correctly handles configuration presence and absence without exposing
secret values or requiring a live database connection.
"""

import os
from unittest.mock import patch

import pytest

from oau_ai.db.session import get_database_url


def test_get_database_url_raises_when_not_configured():
    """get_database_url() raises RuntimeError when RI_DATABASE_URL is not set."""
    with patch.dict(os.environ, {}, clear=True):
        # Remove RI_DATABASE_URL if it exists in the process environment
        os.environ.pop("RI_DATABASE_URL", None)
        with pytest.raises(RuntimeError, match="RI_DATABASE_URL is not configured"):
            get_database_url()


def test_get_database_url_normalizes_postgresql_scheme():
    """get_database_url() normalizes postgresql:// to postgresql+psycopg://."""
    with patch.dict(
        os.environ,
        {"RI_DATABASE_URL": "postgresql://user:pass@localhost:5432/db"},
        clear=True,
    ):
        url = get_database_url()
        assert url == "postgresql+psycopg://user:pass@localhost:5432/db"


def test_get_database_url_normalizes_postgres_scheme():
    """get_database_url() normalizes postgres:// to postgresql+psycopg://."""
    with patch.dict(
        os.environ,
        {"RI_DATABASE_URL": "postgres://user:pass@localhost:5432/db"},
        clear=True,
    ):
        url = get_database_url()
        assert url == "postgresql+psycopg://user:pass@localhost:5432/db"


def test_get_database_url_passes_through_psycopg_scheme():
    """get_database_url() leaves postgresql+psycopg:// URLs unchanged."""
    with patch.dict(
        os.environ,
        {"RI_DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5433/db"},
        clear=True,
    ):
        url = get_database_url()
        assert url == "postgresql+psycopg://user:pass@localhost:5433/db"


def test_get_database_url_strips_whitespace():
    """get_database_url() strips surrounding whitespace from the URL."""
    with patch.dict(
        os.environ,
        {"RI_DATABASE_URL": "  postgresql://user:pass@localhost:5432/db  "},
        clear=True,
    ):
        url = get_database_url()
        assert url == "postgresql+psycopg://user:pass@localhost:5432/db"


def test_get_database_url_does_not_expose_secret():
    """The error message does not contain the database URL or credentials."""
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("RI_DATABASE_URL", None)
        with pytest.raises(RuntimeError) as exc_info:
            get_database_url()
        error_msg = str(exc_info.value)
        assert "password" not in error_msg.lower()
        assert "postgresql" not in error_msg.lower()
        assert "://" not in error_msg


def test_get_database_url_builds_from_postgres_components():
    """Falls back to assembling a URL from POSTGRES_* components."""
    with patch.dict(
        os.environ,
        {
            "POSTGRES_HOST": "db.example.com",
            "POSTGRES_PORT": "5433",
            "POSTGRES_DB": "oau_thesis_bank",
            "POSTGRES_USER": "app",
            "POSTGRES_PASSWORD": "s3cret",
        },
        clear=True,
    ):
        url = get_database_url()
        assert url == (
            "postgresql+psycopg://app:s3cret@db.example.com:5433/oau_thesis_bank"
        )


def test_get_database_url_prefers_ri_url_over_components():
    """RI_DATABASE_URL takes precedence over POSTGRES_* components."""
    with patch.dict(
        os.environ,
        {
            "RI_DATABASE_URL": "postgresql://primary:pass@host:5432/db",
            "POSTGRES_HOST": "ignored-host",
            "POSTGRES_DB": "ignored-db",
            "POSTGRES_USER": "ignored-user",
        },
        clear=True,
    ):
        url = get_database_url()
        assert url == "postgresql+psycopg://primary:pass@host:5432/db"


def test_get_database_url_build_encodes_special_chars():
    """Fallback URL-encodes user/password to keep the URL valid."""
    with patch.dict(
        os.environ,
        {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "db",
            "POSTGRES_USER": "user@domain",
            "POSTGRES_PASSWORD": "p@ss:word/",
        },
        clear=True,
    ):
        url = get_database_url()
        assert url == (
            "postgresql+psycopg://user%40domain:p%40ss%3Aword%2F@localhost:5432/db"
        )
