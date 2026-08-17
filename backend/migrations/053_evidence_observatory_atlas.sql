-- Sovereign Evidence Observatory Atlas v1
-- Research intake is private/quarantined by default. Publication requires
-- deterministic gate + passport readback and never equates engagement with truth.

CREATE TABLE IF NOT EXISTS evidence_observatory_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    claim TEXT NOT NULL,
    claim_sha256 CHAR(64) NOT NULL,
    verdict TEXT NOT NULL DEFAULT 'UNPROVEN'
        CHECK (verdict IN ('SUPPORTED','REFUTED','UNPROVEN','NOT_APPLICABLE')),
    evidence_class TEXT,
    workflow_state TEXT NOT NULL DEFAULT 'QUARANTINED'
        CHECK (workflow_state IN ('QUARANTINED','PUBLISHABLE','PUBLISHED')),
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private','public')),
    source_kind TEXT NOT NULL,
    source_locator TEXT,
    external_key TEXT NOT NULL UNIQUE,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    case_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    gate_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    passport JSONB NOT NULL DEFAULT '{}'::jsonb,
    passport_sha256 CHAR(64),
    case_sha256 CHAR(64),
    as_of TIMESTAMPTZ,
    created_by UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evidence_observatory_public_state_ck CHECK (
        visibility <> 'public' OR workflow_state IN ('PUBLISHABLE','PUBLISHED')
    ),
    CONSTRAINT evidence_observatory_published_receipt_ck CHECK (
        workflow_state <> 'PUBLISHED' OR published_at IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_evidence_observatory_cases_project
    ON evidence_observatory_cases (project_id, workflow_state, as_of);
CREATE INDEX IF NOT EXISTS idx_evidence_observatory_cases_claim_sha
    ON evidence_observatory_cases (claim_sha256);
CREATE INDEX IF NOT EXISTS idx_evidence_observatory_cases_public
    ON evidence_observatory_cases (as_of, id)
    WHERE visibility='public' AND workflow_state IN ('PUBLISHABLE','PUBLISHED');
CREATE INDEX IF NOT EXISTS idx_evidence_observatory_cases_payload_gin
    ON evidence_observatory_cases USING GIN (case_payload jsonb_path_ops);

CREATE TABLE IF NOT EXISTS evidence_observatory_publish_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL UNIQUE,
    repo_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    commit_oid TEXT NOT NULL,
    data_path TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    data_sha256 CHAR(64) NOT NULL,
    manifest_sha256 CHAR(64) NOT NULL,
    case_ids JSONB NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PUBLISHED')),
    readback_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evidence_observatory_publish_readback_ck CHECK (readback_verified = TRUE)
);

CREATE INDEX IF NOT EXISTS idx_evidence_observatory_publish_receipts_created
    ON evidence_observatory_publish_receipts (created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_observatory_arena_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES evidence_observatory_cases(id) ON DELETE RESTRICT,
    user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE RESTRICT,
    route_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    llm_request_id UUID NOT NULL,
    response_sha256 CHAR(64) NOT NULL,
    metrics JSONB NOT NULL,
    run_sha256 CHAR(64) NOT NULL,
    settlement_evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, llm_request_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_observatory_arena_case
    ON evidence_observatory_arena_runs (case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_observatory_arena_model
    ON evidence_observatory_arena_runs (model_id, provider, created_at DESC);
