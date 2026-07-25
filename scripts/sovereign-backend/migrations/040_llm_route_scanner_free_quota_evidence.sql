-- Extend the candidate-only scanner with bounded Free-quota provenance.
-- No candidate becomes routing eligible in this migration. Promotion remains a
-- disabled onboarding record until managed FreeLLM canaries and receipts pass.
BEGIN;

DO $$
BEGIN
    IF to_regclass('llm_route_scanner_candidates') IS NOT NULL THEN
        ALTER TABLE llm_route_scanner_candidates
            ADD COLUMN IF NOT EXISTS free_quota_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS source_consensus BOOLEAN NOT NULL DEFAULT false;

        ALTER TABLE llm_route_scanner_candidates
            DROP CONSTRAINT IF EXISTS llm_route_scanner_candidates_free_quota_evidence_check;
        ALTER TABLE llm_route_scanner_candidates
            ADD CONSTRAINT llm_route_scanner_candidates_free_quota_evidence_check
            CHECK (jsonb_typeof(free_quota_evidence) = 'array');

        CREATE INDEX IF NOT EXISTS idx_llm_route_scanner_candidates_consensus
            ON llm_route_scanner_candidates
            (source_consensus, status, last_checked_at DESC);

        COMMENT ON COLUMN llm_route_scanner_candidates.free_quota_evidence IS
            'Bounded source claims for free quota/model identifiers only; price and cost fields are not parsed.';
        COMMENT ON COLUMN llm_route_scanner_candidates.source_consensus IS
            'True only when independent source authorities agree, or one seed and one public authority agree.';
    END IF;
END $$;

COMMIT;
