-- Migration 0001: initial schema + role model
-- ==========================================================================
-- Implements: ADR-007 (content corpus read-only at runtime), ADR-008
--   (event-sourced progress), ADR-009 (learner-data isolation), ADR-011
--   (Render managed PostgreSQL/pgvector), INV-SEC-001 (runtime read-only
--   vector role), INV-AUTH-001 (owner-scoped tables), INV-PROG-001.
--
-- APPLIED MIGRATIONS ARE IMMUTABLE (structural-constraints.md S2). A change is
-- a new migration file; never edit this one after it is applied.
--
-- Roles created here:
--   app_runtime   : the Render web service role. SELECT-only on the corpus
--                   (content_*), read/write on learner tables. NO DDL. NO write
--                   on content_chunks/content_sources -> INV-SEC-001.
--   ingest_admin  : the offline ingestion role. Write on the corpus.
--                   NEVER given to the Render service.
--   owner         : the migration/DDL path (Render's default DB user). Runs
--                   this file once; the app never connects as owner.
--
-- Passwords are deliberately NOT set here. Set them out of band; no secret is
-- ever committed to the repository (guard_secret).
-- ==========================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
        CREATE ROLE app_runtime NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ingest_admin') THEN
        CREATE ROLE ingest_admin NOLOGIN;
    END IF;
END
$$;

-- Learner-scoped tables (written by app_runtime; owner-scoped by INV-AUTH-001)
CREATE TABLE IF NOT EXISTS users (
    user_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    salt           TEXT NOT NULL,
    cefr_level     TEXT NOT NULL CHECK (cefr_level IN ('A1', 'A2', 'B1', 'B2')),
    language       TEXT NOT NULL DEFAULT 'en' CHECK (language = 'en'),
    learning_goals TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    issued_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS user_vocabulary (
    user_id        UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    entry_id       TEXT NOT NULL,
    state          TEXT NOT NULL CHECK (state IN ('learning', 'familiar', 'mastered')),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, entry_id)
);

-- Event-sourced progress (ADR-008). Append-only; no update/delete granted.
CREATE TABLE IF NOT EXISTS learning_events (
    event_id          BIGSERIAL PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    event_type        TEXT NOT NULL,
    payload           JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key   TEXT NOT NULL,
    corrects_event_id BIGINT REFERENCES learning_events(event_id),
    occurred_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_events_user_time ON learning_events(user_id, occurred_at);

-- Content corpus (ADR-007). Written ONLY by ingest_admin, read-only at runtime.
CREATE TABLE IF NOT EXISTS content_sources (
    source_id     TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    language      TEXT NOT NULL DEFAULT 'en' CHECK (language = 'en'),
    level         TEXT NOT NULL CHECK (level IN ('A1', 'A2', 'B1', 'B2')),
    topic         TEXT,
    review_status TEXT NOT NULL CHECK (review_status IN ('draft', 'published', 'retired')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS content_chunks (
    chunk_id    TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES content_sources(source_id),
    section     TEXT NOT NULL,
    ordinal     INTEGER NOT NULL,
    text        TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    embedding   vector(1536),
    UNIQUE (source_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON content_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON content_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS content_audit (
    audit_id   BIGSERIAL PRIMARY KEY,
    event      TEXT NOT NULL,
    source_id  TEXT,
    actor      TEXT NOT NULL,
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- GRANTS - app_runtime (INV-SEC-001: corpus read-only; no DDL)
GRANT USAGE ON SCHEMA public TO app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, sessions, user_vocabulary TO app_runtime;
GRANT SELECT, INSERT ON learning_events TO app_runtime;
GRANT USAGE, SELECT ON SEQUENCE learning_events_event_id_seq TO app_runtime;
GRANT SELECT ON content_sources, content_chunks, content_audit TO app_runtime;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON content_sources, content_chunks, content_audit FROM app_runtime;

-- GRANTS - ingest_admin (offline only; never used by the Render service)
GRANT USAGE ON SCHEMA public TO ingest_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON content_sources, content_chunks, content_audit TO ingest_admin;
GRANT USAGE, SELECT ON SEQUENCE content_audit_audit_id_seq TO ingest_admin;

COMMIT;
