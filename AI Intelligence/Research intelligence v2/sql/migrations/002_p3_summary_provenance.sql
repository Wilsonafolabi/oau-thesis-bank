-- 002 — P3 summary provenance and staleness (additive, approved)
--
-- Adds the columns required to record where a generated thesis summary came
-- from, when it was produced, and which version superseded it.
--
-- Safety: every statement is additive and idempotent. No column is renamed or
-- dropped, no row is rewritten, and every new column is nullable or defaulted,
-- so existing rows and existing inserts keep working unchanged.

BEGIN;

-- Thesis summary provenance / versioning -----------------------------------
ALTER TABLE ai_intelligence.thesis_summaries
    ADD COLUMN IF NOT EXISTS source_hash TEXT;

ALTER TABLE ai_intelligence.thesis_summaries
    ADD COLUMN IF NOT EXISTS source_version TEXT;

ALTER TABLE ai_intelligence.thesis_summaries
    ADD COLUMN IF NOT EXISTS generated_at TIMESTAMP;

ALTER TABLE ai_intelligence.thesis_summaries
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

-- NULL means "this row is the current version".
ALTER TABLE ai_intelligence.thesis_summaries
    ADD COLUMN IF NOT EXISTS superseded_by TEXT;

CREATE INDEX IF NOT EXISTS ix_thesis_summaries_current
    ON ai_intelligence.thesis_summaries (backend_thesis_id, user_id, superseded_by);

-- Memory last-used tracking ------------------------------------------------
ALTER TABLE ai_intelligence.researcher_memories
    ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP;

COMMIT;
