import hashlib
import importlib.util
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
SELF_UPDATE_SERVICE = ROOT / "sovereign-chatgpt-mcp" / "deploy" / "sovereign-chatgpt-mcp-self-update.service"


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
    assert 'UV_CACHE_DIR="$TEMP/uv-cache"' in installer
    assert 'install -d -m 0700 -o root -g root "$UV_CACHE_DIR"' in installer
    assert 'env -u UV_FROZEN -u UV_LOCKED UV_CACHE_DIR="$UV_CACHE_DIR" uv sync --locked --no-dev --no-install-project' in installer
    assert 'rm -rf "$UV_CACHE_DIR"' in installer
    assert "SOVEREIGN_TOOLCHAIN_UV_DIAGNOSTIC" in installer
    assert "CLI_COMPATIBILITY" in installer
    assert "LOCK_DRIFT" in installer
    assert "STORAGE" in installer
    assert "PERMISSION" in installer
    assert "BUILD_SYSTEM" in installer
    assert "CACHE_IO" in installer
    assert "RESOLUTION" in installer
    assert "PYTHON" in installer
    assert "NETWORK" in installer
    assert "bounded_uv_version" in installer
    assert "UV_OUTPUT_SHA256" in installer
    assert "uv lock --check" not in installer
    assert "uv sync --frozen" not in installer
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
    assert 'ROLLBACK_PREPARE_LOG="$(mktemp)"' in installer
    assert "SOVEREIGN_TOOLCHAIN_ROLLBACK_FAILURE operation=prepare reason_sha256=" in installer
    assert 'rollback prepare failed: $ROLLBACK_PREPARE_DIAGNOSTIC output_sha256=$ROLLBACK_PREPARE_OUTPUT_SHA256' in installer
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
    assert "SOVEREIGN_TOOLCHAIN_AUTH_CANARY_DIAGNOSTIC" in installer
    assert '"status": "AUTHENTICATED_BOUNDARY_CANARY_FAILED"' in installer
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


def test_activation_rebinds_unit_sources_after_staged_tree_move() -> None:
    installer = INSTALLER.read_text("utf-8")
    activation = installer.split("MUTATION_STARTED=1", 1)[1].split("STAGE=runtime", 1)[0]

    tree_move = 'mv "$TEMP/sovereign-toolchain" "$TARGET"'
    full_rebind = 'UNIT_SOURCE="$TARGET/deploy/sovereign-toolchain.service"'
    evidence_rebind = (
        'EVIDENCE_UNIT_SOURCE="$TARGET/deploy/'
        'sovereign-toolchain-n8n-evidence.service"'
    )
    full_install = 'atomic_install 0644 "$UNIT_SOURCE" "$UNIT_TARGET"'
    evidence_install = (
        'atomic_install 0644 "$EVIDENCE_UNIT_SOURCE" "$EVIDENCE_UNIT_TARGET"'
    )

    assert activation.count(full_rebind) == 1
    assert activation.count(evidence_rebind) == 1
    assert activation.index(tree_move) < activation.index(full_rebind) < activation.index(full_install)
    assert activation.index(tree_move) < activation.index(evidence_rebind) < activation.index(evidence_install)


