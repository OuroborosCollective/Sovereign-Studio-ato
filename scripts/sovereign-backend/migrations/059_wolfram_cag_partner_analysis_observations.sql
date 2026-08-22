BEGIN;

-- Optional observation/identity columns for the Wolfram CAG partner analysis
-- ledger (#1626). All additions are nullable or default-empty so existing
-- rows from the v1 lane remain valid; validation stays fail-closed in the
-- canonical agent_runtime module.
ALTER TABLE wolfram_cag_analysis_records
    ADD COLUMN IF NOT EXISTS sovereign_run_id TEXT,
    ADD COLUMN IF NOT EXISTS toolchain_step_id TEXT,
    ADD COLUMN IF NOT EXISTS failure_family TEXT,
    ADD COLUMN IF NOT EXISTS quota_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS rate_limit_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
