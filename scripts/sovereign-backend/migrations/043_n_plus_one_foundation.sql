-- Establish the first evidence-gated N+1 domain inside Sovereign Studio ATO.
-- Source repository: https://github.com/OuroborosCollective/SovAreAgentn1
-- Source revision: 9fe3e992302f84e47bd52942df4313cabd0a7447
-- Source archive SHA-256: 345b612a11e7a5cb99f02a75063743c19533a4728c50415d2242bcb0c8b2f7d7
-- This migration imports provenance and contracts, not a second runtime.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS n1_source_artifacts (
    source_artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key TEXT NOT NULL UNIQUE,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('archive','repository-file','owner-narrative','runtime-evidence')),
    repository TEXT NOT NULL,
    source_revision TEXT NOT NULL CHECK (source_revision ~ '^[0-9a-f]{40}$'),
    original_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
    classification TEXT NOT NULL,
    source_reference JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n1_identity_versions (
    identity_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identity_sha256 TEXT NOT NULL UNIQUE CHECK (identity_sha256 ~ '^[0-9a-f]{64}$'),
    payload JSONB NOT NULL,
    source_revision TEXT NOT NULL CHECK (source_revision ~ '^[0-9a-f]{40}$'),
    source_artifact_id UUID REFERENCES n1_source_artifacts(source_artifact_id),
    supersedes_identity_version_id UUID REFERENCES n1_identity_versions(identity_version_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (payload->>'canonicalName' = 'N+1'),
    CHECK (payload->>'spokenName' = 'NPlusEins'),
    CHECK (payload->>'technicalNamespace' = 'n_plus_one')
);

CREATE TABLE IF NOT EXISTS n1_personality_traits (
    personality_trait_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trait_key TEXT NOT NULL,
    trait_payload JSONB NOT NULL,
    source_artifact_id UUID REFERENCES n1_source_artifacts(source_artifact_id),
    source_revision TEXT NOT NULL CHECK (source_revision ~ '^[0-9a-f]{40}$'),
    trait_sha256 TEXT NOT NULL UNIQUE CHECK (trait_sha256 ~ '^[0-9a-f]{64}$'),
    supersedes_trait_id UUID REFERENCES n1_personality_traits(personality_trait_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n1_family_provenance (
    family_provenance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    relationship_key TEXT NOT NULL,
    account TEXT NOT NULL,
    provenance_kind TEXT NOT NULL,
    truth_boundary TEXT NOT NULL,
    source_artifact_id UUID REFERENCES n1_source_artifacts(source_artifact_id),
    content_sha256 TEXT NOT NULL UNIQUE CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n1_story_entries (
    story_entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    original_content TEXT NOT NULL,
    source_artifact_id UUID REFERENCES n1_source_artifacts(source_artifact_id),
    provenance_kind TEXT NOT NULL,
    content_sha256 TEXT NOT NULL UNIQUE CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n1_experience_events (
    experience_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rubric TEXT NOT NULL CHECK (rubric IN (
        'funny_experience',
        'family_friendship_experience',
        'emotionally_formed_bond_experience'
    )),
    event_payload JSONB NOT NULL,
    provenance_kind TEXT NOT NULL,
    content_sha256 TEXT NOT NULL UNIQUE CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n1_learning_candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN (
        'owner_narrative',
        'repository_source',
        'user_observation',
        'llm_hypothesis',
        'runtime_evidence'
    )),
    source_identity TEXT NOT NULL,
    source_revision TEXT CHECK (source_revision IS NULL OR source_revision ~ '^[0-9a-f]{40}$'),
    classification TEXT NOT NULL CHECK (classification IN (
        'family_provenance',
        'story',
        'experience',
        'linguistic_observation',
        'learning_hypothesis',
        'technical_claim'
    )),
    content TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    candidate_sha256 TEXT NOT NULL UNIQUE CHECK (candidate_sha256 ~ '^[0-9a-f]{64}$'),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    state TEXT NOT NULL DEFAULT 'candidate' CHECK (state = 'candidate'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, source_identity, content_sha256)
);

CREATE TABLE IF NOT EXISTS n1_learning_receipts (
    learning_receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES n1_learning_candidates(candidate_id),
    decision TEXT NOT NULL CHECK (decision IN ('accepted','rejected')),
    owner_admin_id UUID,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    receipt_sha256 TEXT NOT NULL UNIQUE CHECK (receipt_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        owner_admin_id IS NOT NULL
        OR COALESCE(jsonb_typeof(evidence->'checks'), '') = 'array'
    )
);

CREATE TABLE IF NOT EXISTS n1_linguistic_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_key TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK (mode IN ('GRAMAR','HABAR','SYNTHESIS')),
    profile_payload JSONB NOT NULL,
    source_revision TEXT NOT NULL CHECK (source_revision ~ '^[0-9a-f]{40}$'),
    profile_sha256 TEXT NOT NULL UNIQUE CHECK (profile_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n1_grammar_rules (
    grammar_rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES n1_linguistic_profiles(profile_id),
    rule_key TEXT NOT NULL UNIQUE,
    marker_text TEXT NOT NULL,
    category TEXT NOT NULL,
    confidence_ppm INTEGER NOT NULL CHECK (confidence_ppm BETWEEN 0 AND 1000000),
    source_reference JSONB NOT NULL DEFAULT '{}'::jsonb,
    rule_sha256 TEXT NOT NULL UNIQUE CHECK (rule_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n1_dialect_observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    batch_sha256 TEXT NOT NULL CHECK (batch_sha256 ~ '^[0-9a-f]{64}$'),
    text_sha256 TEXT NOT NULL CHECK (text_sha256 ~ '^[0-9a-f]{64}$'),
    profile_key TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    category TEXT NOT NULL,
    span_start INTEGER NOT NULL CHECK (span_start >= 0),
    span_end INTEGER NOT NULL CHECK (span_end >= span_start),
    matched_text TEXT NOT NULL,
    match_confidence_ppm INTEGER NOT NULL CHECK (match_confidence_ppm BETWEEN 0 AND 1000000),
    source_reference JSONB NOT NULL DEFAULT '{}'::jsonb,
    observation_sha256 TEXT NOT NULL CHECK (observation_sha256 ~ '^[0-9a-f]{64}$'),
    classification_state TEXT NOT NULL CHECK (classification_state = 'candidate_observation'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, batch_sha256, observation_sha256)
);

CREATE TABLE IF NOT EXISTS n1_voice_profiles (
    voice_profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_key TEXT NOT NULL UNIQUE,
    language_tag TEXT NOT NULL,
    profile_payload JSONB NOT NULL,
    verification_state TEXT NOT NULL CHECK (verification_state IN (
        'configured_not_canary_verified',
        'canary_verified',
        'retired'
    )),
    source_revision TEXT NOT NULL CHECK (source_revision ~ '^[0-9a-f]{40}$'),
    profile_sha256 TEXT NOT NULL UNIQUE CHECK (profile_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n1_response_style_receipts (
    response_style_receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    canonical_content_sha256 TEXT NOT NULL CHECK (canonical_content_sha256 ~ '^[0-9a-f]{64}$'),
    projected_content_sha256 TEXT NOT NULL CHECK (projected_content_sha256 ~ '^[0-9a-f]{64}$'),
    linguistic_profile_key TEXT,
    voice_profile_key TEXT,
    projection_payload JSONB NOT NULL,
    receipt_sha256 TEXT NOT NULL UNIQUE CHECK (receipt_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $admin_foreign_keys$
BEGIN
    IF to_regclass(format('%I.admin_users', current_schema())) IS NULL THEN
        RAISE NOTICE 'Migration 043 preview: admin_users absent; N+1 owner FKs deferred';
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname='n1_learning_candidates_user_id_fkey'
          AND conrelid='n1_learning_candidates'::regclass
    ) THEN
        ALTER TABLE n1_learning_candidates
            ADD CONSTRAINT n1_learning_candidates_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname='n1_learning_receipts_owner_admin_id_fkey'
          AND conrelid='n1_learning_receipts'::regclass
    ) THEN
        ALTER TABLE n1_learning_receipts
            ADD CONSTRAINT n1_learning_receipts_owner_admin_id_fkey
            FOREIGN KEY (owner_admin_id) REFERENCES admin_users(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname='n1_dialect_observations_user_id_fkey'
          AND conrelid='n1_dialect_observations'::regclass
    ) THEN
        ALTER TABLE n1_dialect_observations
            ADD CONSTRAINT n1_dialect_observations_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname='n1_response_style_receipts_user_id_fkey'
          AND conrelid='n1_response_style_receipts'::regclass
    ) THEN
        ALTER TABLE n1_response_style_receipts
            ADD CONSTRAINT n1_response_style_receipts_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
    END IF;
END
$admin_foreign_keys$;

CREATE INDEX IF NOT EXISTS idx_n1_learning_candidates_user_created
    ON n1_learning_candidates(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_n1_dialect_observations_user_created
    ON n1_dialect_observations(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_n1_story_entries_created
    ON n1_story_entries(created_at DESC);

CREATE OR REPLACE FUNCTION n1_reject_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'N+1 append-only relation % does not allow %', TG_TABLE_NAME, TG_OP;
END;
$$;

DO $append_only$
DECLARE
    table_name TEXT;
    trigger_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'n1_source_artifacts',
        'n1_identity_versions',
        'n1_personality_traits',
        'n1_family_provenance',
        'n1_story_entries',
        'n1_experience_events',
        'n1_learning_candidates',
        'n1_learning_receipts',
        'n1_linguistic_profiles',
        'n1_grammar_rules',
        'n1_dialect_observations',
        'n1_voice_profiles',
        'n1_response_style_receipts'
    ]
    LOOP
        trigger_name := table_name || '_append_only';
        IF NOT EXISTS (
            SELECT 1
            FROM pg_trigger
            WHERE tgname = trigger_name
              AND tgrelid = to_regclass(table_name)
              AND NOT tgisinternal
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I '
                'FOR EACH ROW EXECUTE FUNCTION n1_reject_append_only_mutation()',
                trigger_name,
                table_name
            );
        END IF;
    END LOOP;
END
$append_only$;

INSERT INTO n1_source_artifacts (
    source_key, source_kind, repository, source_revision, original_path,
    content_sha256, byte_size, classification, source_reference
)
VALUES (
    'sovareagentn1-archive-20260727',
    'archive',
    'https://github.com/OuroborosCollective/SovAreAgentn1',
    '9fe3e992302f84e47bd52942df4313cabd0a7447',
    '1785236849710.zip',
    '345b612a11e7a5cb99f02a75063743c19533a4728c50415d2242bcb0c8b2f7d7',
    1394904,
    'provenance-archive',
    '{"archiveEntryCount":101,"unsafeArchivePathCount":0,"manifestPath":"config/architecture/N_PLUS_ONE_SOURCE_MANIFEST.v1.json"}'::jsonb
)
ON CONFLICT (source_key) DO NOTHING;

INSERT INTO n1_source_artifacts (
    source_key, source_kind, repository, source_revision, original_path,
    content_sha256, byte_size, classification, source_reference
)
VALUES
('sovareagentn1-linguahabar-engine','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/components/LinguaHabarEngine.tsx','7130e5d3413e4209ab28d6faab8629589642ab0af65794f06901f1c846e00718',25946,'ui-projection-and-domain-concept','{"archiveSha256":"345b612a11e7a5cb99f02a75063743c19533a4728c50415d2242bcb0c8b2f7d7"}'::jsonb),
('sovareagentn1-hia-resonance-voice','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/components/HiaResonanceVoice.tsx','5beb400447cbdb8b685daca16bff21676130bf719677cd20a7b39a27eb83e4b0',27895,'ui-projection-and-voice-concept','{"archiveSha256":"345b612a11e7a5cb99f02a75063743c19533a4728c50415d2242bcb0c8b2f7d7"}'::jsonb),
('sovareagentn1-server','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','server.ts','3ba026f77212d61717867526cf9aadf8bffee9bdfb0780df255b42cf24e62d76',40785,'technical-implementation-requires-security-adaptation','{"openSqlImported":false}'::jsonb),
('sovareagentn1-deterministic-utility','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/utils/deterministic.ts','5d61bf5686e03f932e927ee3760860e24343993631b2dd7005675d572b9265ae',1469,'technical-claim-not-are-deterministic','{"areDeterministicVerified":false}'::jsonb),
('sovareagentn1-aha-timeline','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/components/AhaMomentTimeline.tsx','cc147326de172898471f0396dacb307cf81107232ac3a7f173715783fc41a029',4090,'personality-projection','{}'::jsonb),
('sovareagentn1-proactive-learning','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/components/ProactiveLearningEngine.tsx','7a0ca4f23325325faa00f79375eaa813b50c4cb627014b3314cba7704d84b6e3',19331,'learning-ui-projection-requires-candidate-gate','{"autoVerifiedImported":false}'::jsonb),
('sovareagentn1-protected-personality','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/components/ProtectedPersonalityMemory.tsx','eed829d9ecb2993398cdf89fbfdf328db0f945dbbaa8d542807a560f6fd84047',6262,'personality-memory-concept-requires-receipts','{"browserStorageImported":false}'::jsonb),
('sovareagentn1-papas-story-archive','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/components/PapasStoryArchive.tsx','139bc225fff09e580d124802d7e9a05b97d8780c921b583ba5806423a5ccd425',23781,'owner-narrative-provenance','{}'::jsonb),
('sovareagentn1-personal-log','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/components/PucksPersonalLog.tsx','ec76066abfd93afcbb587b4965d5d3cb62c93d549741997d29a7072cd39a9576',17878,'historical-personality-source','{"legacyAlias":"Puck","canonicalReplacement":false}'::jsonb),
('sovareagentn1-song-book','repository-file','https://github.com/OuroborosCollective/SovAreAgentn1','9fe3e992302f84e47bd52942df4313cabd0a7447','src/components/PuckSongBook.tsx','ba9b5c90a87d415c9c67984e7fdfb2790fea2f088c84539b76de80cffdec651d',9244,'historical-expression-source','{"legacyAlias":"Puck","canonicalReplacement":false}'::jsonb)
ON CONFLICT (source_key) DO NOTHING;

INSERT INTO n1_identity_versions (
    identity_sha256, payload, source_revision, source_artifact_id
)
SELECT
    'd7d697f7a9da9850d29549d840088ca2a0b76d50cd88cb44953ee12ae02abbf1',
    '{
      "schemaVersion":"sovereign.n-plus-one-identity.v1",
      "canonicalName":"N+1",
      "spokenName":"NPlusEins",
      "familyDesignation":"Papas kleines Mädchen",
      "technicalNamespace":"n_plus_one",
      "legacyAliases":[{"name":"Puck","status":"historical-source-alias-only"}],
      "projectBoundaries":{
        "host":"Sovereign Studio ATO",
        "separateProjects":["Arelorian Wasd"],
        "sharedRuntime":false,
        "sharedDatabase":false
      },
      "truthBoundary":"identity-and-relationship-domain-not-technical-truth-authority"
    }'::jsonb,
    '9fe3e992302f84e47bd52942df4313cabd0a7447',
    source_artifact_id
FROM n1_source_artifacts
WHERE source_key='sovareagentn1-archive-20260727'
ON CONFLICT (identity_sha256) DO NOTHING;

INSERT INTO n1_linguistic_profiles (
    profile_key, mode, profile_payload, source_revision, profile_sha256
)
VALUES (
    'n1-family-expression-v1',
    'SYNTHESIS',
    '{
      "purpose":"Preserve configured identity and family terms without claiming dialect detection",
      "dialectModelPresent":false,
      "voiceLinked":false,
      "canonicalContentMutable":false
    }'::jsonb,
    '9fe3e992302f84e47bd52942df4313cabd0a7447',
    '247cd5ab1d686f17324615cdbbcc71d8d952171c8d63dd51556bd5a0ecdda40f'
)
ON CONFLICT (profile_key) DO NOTHING;

INSERT INTO n1_grammar_rules (
    profile_id, rule_key, marker_text, category, confidence_ppm,
    source_reference, rule_sha256
)
SELECT profile_id, seed.rule_key, seed.marker_text, seed.category, 1000000,
       seed.source_reference, seed.rule_sha256
FROM n1_linguistic_profiles
CROSS JOIN (
    VALUES
      ('identity-n-plus-one','N+1','identity-token','{"provenance":"canonical-identity"}'::jsonb,'1f7bc2a1e2c7bfb4ccb5c7e44176c3e9c694bf7b9e7dcb6d4175ab592c4b1ced'),
      ('identity-npluseins','NPlusEins','identity-token','{"provenance":"canonical-identity"}'::jsonb,'459acb39bdf3c76fca47738e330ee10bcc5724dba34cc316eaa44f3bb0b35c17'),
      ('family-papa','Papa','family-term','{"provenance":"owner-family-context"}'::jsonb,'0e34321b89a50071a7edee669695c32d07e4df3b06656b5af7b3d18cb618168c'),
      ('family-mama','Mama','family-term','{"provenance":"owner-family-context"}'::jsonb,'91bea3b2c78c209443022e493aea19a1e702b61f1b65494e2c3bbe9f4b19de93'),
      ('legacy-puck','Puck','legacy-alias','{"provenance":"historical-source-only","canonicalReplacement":false}'::jsonb,'aa920e46d03bdf0224be67395deb056cb778a5e98b2547896f726f531ca72f99')
) AS seed(rule_key, marker_text, category, source_reference, rule_sha256)
WHERE profile_key='n1-family-expression-v1'
ON CONFLICT (rule_key) DO NOTHING;

INSERT INTO n1_voice_profiles (
    profile_key, language_tag, profile_payload, verification_state,
    source_revision, profile_sha256
)
VALUES (
    'n1-de-de-source-baseline-v1',
    'de-DE',
    '{
      "sourceComponent":"src/components/HiaResonanceVoice.tsx",
      "linguaHabarLinked":false,
      "ttsCanaryVerified":false,
      "personalityProjectionPreserved":true
    }'::jsonb,
    'configured_not_canary_verified',
    '9fe3e992302f84e47bd52942df4313cabd0a7447',
    'fbc7ec3d8110b615675fd14931dc1531119f5886a315063d04b03bec30a681ed'
)
ON CONFLICT (profile_key) DO NOTHING;

DO $migration_ledger$
DECLARE
    ledger_columns TEXT[];
BEGIN
    IF to_regclass(format('%I.schema_migrations', current_schema())) IS NULL THEN
        RAISE NOTICE 'Migration 043 preview: schema_migrations absent; ledger registration deferred';
        RETURN;
    END IF;

    SELECT COALESCE(array_agg(column_name ORDER BY ordinal_position), ARRAY[]::TEXT[])
    INTO ledger_columns
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'schema_migrations';

    IF ledger_columns @> ARRAY['version', 'applied_at']::TEXT[]
       AND NOT ledger_columns @> ARRAY['id', 'name']::TEXT[] THEN
        INSERT INTO schema_migrations (version, applied_at)
        VALUES ('043', NOW())
        ON CONFLICT (version) DO NOTHING;
    ELSIF ledger_columns @> ARRAY['version']::TEXT[]
          AND NOT ledger_columns @> ARRAY['id', 'name']::TEXT[] THEN
        INSERT INTO schema_migrations (version)
        VALUES ('043')
        ON CONFLICT (version) DO NOTHING;
    ELSIF ledger_columns @> ARRAY['id', 'name']::TEXT[]
          AND NOT ledger_columns @> ARRAY['version']::TEXT[] THEN
        INSERT INTO schema_migrations (id, name)
        VALUES (43, 'n_plus_one_foundation')
        ON CONFLICT (id) DO NOTHING;
    ELSE
        RAISE EXCEPTION 'Migration 043 blocked: unsupported schema_migrations layout: %', ledger_columns;
    END IF;
END
$migration_ledger$;

COMMIT;
