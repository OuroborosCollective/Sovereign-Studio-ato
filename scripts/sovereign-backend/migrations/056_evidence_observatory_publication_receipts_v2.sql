-- Evidence Observatory publisher receipt v2 (#1507)
-- Persist every publication-only binding needed to replay a Hugging Face write.

ALTER TABLE evidence_observatory_publish_receipts
    ADD COLUMN IF NOT EXISTS batch_sha256 CHAR(64),
    ADD COLUMN IF NOT EXISTS license_rights_sha256 CHAR(64),
    ADD COLUMN IF NOT EXISTS privacy_scan_sha256 CHAR(64),
    ADD COLUMN IF NOT EXISTS publisher_policy_sha256 CHAR(64),
    ADD COLUMN IF NOT EXISTS expected_target TEXT,
    ADD COLUMN IF NOT EXISTS observed_target TEXT,
    ADD COLUMN IF NOT EXISTS observed_target_revision TEXT,
    ADD COLUMN IF NOT EXISTS observed_artifact_hashes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS write_attempt_identity CHAR(64),
    ADD COLUMN IF NOT EXISTS readback_identity CHAR(64),
    ADD COLUMN IF NOT EXISTS publication_status TEXT,
    ADD COLUMN IF NOT EXISTS publication_receipt JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS publication_receipt_sha256 CHAR(64);

UPDATE evidence_observatory_publish_receipts
SET publication_status = CASE
    WHEN readback_verified THEN 'PUBLISHED_VERIFIED'
    ELSE 'PENDING_READBACK'
END
WHERE publication_status IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evidence_observatory_publish_status_v2_ck'
    ) THEN
        ALTER TABLE evidence_observatory_publish_receipts
            ADD CONSTRAINT evidence_observatory_publish_status_v2_ck CHECK (
                publication_status IN (
                    'PUBLISHED_VERIFIED', 'PUBLISHED_CONTRADICTED', 'PENDING_READBACK', 'BLOCKED'
                )
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evidence_observatory_publish_receipt_v2_ck'
    ) THEN
        ALTER TABLE evidence_observatory_publish_receipts
            ADD CONSTRAINT evidence_observatory_publish_receipt_v2_ck CHECK (
                publication_status <> 'PUBLISHED_VERIFIED'
                OR (
                    readback_verified = TRUE
                    AND batch_sha256 IS NOT NULL
                    AND license_rights_sha256 IS NOT NULL
                    AND privacy_scan_sha256 IS NOT NULL
                    AND publisher_policy_sha256 IS NOT NULL
                    AND observed_target_revision IS NOT NULL
                    AND write_attempt_identity IS NOT NULL
                    AND readback_identity IS NOT NULL
                    AND publication_receipt_sha256 IS NOT NULL
                )
                OR publication_receipt = '{}'::jsonb
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_observatory_publish_receipts_batch_sha_v2
    ON evidence_observatory_publish_receipts (batch_sha256)
    WHERE batch_sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_observatory_publish_receipts_target_revision_v2
    ON evidence_observatory_publish_receipts (observed_target_revision)
    WHERE observed_target_revision IS NOT NULL;
