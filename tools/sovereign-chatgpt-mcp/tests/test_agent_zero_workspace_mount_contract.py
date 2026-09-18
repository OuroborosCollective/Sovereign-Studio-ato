from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "reconcile-agent-zero-workspace-mount.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "agent-zero-shared-workspace-mount.yml"


def test_agent_zero_workspace_mount_script_is_shell_valid_and_fail_closed() -> None:
    source = SCRIPT.read_text("utf-8")
    parsed = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)

    assert parsed.returncode == 0, parsed.stderr
    assert 'HOST_WORKSPACE_ROOT="/opt/sovereign-agent-workspaces"' in source
    assert 'BACKEND_WORKSPACE_ROOT="/var/lib/sovereign-agent/workspaces"' in source
    assert 'AGENT_ZERO_WORKSPACE_ROOT="/a0/sovereign-workspaces"' in source
    assert 'AGENT_ZERO_CONTAINER="agent-zero-xrev-agent-zero-1"' in source
    assert 'mount_present "$BACKEND_CONTAINER"' in source
    assert 'mount_present "$AGENT_ZERO_CONTAINER"' in source
    assert "backend_canary_readback_failed" in source
    assert "agent_zero_canary_readback_failed" in source
    assert "agent_zero_canary_cleanup_unverified" in source
    assert "docker compose -p" in source
    assert "up -d --no-deps" in source
    assert "/var/run/docker.sock" not in source


def test_mount_workflow_uses_pinned_target_identity_and_dispatches_five_path_only_after_receipt() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in workflow
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "SOVEREIGN_RUNTIME_READBACK_SSH_PRIVATE_KEY" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "HostKeyAlgorithms=ssh-ed25519" in workflow
    assert "SHA256:pskBohJoTx/V3iCPaD9m1sW1vchvhvGc89lKnX0RocQ" in workflow
    assert "AGENT_ZERO_SHARED_WORKSPACE_MOUNT_VERIFIED" in workflow
    assert "secretValuesReturned" in workflow
    assert "gh workflow run e2e-testing.yml --ref main -f live_five_path=true" in workflow
    assert workflow.index("AGENT_ZERO_SHARED_WORKSPACE_MOUNT_VERIFIED") < workflow.index(
        "gh workflow run e2e-testing.yml --ref main -f live_five_path=true"
    )
