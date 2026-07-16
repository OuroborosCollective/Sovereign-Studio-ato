-- Align historical user_skills tables with the runtime contract used by app.py.
BEGIN;

CREATE TABLE IF NOT EXISTS user_skills (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL,
    name           TEXT NOT NULL DEFAULT '',
    slug           TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    source_repo    TEXT NOT NULL DEFAULT '',
    source_path    TEXT NOT NULL DEFAULT '',
    framework      TEXT NOT NULL DEFAULT 'generic',
    adapted_prompt TEXT NOT NULL DEFAULT '',
    source_sha     TEXT NOT NULL DEFAULT '',
    content_sha256 TEXT NOT NULL DEFAULT '',
    is_active      BOOLEAN NOT NULL DEFAULT true,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    skill_id       TEXT,
    level          INTEGER DEFAULT 1
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = 'admin_users'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'user_skills'::regclass
          AND conname = 'user_skills_user_id_fkey'
    ) THEN
        ALTER TABLE user_skills
            ADD CONSTRAINT user_skills_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE user_skills
    ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS slug TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS source_repo TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS source_path TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS framework TEXT NOT NULL DEFAULT 'generic',
    ADD COLUMN IF NOT EXISTS adapted_prompt TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS source_sha TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS content_sha256 TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'user_skills'
          AND column_name = 'skill_id'
    ) THEN
        ALTER TABLE user_skills ALTER COLUMN skill_id DROP NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_user_skills_user_id ON user_skills(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_skills_user_slug
    ON user_skills(user_id, slug)
    WHERE btrim(slug) <> '';

COMMIT;
