BEGIN;

ALTER TABLE sovereign_rescue_repairs
    ADD COLUMN IF NOT EXISTS published_head_sha CHAR(40);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'sovereign_rescue_published_head_sha_check'
          AND conrelid = 'sovereign_rescue_repairs'::regclass
    ) THEN
        ALTER TABLE sovereign_rescue_repairs
            ADD CONSTRAINT sovereign_rescue_published_head_sha_check
            CHECK (
                published_head_sha IS NULL
                OR published_head_sha ~ '^[0-9a-f]{40}$'
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_sovereign_rescue_published_head
    ON sovereign_rescue_repairs(published_head_sha)
    WHERE published_head_sha IS NOT NULL;

COMMENT ON COLUMN sovereign_rescue_repairs.published_head_sha IS
    'Exact isolated-workspace commit published before Draft PR creation; ProofPack must match it to the live PR head.';

COMMIT;
