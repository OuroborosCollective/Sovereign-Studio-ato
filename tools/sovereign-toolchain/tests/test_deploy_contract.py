import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIT = ROOT / "sovereign-toolchain" / "deploy" / "sovereign-toolchain.service"
EVIDENCE_UNIT = ROOT / "sovereign-toolchain" / "deploy" / "sovereign-toolchain-n8n-evidence.service"
INSTALLER = ROOT / "sovereign-toolchain" / "deploy" / "install-on-vps.sh"
ROLLBACK_HELPER = ROOT / "sovereign-toolchain" / "deploy" / "rollback-last-install.py"
APP = ROOT / "sovereign-toolchain" / "src" / "sovereign_toolchain" / "app.py"
METADATA_READER = ROOT / "sovereign-toolchain" / "deploy" / "read-broker-github-app-metadata.sh"
WORKFLOW = ROOT.parent / ".github" / "workflows" / "sovereign-toolchain.yml"


def test_units_split_loopback_full_app_from_minimal_evidence_listener() -> None:
    unit = UNIT.read_text("utf-8")
    evidence_unit = EVIDENCE_UNIT.read_text("utf-8")

    assert "LoadCredential=github-app-private-key.pem:/opt/secure/sovereign-github-app/private-key.pem" in unit
    assert "EnvironmentFile=/etc/sovereign-toolchain/runtime.env" in unit
    assert "sovereign_toolchain.app:app --host 127.0.0.1 --port 8001" in unit
    assert "--host 0.0.0.0" not in unit
    assert "n8n-evidence-master.key" not in unit

    assert "LoadCredential=github-app-private-key.pem:/opt/secure/sovereign-github-app/private-key.pem" in evidence_unit
    assert "LoadCredential=n8n-evidence-master.key:/etc/sovereign-toolchain/n8n-evidence.key" in evidence_unit
    assert "EnvironmentFile=/etc/sovereign-toolchain/evidence-runtime.env" in evidence_unit
    assert "EnvironmentFile=/etc/sovereign-toolchain/runtime.env" not in evidence_unit
    assert "sovereign_toolchain.n8n_evidence_app:app --host 0.0.0.0 --port 8002" in evidence_unit
    assert "sovereign_toolchain.app:app" not in evidence_unit
    assert "DynamicUser=yes" in evidence_unit
    assert "User=root" not in evidence_unit
    assert "ProtectSystem=strict" in evidence_unit
    assert "ReadWritePaths=" not in evidence_unit
    assert "PYTHONDONTWRITEBYTECODE=1" in evidence_unit

    for source in (unit, evidence_unit):
        assert "GITHUB_TOKEN=" not in source
        assert "GH_TOKEN=" not in source
        assert "GITHUB_PAT=" not in source


def test_installer_atomically_deploys_and_verifies_both_boundaries() -> None:
    installer = INSTALLER.read_text("utf-8")

    assert "command -v uv" in installer
    assert "uv lock --check" in installer
    assert "uv sync --frozen --no-dev --no-install-project" in installer
    assert 'git -C "$SOURCE_REPOSITORY_ROOT" archive --format=tar "$EXPECTED_REVISION"' in installer
    assert 'cp -a "$SOURCE_DIR/."' not in installer
    assert 'cp -a "$COMMON_SOURCE/."' not in installer
    assert "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE" in installer
    assert "persistent GitHub token inherited by service" in installer
    assert "runtime environment has persistent GitHub token" in installer
    assert "openssl rand -hex 32" in installer
    assert "existing toolchain API key cardinality invalid" in installer
    assert "existing n8n evidence key cardinality invalid" in installer
    assert "n8n evidence key sources disagree" in installer

    assert 'ROLLBACK_HELPER="$BACKUP_ROOT/rollback-last-install.py"' in installer
    assert 'python3 "$ROLLBACK_HELPER" prepare' in installer
    assert 'python3 "$ROLLBACK_HELPER" rollback' in installer
    assert 'python3 "$ROLLBACK_HELPER" commit' in installer
    assert 'trap \'on_activation_signal HUP\' HUP' in installer
    assert 'trap \'on_activation_signal INT\' INT' in installer
    assert 'trap \'on_activation_signal TERM\' TERM' in installer
    assert installer.index("MUTATION_STARTED=1") < installer.index('mv "$TARGET" "$TARGET_BACKUP"')
    assert '"rollbackCapable":true' in installer
    assert '"rollbackManifestCommitted":true' in installer

    assert 'atomic_install 0600 "$TEMP/runtime.env" "$ENV_TARGET"' in installer
    assert 'atomic_install 0600 "$TEMP/evidence-runtime.env" "$EVIDENCE_ENV_TARGET"' in installer
    assert 'atomic_install 0600 "$TEMP/n8n-evidence.key" "$N8N_EVIDENCE_KEY_TARGET"' in installer
    assert 'cmp -s "$TEMP/runtime.env" "$ENV_TARGET"' in installer
    assert 'cmp -s "$TEMP/evidence-runtime.env" "$EVIDENCE_ENV_TARGET"' in installer
    assert 'cmp -s "$TEMP/n8n-evidence.key" "$N8N_EVIDENCE_KEY_TARGET"' in installer
    assert "toolchain API key crossed into evidence environment" in installer
    assert "toolchain capability leaked into evidence process" in installer
    assert "SOVEREIGN_TOOLCHAIN_GITHUB_READ_ONLY=1" in installer
    assert "read-only token mode crossed into full runtime" in installer

    assert "authenticated boundary canary failed" in installer
    assert "ProxyHandler({})" in installer
    assert "X-Sovereign-Evidence-Capability" in installer
    assert "X-Toolchain-Key" in installer
    assert '"method": "initialize"' in installer
    assert 'full_origin + "/mcp/"' in installer
    assert 'connection.putheader("X-Toolchain-Key", toolchain_key)' in installer
    assert "duplicate_response.status == 401" in installer
    assert "mcp_status == 200" in installer
    assert "rest_status == 200" in installer
    assert "result[\"repository\"] == payload[\"owner\"]" in installer
    assert "result[\"workflowSelector\"] == str(payload[\"workflow_id\"])" in installer
    assert "result[\"branch\"] == payload[\"branch\"]" in installer
    assert "listener socket boundary canary failed" in installer
    assert 'evidence_origin = "http://127.0.0.1:8002"' in installer
    assert 'evidence_url = evidence_origin + "/api/v1/n8n/ci-evidence"' in installer
    assert "sovereign.n8n-ci-evidence-capability.v1" in installer
    assert "n8nEvidenceLaneCapabilities" in installer
    assert "fullMcpAuthCanary" in installer
    assert "ALLOWED_REPOS=%s,%s" in installer
    assert "OuroborosCollective/Sovereign-Studio-ato" in installer
    assert "OuroborosCollective/Echoes_of_Aurion" in installer
    assert "sovereign-coordinated-release.yml" in installer
    assert "340269357" in installer
    assert "ALLOWED_REPOS=*" not in installer

    assert 'systemctl stop "$EVIDENCE_SERVICE" "$SERVICE"' in installer
    assert 'systemctl enable "$SERVICE" "$EVIDENCE_SERVICE"' in installer
    assert 'systemctl restart "$SERVICE"' in installer
    assert 'systemctl restart "$EVIDENCE_SERVICE"' in installer
    assert "evidence DynamicUser readback failed" in installer
    assert "evidence ProtectSystem readback failed" in installer
    assert "evidence service has effective writable paths" in installer
    assert "GitHub App private key owner is invalid" in installer
    assert "GitHub App private key mode is invalid" in installer
    assert ". /opt/sovereign-chatgpt-tools/broker.env" not in installer
    assert "read-broker-github-app-metadata.sh" in installer
    assert "final target runtime executable missing" in installer
    assert "n8n evidence master key leaked into process environment" in installer



