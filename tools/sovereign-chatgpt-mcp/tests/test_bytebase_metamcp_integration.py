from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
BYTEBASE_COMPOSE = ROOT / "templates" / "sovereign-bytebase" / "docker-compose.yml"
METAMCP_COMPOSE = ROOT / "templates" / "sovereign-metamcp" / "docker-compose.yml"
INSTALLER = ROOT / "deploy" / "install-bytebase-metamcp.sh"
BROKER_SERVICE = ROOT / "deploy" / "sovereign-chatgpt-broker.service"
WORKER_SERVICE = ROOT / "deploy" / "sovereign-chatgpt-command-worker.service"
EXTENSION = ROOT / "deploy" / "extensions" / "sovereign_external_control_plane.py"
SITECUSTOMIZE = ROOT / "deploy" / "extensions" / "sitecustomize.py"


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
    assert 'BYTEBASE_ENV="$BYTEBASE_ROOT/.env"' in text
    assert 'METAMCP_ENV="$METAMCP_ROOT/.env"' in text
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
    assert '"managedCompose": json.loads(os.environ["BROKER_PLAN_RECEIPT"])' in text


def test_installer_requires_mcp_sandbox_contract_before_external_mutation() -> None:
    text = INSTALLER.read_text("utf-8")

    assert "require_control_plane_contract" in text
    assert 'Environment=PYTHONPATH=$MCP_EXTENSION_ROOT' in text
    assert 'fail "command worker does not permit the Bytebase deploy root"' in text
    assert 'fail "command worker does not permit the MetaMCP deploy root"' in text
    assert text.index("require_control_plane_contract") < text.index('docker network inspect supabase_default')


def test_installer_materializes_templates_and_mcp_extension_then_reads_broker_back() -> None:
    text = INSTALLER.read_text("utf-8")

    assert 'MCP_TEMPLATE_ROOT="$MCP_ROOT/templates"' in text
    assert 'MCP_EXTENSION_ROOT="$MCP_ROOT/extensions"' in text
    assert 'install -m 0644 "$SOURCE_DIR/deploy/extensions/sitecustomize.py"' in text
    assert 'install -m 0644 "$SOURCE_DIR/deploy/extensions/sovereign_external_control_plane.py"' in text
    assert '"action": "managed_compose_stack_plan"' in text
    assert '"sovereign-bytebase", "sovereign-metamcp"' in text
    assert 'result.get("templateRegistered") is not True' in text
    assert 'systemctl restart "$BROKER_SERVICE" "$WORKER_SERVICE"' in text


def test_external_stacks_share_only_the_expected_sovereign_networks() -> None:
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


def test_host_services_load_extension_and_worker_grants_only_required_new_roots() -> None:
    broker = BROKER_SERVICE.read_text("utf-8")
    worker = WORKER_SERVICE.read_text("utf-8")
    expected = "Environment=PYTHONPATH=/opt/sovereign-chatgpt-tools/extensions"

    assert expected in broker
    assert expected in worker
    assert "/opt/sovereign-bytebase" not in broker.split("ReadWritePaths=", 1)[1].splitlines()[0]
    assert "/opt/sovereign-metamcp" not in broker.split("ReadWritePaths=", 1)[1].splitlines()[0]
    worker_writes = worker.split("ReadWritePaths=", 1)[1].splitlines()[0]
    assert "/opt/sovereign-bytebase" in worker_writes
    assert "/opt/sovereign-metamcp" in worker_writes


def test_external_registry_extension_adds_only_reviewed_stack_ids(monkeypatch) -> None:
    sys.path.insert(0, str(ROOT))
    try:
        import managed_compose

        before = dict(managed_compose.STACKS)
        spec = importlib.util.spec_from_file_location("sovereign_external_control_plane_test", EXTENSION)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        registered = module.install()
        assert registered == ("sovereign-bytebase", "sovereign-metamcp")
        assert set(managed_compose.STACKS) - set(before) == set(registered)
        bytebase = managed_compose.STACKS["sovereign-bytebase"]
        metamcp = managed_compose.STACKS["sovereign-metamcp"]
        assert bytebase.allowed_published_ports == ("127.0.0.1:32831:8080",)
        assert metamcp.allowed_published_ports == ("127.0.0.1:32832:12008",)
        assert metamcp.allowed_services == ("metamcp", "postgres")
    finally:
        sys.path.remove(str(ROOT))
        for key in ("sovereign-bytebase", "sovereign-metamcp"):
            managed_compose.STACKS.pop(key, None)


def test_sitecustomize_is_declarative_registration_only() -> None:
    text = SITECUSTOMIZE.read_text("utf-8")
    assert "from sovereign_external_control_plane import install" in text
    assert "REGISTERED_EXTERNAL_CONTROL_PLANE_STACKS = install()" in text
    assert "subprocess" not in text
    assert "socket" not in text
    assert "docker" not in text.lower()
