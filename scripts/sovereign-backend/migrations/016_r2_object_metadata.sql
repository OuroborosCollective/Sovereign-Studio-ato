-- Cloudflare R2 object metadata and ownership truth.
-- Bytes stay in private R2 buckets. PostgreSQL stores ownership, hashes,
-- lifecycle state and links to knowledge sources or agent jobs.
BEGIN;

CREATE TABLE IF NOT EXISTS sovereign_objects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    bucket_name TEXT NOT NULL,
    object_key TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    source_id UUID REFERENCES knowledge_sources(id) ON DELETE SET NULL,
    job_id TEXT REFERENCES sovereign_agent_jobs(job_id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    etag TEXT,
    blocker TEXT,
    retention_until TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT sovereign_objects_bucket_check CHECK (
        bucket_name IN ('sovereign-knowledge-files', 'sovereign-runtime-artifacts')
    ),
    CONSTRAINT sovereign_objects_sha_check CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT sovereign_objects_size_check CHECK (size_bytes > 0),
    CONSTRAINT sovereign_objects_key_check CHECK (
        object_key <> ''
        AND object_key !~ '(^/|\\\\|(^|/)\.\.(/|$)|//)'
    ),
    CONSTRAINT sovereign_objects_status_check CHECK (
        status IN ('pending', 'uploaded', 'verifying', 'verified', 'processing', 'completed', 'blocked', 'deleted')
    ),
    CONSTRAINT sovereign_objects_owner_prefix_check CHECK (
        object_key LIKE ('users/' || user_id::text || '/%')
    ),
    CONSTRAINT sovereign_objects_link_check CHECK (
        NOT (source_id IS NOT NULL AND job_id IS NOT NULL)
    ),
    UNIQUE (bucket_name, object_key)
);

CREATE INDEX IF NOT EXISTS idx_sovereign_objects_user_created
    ON sovereign_objects (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sovereign_objects_source
    ON sovereign_objects (source_id) WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sovereign_objects_job
    ON sovereign_objects (job_id) WHERE job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sovereign_objects_retention
    ON sovereign_objects (retention_until)
    WHERE deleted_at IS NULL AND retention_until IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sovereign_objects_pending
    ON sovereign_objects (status, created_at)
    WHERE status IN ('pending', 'uploaded', 'verifying', 'blocked');

CREATE OR REPLACE FUNCTION update_sovereign_object_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    IF NEW.status = 'deleted' AND NEW.deleted_at IS NULL THEN
        NEW.deleted_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_sovereign_object_timestamp ON sovereign_objects;
CREATE TRIGGER trigger_update_sovereign_object_timestamp
    BEFORE UPDATE ON sovereign_objects
    FOR EACH ROW EXECUTE FUNCTION update_sovereign_object_timestamp();

COMMENT ON TABLE sovereign_objects IS
    'PostgreSQL ownership and SHA-256 evidence for private Cloudflare R2 objects; binary payloads are never stored here.';
COMMENT ON COLUMN sovereign_objects.object_key IS
    'Server-generated private key. Must remain under users/<user-id>/ and is never accepted from frontend input.';

COMMIT;
