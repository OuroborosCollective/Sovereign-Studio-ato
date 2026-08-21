BEGIN;

CREATE TABLE IF NOT EXISTS wolfram_cag_analysis_records (
    analysis_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK (schema_version = 'sovereign.wolfram-cag-partner-analysis.v1'),
    record_sha256 CHAR(64) NOT NULL UNIQUE CHECK (record_sha256 ~ '^[0-9a-f]{64}$'),
    repository_revision CHAR(40) CHECK (repository_revision IS NULL OR repository_revision ~ '^[0-9a-f]{40}$'),
    runtime_revision CHAR(40) CHECK (runtime_revision IS NULL OR runtime_revision ~ '^[0-9a-f]{40}$'),
    cag_component TEXT NOT NULL CHECK (cag_component IN (
        'WolframLanguageHints',
        'WolframLanguageComputation',
        'WolframAlphaResults',
        'WolframAlphaContext'
    )),
    cag_contract_version TEXT NOT NULL,
    normalized_question TEXT NOT NULL,
    normalized_input_sha256 CHAR(64) NOT NULL CHECK (normalized_input_sha256 ~ '^[0-9a-f]{64}$'),
    provider_request_id TEXT,
    provider_response_uuid TEXT,
    provider_response_sha256 CHAR(64) CHECK (provider_response_sha256 IS NULL OR provider_response_sha256 ~ '^[0-9a-f]{64}$'),
    credential_fingerprint_sha256 CHAR(64) CHECK (credential_fingerprint_sha256 IS NULL OR credential_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
    verdict TEXT NOT NULL CHECK (verdict IN ('SUPPORTED', 'CONTRADICTED', 'INCONCLUSIVE', 'UNAVAILABLE')),
    documentation_class TEXT NOT NULL CHECK (documentation_class IN (
        'PRIVATE_PROVIDER_EVIDENCE',
        'PARTNER_REPORTABLE',
        'PUBLIC_DERIVED_RECEIPT',
        'HF_PUBLISHED_VERIFIED'
    )),
    derived_conclusion TEXT NOT NULL,
    assumptions JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(assumptions) = 'array'),
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(limitations) = 'array'),
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(source_refs) = 'array'),
    evidence_passport_hash CHAR(64) CHECK (evidence_passport_hash IS NULL OR evidence_passport_hash ~ '^[0-9a-f]{64}$'),
    hf_publication_ref TEXT,
    hf_target_revision TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        verdict NOT IN ('SUPPORTED', 'CONTRADICTED')
        OR provider_response_sha256 IS NOT NULL
    ),
    CHECK (
        documentation_class <> 'HF_PUBLISHED_VERIFIED'
        OR (hf_publication_ref IS NOT NULL AND hf_target_revision IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_wolfram_cag_analysis_records_created
    ON wolfram_cag_analysis_records (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wolfram_cag_analysis_records_component
    ON wolfram_cag_analysis_records (cag_component, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wolfram_cag_analysis_records_verdict
    ON wolfram_cag_analysis_records (verdict, documentation_class);

COMMIT;
