from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_migration_is_metadata_only_and_has_bounded_lifecycle() -> None:
    migration = (ROOT / "migrations" / "017_owner_input_requests.sql").read_text("utf-8")

    assert "CREATE TABLE IF NOT EXISTS owner_input_requests" in migration
    assert "status IN ('pending', 'processing', 'denied', 'consumed', 'failed', 'expired')" in migration
    assert "expires_at > requested_at" in migration
    assert "char_length(owner_comment) <= 1000" in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_owner_input_requests_open_target" in migration
    assert "WHERE status IN ('pending', 'processing')" in migration
    assert "Protected values are accepted only by the owner endpoint and are never persisted here" in migration
    lowered = migration.lower()
    assert "protected_value" not in lowered
    assert "secret_value" not in lowered
    assert "credential_value" not in lowered


def test_backend_registers_owner_routes_and_prefers_owner_managed_openhands_path() -> None:
    app = (ROOT / "app.py").read_text("utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")

    assert "from owner_input_runtime import register_owner_input_routes" in app
    assert "register_owner_input_routes(" in app
    assert '"/opt/secure/owner-managed/openhands_api_key.txt"' in app
    assert app.index('"/opt/secure/owner-managed/openhands_api_key.txt"') < app.index('"/opt/secure/openhands_api_key.txt"')
    assert "COPY owner_input_runtime.py ." in dockerfile
    owner_runtime = (ROOT / "owner_input_runtime.py").read_text("utf-8")
    assert "ON CONFLICT (target_id) WHERE status IN ('pending','processing') DO NOTHING" in owner_runtime
    assert "content_length > int(target[\"maxBytes\"])" in owner_runtime


def test_backend_deploy_keeps_global_secure_mount_read_only_and_only_owner_subdir_writable() -> None:
    deploy = (ROOT.parent.parent / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "deploy-sovereign-backend").read_text("utf-8")

    assert 'install -d -m 0700 "$OWNER_INPUT_HOST_ROOT"' in deploy
    assert deploy.count("--volume /opt/secure:/opt/secure:ro") == 2
    assert deploy.count('--volume "$OWNER_INPUT_HOST_ROOT:$OWNER_INPUT_CONTAINER_ROOT:rw"') == 2
    assert "--volume /opt/secure:/opt/secure:rw" not in deploy