def test_authenticated_boundary_canary_emits_bounded_phase_evidence() -> None:
    installer = INSTALLER.read_text("utf-8")
    canary = installer.split('AUTH_CANARY_LOG="$TEMP/authenticated-boundary-canary.log"', 1)[1].split(
        'PID="$(systemctl show --property MainPID', 1
    )[0]

    assert "sys.excepthook = _safe_canary_exception_hook" in canary
    assert 'file=sys.stderr' in canary
    assert '"status": "AUTHENTICATED_BOUNDARY_CANARY_FAILED"' in canary
    assert "SOVEREIGN_TOOLCHAIN_AUTH_CANARY_DIAGNOSTIC %s output_sha256=%s" in canary
    assert "phase_pattern.fullmatch(phase)" in canary
    assert "error_pattern.fullmatch(error_type)" in canary
    assert "phase=unclassified;error=UnknownError" in canary
    assert 'AUTH_CANARY_LOG="$(mktemp)"' not in installer
    assert 'AUTH_CANARY_LOG="$TEMP/authenticated-boundary-canary.log"' in installer
    assert 'trap cleanup_stage EXIT' in installer
    assert 'python3 - "$AUTH_CANARY_LOG" 2>/dev/null' in canary
    assert 'Path(sys.argv[1]).read_text("utf-8")' in canary
    assert '<<\'PY\' < "$AUTH_CANARY_LOG"' not in canary
    for phase in (
        "protected_credentials",
        "full_rest_auth",
        "full_mcp_auth",
        "evidence_auth_boundaries",
        "evidence_payload_limits",
        "evidence_lane_policy",
        "sovereign_live_evidence",
        "aurion_live_evidence",
    ):
        assert phase in canary
    assert "str(_error)" not in canary
    assert "repr(_error)" not in canary
    assert "traceback.print" not in canary


def test_uv_sync_uses_private_staging_cache_under_protect_home() -> None:
    installer = INSTALLER.read_text("utf-8")
    self_update_service = SELF_UPDATE_SERVICE.read_text("utf-8")

    assert "User=root" in self_update_service
    assert "ProtectHome=true" in self_update_service
    assert 'UV_CACHE_DIR="$TEMP/uv-cache"' in installer
    assert 'UV_CACHE_DIR="$UV_CACHE_DIR" uv sync' in installer
    assert "UV_CACHE_DIR=$HOME" not in installer
    assert "UV_CACHE_DIR=/root" not in installer


