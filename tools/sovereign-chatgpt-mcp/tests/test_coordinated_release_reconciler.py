from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "deploy/reconcile-main-release.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("coordinated_release_reconciler", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_gate_accepts_only_exact_successful_revision(monkeypatch) -> None:
    module = _load()
    revision = "a" * 40
    monkeypatch.setattr(
        module,
        "_github_json",
        lambda _path: {
            "workflow_runs": [
                {
                    "id": 10,
                    "run_attempt": 1,
                    "head_sha": "b" * 40,
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "id": 11,
                    "run_attempt": 1,
                    "head_sha": revision,
                    "status": "completed",
                    "conclusion": "failure",
                },
                {
                    "id": 12,
                    "run_attempt": 2,
                    "head_sha": revision,
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "https://github.test/run/12",
                },
            ]
        },
    )

    result = module._release_gate(revision)

    assert result["ready"] is True
    assert result["status"] == "RELEASE_GATE_VERIFIED"
    assert result["runId"] == 12
    assert result["headSha"] == revision


def test_waiting_release_gate_performs_no_image_or_runtime_mutation(monkeypatch, tmp_path) -> None:
    module = _load()
    revision = "c" * 40
    monkeypatch.setattr(module, "STATE_DIR", tmp_path)
    monkeypatch.setattr(module, "STATUS_FILE", tmp_path / "status.json")
    module.EXPECTED_REVISION = revision
    module.EXPECTED_RELEASE_GATE_RUN_ID = "77"
    module.EXPECTED_BACKEND_DIGEST = "sha256:" + "a" * 64
    module.EXPECTED_MCP_DIGEST = "sha256:" + "b" * 64
    module.EXPECTED_MANIFEST_EVIDENCE_SHA256 = "c" * 64
    monkeypatch.setattr(module, "_main_revision", lambda: revision)
    monkeypatch.setattr(
        module,
        "_release_gate",
        lambda _revision: {"ready": False, "status": "WAITING_FOR_RELEASE_GATE", "runId": 77},
    )
    monkeypatch.setattr(
        module,
        "_image_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("image pull must not start")),
    )

    result = module.reconcile()

    assert result["status"] == "WAITING_FOR_RELEASE_GATE"
    assert result["mutationPerformed"] is False
    assert json.loads((tmp_path / "status.json").read_text("utf-8"))["revision"] == revision


def test_candidate_failure_is_not_a_global_series_rollback_contract() -> None:
    source = (ROOT / "github_admin.py").read_text("utf-8")
    assert "PR_SERIES_COMPLETED_WITH_SKIPS" in source
    assert '"candidate_failures_are_quarantined": True' in source
    assert '"already_merged_prs_are_never_rolled_back": True' in source
    assert "PR_SERIES_HALTED_SYSTEMIC" in source
    assert "MAX_PR_SERIES = 500" in source


def test_workflows_and_installer_bind_coordinated_release_contract() -> None:
    coordinated = (REPOSITORY_ROOT / ".github/workflows/sovereign-coordinated-release.yml").read_text("utf-8")
    mcp_workflow = (REPOSITORY_ROOT / ".github/workflows/sovereign-chatgpt-mcp.yml").read_text("utf-8")
    installer = (ROOT / "deploy/install-on-vps.sh").read_text("utf-8")
    service = (ROOT / "deploy/sovereign-release-reconciler.service").read_text("utf-8")
    timer = (ROOT / "deploy/sovereign-release-reconciler.timer").read_text("utf-8")

    assert "sovereign-backend-image.yml" in coordinated
    assert "sovereign-chatgpt-mcp.yml" in coordinated
    assert "head_sha: expected" in coordinated
    assert "EXACT_REVISION_IMAGE_WORKFLOWS_VERIFIED" in coordinated
    assert "org.opencontainers.image.revision" in coordinated
    push_prefix = mcp_workflow.split("workflow_dispatch:", 1)[0]
    assert "paths:" not in push_prefix
    assert 'remove_value "$ENV_FILE" GITHUB_TOKEN' in installer
    assert 'remove_value "$MANAGED_ENV" GITHUB_TOKEN' in installer
    assert "printf 'GITHUB_TOKEN=%s\\n' \"$EFFECTIVE_GITHUB_TOKEN\"" not in installer
    assert 'SOVEREIGN_MCP_EXPECTED_DIGEST' in installer
    assert 'MCP image digest differs from CI-bound expected digest' in installer
    assert 'SOVEREIGN_MCP_ENABLE_MAIN_PUSH \\' in installer
    assert 'SOVEREIGN_MCP_ENABLE_PR_MERGE \\' in installer
    assert 'SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL \\' in installer
    assert 'set_value "$MANAGED_ENV" "$TOKEN_DEPENDENT_CAPABILITY" "0"' in installer
    assert '"self_update_available":false' in installer
    assert '"pr_lifecycle_available":false' in installer
    assert '"workflow_dispatch_available":false' in installer
    assert 'install_ci_runtime_readback_authorization' in installer
    assert "systemctl enable --now sovereign-release-reconciler.timer" in installer
    assert "ExecStart=/opt/sovereign-chatgpt-tools/bin/reconcile-main-release" in service
    assert "OnUnitActiveSec=2min" in timer
    reconciler = SCRIPT.read_text("utf-8")
    assert "_schedule_self_update" not in reconciler
    assert "def _deploy_mcp_from_ci_scope" in reconciler
    assert '"SOVEREIGN_MCP_EXPECTED_DIGEST": mcp["digest"]' in reconciler
    assert "def _refresh_operator_source" in reconciler
    assert '"git", "-C", str(OPERATOR_SOURCE), "fetch", "--no-tags", "origin", "main"' in reconciler
    assert '"git", "-C", str(OPERATOR_SOURCE), "checkout", "--detach", scope["revision"]' in reconciler
    assert "origin/main differs from CI scope revision" in reconciler
    assert "checked-out source revision differs from CI scope" in reconciler
    assert "installer source revision is not CI-scoped" in reconciler
    assert "installer receipt violates CI scope or capability truth" in reconciler
    assert 'receipt.get("host_command_worker_active") is not True' in reconciler
    assert 'receipt.get("broker") != "active"' in reconciler
    assert 'receipt.get("broker_rpc_ready") is not True' in reconciler
    assert 'receipt.get("broker_socket_host_visible") is not True' in reconciler
    assert 'receipt.get("broker_socket_container_visible") is not True' in reconciler
    assert 'receipt.get("mcp_protocol_ready") is not True' in reconciler
