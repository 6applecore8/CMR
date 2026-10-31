-- Candidate migration for an isolated test database. Review before any deployment.
-- Intentionally fails if legacy session rows exist; no implicit session conversion.
BEGIN;
ALTER TABLE crm_session
    ADD COLUMN csrf_hash CHAR(64) NOT NULL CHECK (csrf_hash ~ '^[0-9a-f]{64}$'),
    ADD COLUMN role_snapshot TEXT NOT NULL CHECK (role_snapshot IN ('sales', 'manager')),
    ADD CONSTRAINT crm_session_token_hash_format CHECK (token_hash ~ '^[0-9a-f]{64}$');
COMMIT;
