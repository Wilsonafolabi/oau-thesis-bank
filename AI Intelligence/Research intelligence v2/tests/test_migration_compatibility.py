"""Migration schema compatibility tests.

Verifies that the SQL migration (sql/migrations/001_initial_schema.sql)
is compatible with the SQLAlchemy ORM models (src/oau_ai/db/models.py).

These tests inspect the migration SQL text and ORM column definitions
without requiring a live database connection.
"""

import re

from oau_ai.db.models import AIJob, JobStatus, ProcessingStage, Base


def test_migration_creates_enum_types_before_tables():
    """Migration creates enum types before CREATE TABLE statements."""
    migration_path = (
        "sql/migrations/001_initial_schema.sql"
    )
    with open(migration_path, "r") as f:
        sql = f.read()

    # Enum type creation must appear before the ai_jobs table definition
    enum_stage_pos = sql.find("CREATE TYPE ai_intelligence.ai_job_stage")
    enum_status_pos = sql.find("CREATE TYPE ai_intelligence.ai_job_status")
    table_jobs_pos = sql.find("CREATE TABLE IF NOT EXISTS ai_intelligence.ai_jobs")

    assert enum_stage_pos != -1, "ai_job_stage enum type not found in migration"
    assert enum_status_pos != -1, "ai_job_status enum type not found in migration"
    assert table_jobs_pos != -1, "ai_jobs table not found in migration"
    assert enum_stage_pos < table_jobs_pos, (
        "ai_job_stage enum must be created before ai_jobs table"
    )
    assert enum_status_pos < table_jobs_pos, (
        "ai_job_status enum must be created before ai_jobs table"
    )


def test_migration_uses_enum_types_for_job_columns():
    """Migration uses enum types (not VARCHAR) for ai_jobs.stage and .status."""
    migration_path = "sql/migrations/001_initial_schema.sql"
    with open(migration_path, "r") as f:
        sql = f.read()

    # The ai_jobs.stage column should reference the enum type
    stage_match = re.search(
        r"stage\s+ai_intelligence\.ai_job_stage", sql
    )
    status_match = re.search(
        r"status\s+ai_intelligence\.ai_job_status", sql
    )
    assert stage_match is not None, (
        "ai_jobs.stage column must use ai_intelligence.ai_job_stage enum type"
    )
    assert status_match is not None, (
        "ai_jobs.status column must use ai_intelligence.ai_job_status enum type"
    )

    # Plain VARCHAR declarations for stage/status should NOT exist.
    # Use word boundaries so "error_stage VARCHAR" does not match "stage VARCHAR".
    varchar_stage = re.search(r"\bstage\b\s+VARCHAR", sql)
    varchar_status = re.search(r"\bstatus\b\s+VARCHAR", sql)
    assert varchar_stage is None, "ai_jobs.stage should not be VARCHAR"
    assert varchar_status is None, "ai_jobs.status should not be VARCHAR"


def test_migration_has_rerun_guards():
    """Migration includes ALTER COLUMN guards for existing VARCHAR columns."""
    migration_path = "sql/migrations/001_initial_schema.sql"
    with open(migration_path, "r") as f:
        sql = f.read()

    assert "information_schema.columns" in sql, (
        "Migration should check information_schema.columns before ALTER"
    )
    assert "ALTER TABLE ai_intelligence.ai_jobs" in sql, (
        "Migration should have ALTER TABLE for existing columns"
    )
    assert "USING stage::ai_intelligence.ai_job_stage" in sql, (
        "Migration should cast stage column to enum type"
    )
    assert "USING status::ai_intelligence.ai_job_status" in sql, (
        "Migration should cast status column to enum type"
    )


def test_orm_job_status_matches_migration_enum_values():
    """ORM JobStatus enum values match migration enum values."""
    migration_path = "sql/migrations/001_initial_schema.sql"
    with open(migration_path, "r") as f:
        sql = f.read()

    # Extract migration enum values for ai_job_status
    status_enum_match = re.search(
        r"ai_job_status\s+AS ENUM\s*\((.*?)\)",
        sql,
        re.DOTALL,
    )
    assert status_enum_match is not None, "ai_job_status enum not found in migration"
    migration_values = re.findall(
        r"'([^']+)'", status_enum_match.group(1)
    )

    orm_values = [member.value for member in JobStatus]
    assert set(migration_values) == set(orm_values), (
        f"Migration enum values {migration_values} do not match ORM {orm_values}"
    )


