# Phase 3 V2 Database Migrations

| File | Description |
|---|---|
| `001_initial_schema.sql` | Creates `ai_intelligence` schema with `ai_documents`, `ai_pages`, `ai_chunks`, `ai_jobs`, `researcher_memories`, `memory_entities`, `memory_relationships`, `thesis_summaries`, `working_memory_exchanges`. Creates enum types for job stage/status and memory type/source. |

## How tables are created

V2 creates the `ai_intelligence` schema and all tables automatically on
startup via `init_db()` in `src/oau_ai/db/session.py`. The SQLAlchemy models
(`src/oau_ai/db/models.py`) are the source of truth, so the database always
matches the ORM. The step is idempotent and safe to run on every startup.

## Manual application (optional)

The SQL file is provided for environments that prefer explicit migrations:

```bash
# Set RI_DATABASE_URL to your PostgreSQL connection string
export RI_DATABASE_URL="postgresql+psycopg://user:password@host:5432/db"

# Apply migration
psql "$RI_DATABASE_URL" -f sql/migrations/001_initial_schema.sql
```

## Schema notes

- `ai_documents`: Canonical document records. `backend_thesis_id` links to Phase 2.
- `ai_pages`: Extracted page-level text with page-level provenance.
- `ai_chunks`: Canonical chunk text + provenance + Vectorize point ID mapping.
- `ai_jobs`: Ingestion job state machine (pending → processing → success/failed).
- `researcher_memories`: Persistent researcher memory, scoped to owner `user_id`.
- `memory_entities`: Extracted entities (topics, researchers, institutions, etc.).
- `memory_relationships`: Relationships between entities.
- `thesis_summaries`: Structured summaries reused across conversations.
- `working_memory_exchanges`: Rolling window of conversation exchanges.
- Canonical text and provenance live in PostgreSQL. Vectorize stores only
  embeddings and retrieval metadata (point_id → chunk_id mapping).
