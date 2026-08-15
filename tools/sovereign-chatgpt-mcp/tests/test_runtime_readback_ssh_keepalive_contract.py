from __future__ import annotations

from pathlib import Path


MCP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MCP_ROOT.parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "sovereign-coordinated-release.yml"


def test_independent_runtime_readback_ssh_uses_keepalive_without_weakening_host_identity() -> None:
    workflow = WORKFLOW.read_text("utf-8")
    step = workflow.split(
        "- name: Verify pinned VPS host and invoke forced runtime readback entrypoint",
        1,
    )[1].split(
        "- name: Verify signed independent runtime receipt against manifest",
        1,
    )[0]

    assert "-o ServerAliveInterval=15" in step
    assert "-o ServerAliveCountMax=40" in step
    assert "-o TCPKeepAlive=yes" in step
    assert "-o ConnectTimeout=30" in step
    assert "-o BatchMode=yes" in step
    assert "-o ClearAllForwardings=yes" in step
    assert "-o StrictHostKeyChecking=yes" in step
    assert "-o UserKnownHostsFile=\"$ssh_dir/known_hosts\"" in step
    assert "-o GlobalKnownHostsFile=/dev/null" in step
    assert "-o HostKeyAlgorithms=ssh-ed25519" in step
    assert "-o IdentitiesOnly=yes" in step
    assert "SHA256:pskBohJoTx/V3iCPaD9m1sW1vchvhvGc89lKnX0RocQ" in step
    assert "StrictHostKeyChecking=no" not in step
    assert "UserKnownHostsFile=/dev/null" not in step
    assert "> .sovereign-evidence/independent-target-runtime-receipt.json" in step


def test_runtime_readback_keepalive_does_not_change_release_identity_contract() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "EXPECTED_REVISION: ${{ github.sha }}" in workflow
    assert "runtimePromotionRequiresIndependentReceipt" in workflow
    assert "Verify signed independent runtime receipt against manifest" in workflow
    assert "Publish verified production deployment verdict" in workflow
