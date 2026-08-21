from __future__ import annotations

from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
BYTEBASE_COMPOSE = ROOT / "templates" / "sovereign-bytebase" / "docker-compose.yml"
METAMCP_COMPOSE = ROOT / "templates" / "sovereign-metamcp" / "docker-compose.yml"
INSTALLER = ROOT / "deploy" / "install-bytebase-metamcp.sh"


def _compose(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text("utf-8"))
    assert isinstance(payload, dict)
    assert isinstance(payload.get("services"), dict)
    return payload


def test_external_control_plane_installer_has_valid_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(INSTALLER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_bytebase_template_is_loopback_only_and_digest_bound() -> None:
    payload = _compose(BYTEBASE_COMPOSE)
    service = payload["services"]["bytebase"]
    text = BYTEBASE_COMPOSE.read_text("utf-8")

    assert service["container_name"] == "sovereign-bytebase"
    assert service["ports"] == ["127.0.0.1:32831:8080"]
    assert "sovereign-bytebase-data:/var/opt/bytebase" in service["volumes"]
    assert "SOVEREIGN_BYTEBASE_IMAGE" in service["image"]
    assert "immutable digest reference" in service["image"]
    assert service.get("privileged") is False
    assert "/var/run/docker.sock" not in text
    assert "/run/docker.sock" not in text


def test_metamcp_template_keeps_database_private_and_host_docker_unreachable() -> None:
    payload = _compose(METAMCP_COMPOSE)
    app = payload["services"]["metamcp"]
    postgres = payload["services"]["postgres"]
    text = METAMCP_COMPOSE.read_text("utf-8")

    assert app["container_name"] == "sovereign-metamcp"
    assert app["ports"] == ["127.0.0.1:32832:12008"]
    assert "SOVEREIGN_METAMCP_IMAGE" in app["image"]
    assert "SOVEREIGN_METAMCP_POSTGRES_IMAGE" in postgres["image"]
    assert app.get("privileged") is False
    assert postgres.get("privileged") is False
    assert "ports" not in postgres
    assert payload["networks"]["metamcp-internal"]["internal"] is True
    assert "/var/run/docker.sock" not in text
    assert "/run/docker.sock" not in text
    assert "docker-socket: forbidden" in text


def test_installer_resolves_source_tags_to_immutable_repo_digests_before_deploy() -> None:
    text = INSTALLER.read_text("utf-8")

    assert "resolve_immutable_image" in text
    assert "docker image inspect" in text
    assert ".RepoDigests" in text
    assert "@sha256:[0-9a-f]{64}" in text
    assert 'set_env_value "$BYTEBASE_ENV" SOVEREIGN_BYTEBASE_IMAGE "$BYTEBASE_IMAGE"' in text
    assert 'set_env_value "$METAMCP_ENV" SOVEREIGN_METAMCP_IMAGE "$METAMCP_IMAGE"' in text
    assert 'set_env_value "$METAMCP_ENV" SOVEREIGN_METAMCP_POSTGRES_IMAGE "$METAMCP_POSTGRES_IMAGE"' in text
    assert 'SOVEREIGN_EXTERNAL_STACK_FORCE_IMAGE_RERESOLVE' in text


def test_installer_generates_private_secrets_and_secrets_free_runtime_receipt() -> None:
    text = INSTALLER.read_text("utf-8")

    assert "openssl rand -hex 32" in text
    assert 'chmod 0600 "$BYTEBASE_ENV" "$METAMCP_ENV"' in text
    assert "METAMCP_POSTGRES_PASSWORD" in text
    assert "METAMCP_BETTER_AUTH_SECRET" in text
    assert '"secretsIncluded": False' in text
    assert '"receiptSha256"' in text
    assert '"repositoryRevision"' in text
    assert '"dockerSocketDelegatedToMetaMCP": False' in text


def test_external_stacks_share_only_the_existing_private_sovereign_network() -> None:
    bytebase = _compose(BYTEBASE_COMPOSE)
    metamcp = _compose(METAMCP_COMPOSE)

    assert bytebase["networks"]["supabase_default"]["external"] is True
    assert metamcp["networks"]["supabase_default"]["external"] is True
    assert set(bytebase["services"]["bytebase"]["networks"]) == {"supabase_default"}
    assert set(metamcp["services"]["metamcp"]["networks"]) == {
        "metamcp-internal",
        "supabase_default",
    }
    assert set(metamcp["services"]["postgres"]["networks"]) == {"metamcp-internal"}