def test_orm_job_stage_matches_migration_enum_values():
    """ORM ProcessingStage enum values match migration enum values."""
    migration_path = "sql/migrations/001_initial_schema.sql"
    with open(migration_path, "r") as f:
        sql = f.read()

    stage_enum_match = re.search(
        r"ai_job_stage\s+AS ENUM\s*\((.*?)\)",
        sql,
        re.DOTALL,
    )
    assert stage_enum_match is not None, "ai_job_stage enum not found in migration"
    migration_values = re.findall(
        r"'([^']+)'", stage_enum_match.group(1)
    )

    orm_values = [member.value for member in ProcessingStage]
    assert set(migration_values) == set(orm_values), (
        f"Migration enum values {migration_values} do not match ORM {orm_values}"
    )


def test_orm_ai_jobs_table_name_and_schema():
    """ORM AIJob model uses the correct table name and schema."""
    assert AIJob.__tablename__ == "ai_jobs"
    assert AIJob.__table_args__["schema"] == "ai_intelligence"


def test_orm_ai_jobs_columns_match_migration():
    """ORM AIJob columns match the migration column definitions."""
    # Check that stage and status columns use SAEnum (matching migration enum types)
    stage_col = AIJob.__table__.columns["stage"]
    status_col = AIJob.__table__.columns["status"]

    # The column types should be enum types (matching migration enum types).
    # SQLAlchemy 2.x uses sqlalchemy.types.Enum which compiles to PG ENUM.
    from sqlalchemy.types import Enum as SAEnumType

    assert isinstance(stage_col.type, SAEnumType), (
        f"ai_jobs.stage should be SA Enum, got {type(stage_col.type)}"
    )
    assert isinstance(status_col.type, SAEnumType), (
        f"ai_jobs.status should be SA Enum, got {type(status_col.type)}"
    )

    # Check enum type names match migration
    assert stage_col.type.name == "ai_job_stage"
    assert status_col.type.name == "ai_job_status"


EXPECTED_TABLES = {
    "ai_documents",
    "ai_pages",
    "ai_chunks",
    "ai_jobs",
    "researcher_memories",
    "memory_entities",
    "memory_relationships",
    "thesis_summaries",
    "working_memory_exchanges",
}

EXPECTED_ENUMS = {
    "ai_job_stage",
    "ai_job_status",
    "ai_memory_type",
    "ai_memory_source",
}


def _migration_sql() -> str:
    with open("sql/migrations/001_initial_schema.sql", "r") as f:
        return f.read()


def test_migration_creates_schema_before_enum_types():
    """Schema must be created before enum types and tables."""
    sql = _migration_sql()
    schema_pos = sql.find("CREATE SCHEMA IF NOT EXISTS ai_intelligence")
    enum_pos = sql.find("CREATE TYPE ai_intelligence.ai_job_stage")
    assert schema_pos != -1
    assert enum_pos != -1
    assert schema_pos < enum_pos, "schema must be created before enum types"


def test_migration_creates_all_tables():
    """Migration creates every table defined by the ORM models."""
    sql = _migration_sql()
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS ai_intelligence.{table}" in sql, (
            f"missing table definition for ai_intelligence.{table}"
        )


def test_migration_creates_all_enum_types():
    """Migration creates every enum type used by the ORM models."""
    sql = _migration_sql()
    for enum_name in EXPECTED_ENUMS:
        assert f"CREATE TYPE ai_intelligence.{enum_name}" in sql, (
            f"missing enum type definition for ai_intelligence.{enum_name}"
        )


def test_orm_metadata_registers_all_tables():
    """Every expected table is registered on the shared Base metadata."""
    registered = set(Base.metadata.tables.keys())
    expected = {f"ai_intelligence.{t}" for t in EXPECTED_TABLES}
    missing = expected - registered
    assert not missing, f"tables missing from Base.metadata: {sorted(missing)}"
