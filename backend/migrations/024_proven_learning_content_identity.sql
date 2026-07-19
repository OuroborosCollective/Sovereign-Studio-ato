-- Canonical, idempotent content identity for evidence-proven learning patterns.
BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sovereign_agent_pattern_candidates_proven_content
    ON sovereign_agent_pattern_candidates (user_id, (payload->>'contentHash'))
    WHERE decision = 'accepted'
      AND payload ? 'contentHash';

INSERT INTO schema_migrations (id, name)
VALUES (24, 'proven_learning_content_identity')
ON CONFLICT (id) DO NOTHING;

COMMIT;