def test_rollback_helper_verifies_revision_files_services_and_sockets() -> None:
    helper = ROLLBACK_HELPER.read_text("utf-8")

    assert 'SCHEMA = "sovereign.toolchain.rollback.v1"' in helper
    assert 'MANIFEST_PATH = BACKUP_ROOT / "last-install.json"' in helper
    assert "previousDevice" in helper
    assert "previousInode" in helper
    assert "sha256_file" in helper
    assert "stat.S_ISREG" in helper
    assert "stat.S_IMODE(metadata.st_mode) != 0o600" in helper
    assert '"O_NOFOLLOW"' in helper
    assert "os.replace(backup, target)" in helper
    assert "verify_restored_snapshots" in helper
    assert "verify_service_states" in helper
    assert "verify_socket_boundary" in helper
    assert '"state": "pending"' in helper
    assert 'payload["state"] = "committed"' in helper
    assert 'payload["state"] = "rolled_back"' in helper
    assert "rollback expected revision mismatch" in helper
    assert "rollbackVerified" in helper
    assert "except: pass" not in helper


def test_installer_is_valid_bash() -> None:
    result = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
    helper = subprocess.run(
        ["python3", "-m", "py_compile", str(ROLLBACK_HELPER)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert helper.returncode == 0, helper.stderr


def test_metadata_reader_ignores_unrelated_non_shellsafe_dotenv_line(tmp_path: Path) -> None:
    broker_env = tmp_path / "broker.env"
    broker_env.write_text(
        "SOVEREIGN_MCP_GITHUB_APP_ID=12345\n"
        "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID=67890\n"
        "SOVEREIGN_MCP_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato\n"
        "UNRELATED_NOTE=NOCode command-shaped text\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(METADATA_READER), str(broker_env)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "SOVEREIGN_MCP_GITHUB_APP_ID=12345",
        "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID=67890",
        "SOVEREIGN_MCP_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato",
    ]


def test_metadata_reader_rejects_duplicate_required_literal(tmp_path: Path) -> None:
    broker_env = tmp_path / "broker.env"
    broker_env.write_text(
        "SOVEREIGN_MCP_GITHUB_APP_ID=12345\n"
        "SOVEREIGN_MCP_GITHUB_APP_ID=54321\n"
        "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID=67890\n"
        "SOVEREIGN_MCP_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato\n",
        encoding="utf-8",
    )
    result = subprocess.run(["bash", str(METADATA_READER), str(broker_env)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "cardinality invalid" in result.stderr


def test_ci_is_supplemental_and_exact_head_bound() -> None:
    workflow = WORKFLOW.read_text("utf-8")
    assert "pull_request:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "expected_head_sha:" in workflow
    assert "ref: ${{ inputs.expected_head_sha || github.sha }}" in workflow
    assert "Verify exact dispatch revision" in workflow
    assert "astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4" in workflow
    assert "astral-sh/setup-uv@v4" not in workflow


def test_app_exposes_the_installer_health_contract() -> None:
    app = APP.read_text("utf-8")
    assert "@app.get(\"/\")" in app
    assert '"ok": True' in app
    assert '"name": "Sovereign Universal Toolchain"' in app
