from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "bootstrap-database.sh"


def test_database_bootstrap_shell_parses() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_production_reader_grants_are_owner_preflighted_and_transactional() -> None:
    script = SCRIPT.read_text("utf-8")

    assert "foreign_public_object_owners" in script
    assert 'PRODUCTION_FOREIGN_OWNERS="$(foreign_public_object_owners "$ADMIN_DB" "$ADMIN_USER")"' in script
    assert "production public objects are not owned by $ADMIN_USER" in script
    assert 'database_owner_can_manage_public_schema "$ADMIN_DB"' in script
    assert "BEGIN;\nGRANT CONNECT ON DATABASE $ADMIN_DB TO $READER_USER;" in script
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE $ADMIN_USER IN SCHEMA public" in script
    assert "COMMIT;" in script
    assert "production reader object privilege canary failed" in script
    assert '"reader_object_privileges":true' in script


def test_preview_database_does_not_grant_objects_to_their_existing_owner() -> None:
    script = SCRIPT.read_text("utf-8")

    assert 'PREVIEW_FOREIGN_OWNERS="$(foreign_public_object_owners "$PREVIEW_DB" "$PREVIEW_USER")"' in script
    assert "preview public objects are not owned by $PREVIEW_USER" in script
    assert 'database_owner_can_manage_public_schema "$PREVIEW_DB"' in script
    assert "GRANT USAGE, CREATE ON SCHEMA public TO $PREVIEW_USER;" in script
    assert "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $PREVIEW_USER" not in script
    assert "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $PREVIEW_USER" not in script
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES" not in script
    assert "preview database object ownership canary failed" in script
    assert '"preview_owner_canary":true' in script


def test_owner_evidence_is_bounded_to_public_runtime_objects() -> None:
    script = SCRIPT.read_text("utf-8")

    assert "n.nspname = 'public'" in script
    assert "c.relkind IN ('r','p','v','m','S','f')" in script
    assert "string_agg(owner_name, ', ' ORDER BY owner_name)" in script
    assert "ALTER TABLE" not in script
    assert "OWNER TO" not in script


def test_privilege_canary_guards_relation_specific_functions_with_case() -> None:
    script = SCRIPT.read_text("utf-8")

    assert "WHEN c.relkind IN ('r','p','v','m','f')" in script
    assert "THEN NOT has_table_privilege('$READER_USER', c.oid, 'SELECT')" in script
    assert "WHEN c.relkind = 'S'" in script
    assert "THEN NOT has_sequence_privilege('$READER_USER', c.oid, 'SELECT')" in script
    assert script.count("ELSE FALSE") >= 2
    assert "AND c.relkind = 'S'\n           AND NOT has_sequence_privilege" not in script
