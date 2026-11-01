"""Database session and engine for Phase 3 V2.

Engine creation is lazy: DATABASE_URL is read from the environment only when
first needed. This allows importing the module in test environments without
a configured database.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Project root is three levels up from this file (src/oau_ai/db/session.py).
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

if os.name == "nt" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_engine = None
_session_factory = None


def get_database_url() -> str:
    """Read the database URL from the environment.

    Prefers RI_DATABASE_URL. If it is absent, assembles a URL from the
    POSTGRES_* component variables. Refuses to silently connect with
    incorrect fallback credentials when neither is present.
    """
    url = os.getenv("RI_DATABASE_URL", "").strip()

    if not url:
        url = _build_url_from_postgres_components()

    if not url:
        raise RuntimeError(
            "RI_DATABASE_URL is not configured. Set it to the dedicated "
            "Research Intelligence database before starting the service."
        )

    # Normalize common PostgreSQL URL schemes for SQLAlchemy.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)

    return url


def _build_url_from_postgres_components() -> str:
    """Assemble a psycopg URL from POSTGRES_* environment variables.

    Returns an empty string when required components are missing, so the
    caller can raise the canonical configuration error.
    """
    host = os.getenv("POSTGRES_HOST", "").strip()
    port = os.getenv("POSTGRES_PORT", "5432").strip()
    db = os.getenv("POSTGRES_DB", "").strip()
    user = os.getenv("POSTGRES_USER", "").strip()
    password = os.getenv("POSTGRES_PASSWORD", "").strip()

    if not (host and db and user):
        return ""

    auth = quote_plus(user)
    if password:
        auth = f"{quote_plus(user)}:{quote_plus(password)}"

    return f"postgresql+psycopg://{auth}@{host}:{port}/{db}"


def _ensure_engine():
    """Lazily create the engine and sessionmaker on first use."""
    global _engine, _session_factory
    if _engine is None:
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        _engine = create_async_engine(
            get_database_url(),
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=1800,
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _engine, _session_factory


def get_session_factory():
    """Return the async session factory, initializing it lazily."""
    _, factory = _ensure_engine()
    return factory


async def get_async_session():
    """FastAPI dependency that provides a database session."""
    _, session_factory = _ensure_engine()
    async with session_factory() as session:
        yield session


async def check_database_connection() -> bool:
    """Check database connectivity without exposing credentials or reading rows."""
    from sqlalchemy import text

    engine, _ = _ensure_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    return True


async def close_database_connection() -> None:
    """Dispose of the SQLAlchemy connection pool during shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def init_db() -> None:
    """Create the ai_intelligence schema and all ORM tables if missing.

    Uses the SQLAlchemy models as the source of truth, so the database always
    matches the ORM definitions. Idempotent: safe to call on every startup.
    """
    from sqlalchemy import text

    from .models import Base

    engine, _ = _ensure_engine()
    async with engine.begin() as connection:
        # Enums and tables are schema-qualified, so the schema must exist first.
        await connection.execute(
            text("CREATE SCHEMA IF NOT EXISTS ai_intelligence")
        )
        await connection.run_sync(Base.metadata.create_all)