def test_uv_sync_failure_classifier_is_bounded_and_causal(tmp_path: Path) -> None:
    installer = INSTALLER.read_text("utf-8")
    function_body = installer.split("classify_uv_sync_failure() {", 1)[1].split(
        "\nbounded_uv_version()", 1
    )[0]
    function_source = "classify_uv_sync_failure() {" + function_body
    cases = {
        "CLI_COMPATIBILITY": "error: unexpected argument '--no-install-project' found",
        "LOCK_DRIFT": "uv.lock needs to be updated, but --locked was provided",
        "STORAGE": "failed to write cache: No space left on device",
        "PERMISSION": "failed to create virtual environment: Permission denied",
        "BUILD_SYSTEM": "Failed to build wheel using the build backend hatchling",
        "CACHE_IO": "cache entry corrupt: checksum mismatch",
        "RESOLUTION": "No solution found when resolving dependencies",
        "PYTHON": "Python not found for the requested environment",
        "NETWORK": "failed to fetch package: connection reset by peer",
        "OTHER": "resolver exited for an unclassified bounded reason",
    }
    for expected, evidence in cases.items():
        log = tmp_path / f"{expected.lower()}.log"
        log.write_text(evidence + "\n", encoding="utf-8")
        completed = subprocess.run(
            [
                "bash",
                "-c",
                function_source + '\nclassify_uv_sync_failure "$1"',
                "bash",
                str(log),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert completed.stderr == ""
        assert completed.stdout.strip() == expected


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
    assert "verify_service_activation_states" in helper
    assert "verify_service_states" in helper
    assert "verify_socket_boundary" in helper
    prepare = helper.split("def prepare", 1)[1].split("def restore_file", 1)[0]
    restore = helper.split("def restore(payload", 1)[1].split("def commit(payload", 1)[0]
    commit = helper.split("def commit(payload", 1)[1].split("def main", 1)[0]
    assert "verify_service_activation_states(services)" in prepare
    assert "verify_service_states(services)" not in prepare
    assert 'verify_service_activation_states(payload["services"])' in restore
    assert 'verify_service_states(payload["services"])' not in restore
    assert "verify_service_states(desired)" in commit
    assert prepare.index("atomic_json_write(") < prepare.index("retire_superseded_snapshots(read_manifest())")
    assert '"state": "pending"' in helper
    assert 'payload["state"] = "committed"' in helper
    assert 'payload["state"] = "rolled_back"' in helper
    assert "rollback expected revision mismatch" in helper
    assert "rollbackVerified" in helper
    assert '"socketBoundaryReadback": arguments.operation == "commit"' in helper
    assert '"predecessorBoundaryPreserved": arguments.operation == "rollback"' in helper
    assert "except: pass" not in helper


def load_rollback_helper():
    spec = importlib.util.spec_from_file_location("sovereign_rollback_helper", ROLLBACK_HELPER)
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def test_prepare_accepts_legacy_predecessor_without_revision_marker(tmp_path: Path) -> None:
    helper = load_rollback_helper()
    root = tmp_path / "legacy-root"
    backup_root = root / ".installer-backups"
    toolchain = root / "sovereign-toolchain"
    common = root / "sovereign-legacy-mcp-common"
    backup_root.mkdir(parents=True)
    toolchain.mkdir()
    common.mkdir()

    helper.BACKUP_ROOT = backup_root
    helper.MANIFEST_PATH = backup_root / "last-install.json"
    helper.DIRECTORIES = (
        (toolchain, "sovereign-toolchain"),
        (common, "sovereign-legacy-mcp-common"),
    )
    helper.FILES = ()
    helper.SERVICES = ()
    captured = {}
    helper.atomic_json_write = lambda payload: captured.update(payload)
    helper.read_manifest = lambda: dict(captured)
    helper.retire_superseded_snapshots = lambda _payload: None

    helper.prepare("a" * 40, "20260903T200000Z.123")

    assert captured["previousRevision"] is None
    assert captured["directories"][0]["previousPresent"] is True
    assert not (toolchain / helper.REVISION_MARKER).exists()
    helper.verify_restored_snapshots(captured)

    (toolchain / helper.REVISION_MARKER).write_text("b" * 40, encoding="ascii")
    try:
        helper.verify_restored_snapshots(captured)
    except helper.RollbackError as exc:
        assert str(exc) == "restored legacy revision marker state changed"
    else:
        raise AssertionError("legacy predecessor marker drift was not rejected")


def test_prepare_rejects_invalid_existing_revision_marker(tmp_path: Path) -> None:
    helper = load_rollback_helper()
    root = tmp_path / "legacy-root"
    backup_root = root / ".installer-backups"
    toolchain = root / "sovereign-toolchain"
    common = root / "sovereign-legacy-mcp-common"
    backup_root.mkdir(parents=True)
    toolchain.mkdir()
    common.mkdir()
    (toolchain / helper.REVISION_MARKER).write_text("not-a-revision", encoding="ascii")

    helper.BACKUP_ROOT = backup_root
    helper.MANIFEST_PATH = backup_root / "last-install.json"
    helper.DIRECTORIES = (
        (toolchain, "sovereign-toolchain"),
        (common, "sovereign-legacy-mcp-common"),
    )
    helper.FILES = ()
    helper.SERVICES = ()

    try:
        helper.prepare("a" * 40, "20260903T200001Z.124")
    except helper.RollbackError as exc:
        assert str(exc) == "previous revision marker is invalid"
    else:
        raise AssertionError("invalid predecessor revision marker was accepted")


def test_snapshot_retirement_is_bounded_and_preserves_the_current_generation(tmp_path: Path) -> None:
    helper = load_rollback_helper()
    helper.BACKUP_ROOT = tmp_path
    helper.DIRECTORIES = ((tmp_path / "toolchain", "toolchain"),)
    helper.FILES = ((tmp_path / "runtime.env", "runtime.env", 0o600),)

    current = "20260901T120000Z.101"
    stale = "20260831T120000Z.99"
    stale_link_stamp = "20260830T120000Z.98"
    current_tree = tmp_path / f"toolchain.{current}"
    current_tree.mkdir()
    current_file = tmp_path / f"runtime.env.{current}"
    current_file.write_text("current", encoding="utf-8")
    current_quarantine = tmp_path / f"failed-toolchain.{current}"
    current_quarantine.mkdir()

    stale_tree = tmp_path / f"toolchain.{stale}"
    stale_tree.mkdir()
    (stale_tree / "large-runtime").write_text("stale", encoding="utf-8")
    stale_file = tmp_path / f"runtime.env.{stale}"
    stale_file.write_text("stale", encoding="utf-8")
    stale_quarantine = tmp_path / f"failed-toolchain.{stale}"
    stale_quarantine.mkdir()
    unmanaged = tmp_path / "operator-note"
    unmanaged.write_text("keep", encoding="utf-8")
    stale_link = tmp_path / f"runtime.env.{stale_link_stamp}"
    stale_link.symlink_to(unmanaged)

    helper.retire_superseded_snapshots(
        {
            "stamp": current,
            "directories": [
                {"target": str(tmp_path / "toolchain"), "backup": str(current_tree)}
            ],
            "files": [
                {"target": str(tmp_path / "runtime.env"), "backup": str(current_file)}
            ],
        }
    )

    assert current_tree.is_dir()
    assert current_file.is_file()
    assert current_quarantine.is_dir()
    assert not stale_tree.exists()
    assert not stale_file.exists()
    assert not stale_quarantine.exists()
    assert not stale_link.exists()
    assert unmanaged.read_text("utf-8") == "keep"


def test_predecessor_activation_readback_does_not_apply_the_new_listener_policy() -> None:
    helper = load_rollback_helper()
    services = [
        {"name": helper.SERVICES[0], "active": True, "enabled": True},
        {"name": helper.SERVICES[1], "active": False, "enabled": False},
    ]
    helper.is_active = lambda service: service == helper.SERVICES[0]
    helper.is_enabled = lambda service: service == helper.SERVICES[0]
    boundary_calls = []
    helper.verify_effective_units = lambda *states: boundary_calls.append(("unit", states))
    helper.verify_socket_boundary = lambda *states: boundary_calls.append(("socket", states))

    helper.verify_service_activation_states(services)
    assert boundary_calls == []

    helper.verify_service_states(services)
    assert boundary_calls == [
        ("unit", (True, False)),
        ("socket", (True, False)),
    ]


def test_installer_is_valid_bash() -> None:
    result = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
    helper = subprocess.run(
        ["python3", "-m", "py_compile", str(ROLLBACK_HELPER)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert helper.returncode == 0, helper.stderr


def test_pre_activation_unhandled_error_emits_only_bounded_hashed_diagnostic(tmp_path: Path) -> None:
    installer = INSTALLER.read_text("utf-8")
    assert 'trap \'on_unhandled_error "$LINENO"\' ERR' in installer
    assert installer.index('trap \'on_unhandled_error "$LINENO"\' ERR') < installer.index("STAGE=preflight")
    assert installer.index("MUTATION_STARTED=1") < installer.index("trap on_activation_error ERR")

    marker = "STAGE=preflight\n"
    injected = installer.replace(marker, marker + "false\n", 1)
    injected_path = tmp_path / "install-on-vps.sh"
    injected_path.write_text(injected, encoding="utf-8")

    false_line = injected.splitlines().index("false") + 1
    expected_reason = hashlib.sha256(
        f"unhandled command failure line={false_line}".encode("utf-8")
    ).hexdigest()
    completed = subprocess.run(
        ["bash", str(injected_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.splitlines() == [
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE "
        f"stage=preflight reason_sha256={expected_reason} rollback=not-required"
    ]
    assert "unhandled command failure" not in completed.stderr


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
