from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.desktop_runtime import (
    DesktopComputerUseRequestV1,
    DesktopInputObservationReceiptV1,
    DesktopWorkerAdmissionV1,
)
from agent_runtime.fleet_supervisor import FleetContractError
from agent_runtime.live_workspace import LiveWorkspaceSessionV1

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
ATTEMPT = "attempt-" + "a" * 24
IMAGE_DIGEST = "sha256:" + "e" * 64
REVISION = "f" * 40


def payload() -> dict:
    return {
        "runtimeIdentityHash": HASH_A,
        "sessionBindingHash": HASH_B,
        "attemptId": ATTEMPT,
        "workspaceId": "job-live-workspace",
        "worktreeIdentityHash": HASH_C,
        "imageDigest": IMAGE_DIGEST,
        "imageReference": "ghcr.io/ouroboroscollective/sovereign-desktop-worker@" + IMAGE_DIGEST,
        "sourceRevision": REVISION,
        "containerId": "1" * 64,
        "privileged": False,
        "dockerSocketMounted": False,
        "hostNamespaces": False,
        "noNewPrivileges": True,
        "capabilitiesDropped": True,
        "readOnlyRootFilesystem": True,
        "networks": ["sovereign-desktop"],
        "publishedPorts": [],
        "workspaceMount": {
            "destination": "/workspace",
            "workspaceId": "job-live-workspace",
            "attemptId": ATTEMPT,
            "worktreeIdentityHash": HASH_C,
            "hostPathHash": HASH_D,
            "readWrite": True,
        },
        "viewScopeHash": HASH_D,
        "inputScopeHash": "e" * 64,
        "cpuMillis": 1000,
        "memoryBytes": 1_073_741_824,
        "pidsLimit": 128,
        "wallTimeSeconds": 3600,
        "idleTimeoutSeconds": 900,
        "workerClaim": "OBSERVED",
    }


def admission() -> DesktopWorkerAdmissionV1:
    return DesktopWorkerAdmissionV1.from_dict(payload())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("privileged", True, "host authority"),
        ("dockerSocketMounted", True, "host authority"),
        ("hostNamespaces", True, "host authority"),
        ("publishedPorts", ["127.0.0.1:8080:8080"], "publish host ports"),
        ("networks", ["sovereign-private"], "network topology"),
        ("workerClaim", "VERIFIED", "may not claim"),
    ],
)
def test_desktop_worker_admission_fails_closed_for_host_authority_and_truth_claims(field, value, message) -> None:
    unsafe = payload()
    unsafe[field] = value
    with pytest.raises(FleetContractError, match=message):
        DesktopWorkerAdmissionV1.from_dict(unsafe)


def test_admission_requires_exact_attempt_workspace_digest_and_split_scopes() -> None:
    allowed = admission()
    assert allowed.to_dict()["authoritative"] is False
    assert allowed.to_runtime_contract().image_digest == IMAGE_DIGEST
    unsafe = payload()
    unsafe["workspaceMount"]["attemptId"] = "attempt-" + "b" * 24
    with pytest.raises(FleetContractError, match="workspace mount"):
        DesktopWorkerAdmissionV1.from_dict(unsafe)
    unsafe = payload()
    unsafe["viewScopeHash"] = unsafe["inputScopeHash"]
    with pytest.raises(FleetContractError, match="distinct"):
        DesktopWorkerAdmissionV1.from_dict(unsafe)
    unsafe = payload()
    unsafe["imageReference"] = "ghcr.io/ouroboroscollective/sovereign-desktop-worker:latest"
    with pytest.raises(FleetContractError, match="digest-bound"):
        DesktopWorkerAdmissionV1.from_dict(unsafe)


def test_computer_use_scopes_are_separated_and_receipts_never_verify_target_effect() -> None:
    allowed = admission()
    frame = DesktopComputerUseRequestV1.create(
        admission=allowed,
        action_id="frame-1",
        input_kind="SCREENSHOT",
        scope_kind="VIEW",
    )
    click = DesktopComputerUseRequestV1.create(
        admission=allowed,
        action_id="click-1",
        input_kind="CLICK",
        scope_kind="CONTROLLER_INPUT",
        normalized_arguments={"x": 12, "y": 34, "button": "left"},
    )
    with pytest.raises(FleetContractError, match="requires controller input"):
        DesktopComputerUseRequestV1.create(
            admission=allowed,
            action_id="bad-click",
            input_kind="CLICK",
            scope_kind="VIEW",
        )
    with pytest.raises(FleetContractError, match="requires view"):
        DesktopComputerUseRequestV1.create(
            admission=allowed,
            action_id="bad-frame",
            input_kind="SCREENSHOT",
            scope_kind="CONTROLLER_INPUT",
        )
    receipt = DesktopInputObservationReceiptV1.create(admission=allowed, request=click, status="SENT")
    assert frame.to_dict()["authoritative"] is False
    assert receipt.to_dict()["targetEffectVerified"] is False
    assert receipt.to_dict()["authoritative"] is False


def test_admission_checks_live_workspace_binding_when_a_session_is_supplied() -> None:
    allowed = admission()
    session = object.__new__(LiveWorkspaceSessionV1)
    object.__setattr__(session, "session_binding_hash", HASH_B)
    object.__setattr__(session, "attempt_id", ATTEMPT)
    object.__setattr__(session, "workspace_id", "job-live-workspace")
    object.__setattr__(session, "worktree_identity_hash", HASH_C)
    assert DesktopWorkerAdmissionV1.from_dict(payload(), session=session).admission_hash == allowed.admission_hash
    unsafe = payload()
    unsafe["sessionBindingHash"] = "f" * 64
    with pytest.raises(FleetContractError, match="live workspace"):
        DesktopWorkerAdmissionV1.from_dict(unsafe, session=session)


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts/sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_desktop_runtime_contract_is_byte_identical_in_deployment_mirror() -> None:
    root = _repo_root()
    assert (
        root / "backend/agent_runtime/desktop_runtime.py"
    ).read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/desktop_runtime.py"
    ).read_bytes()
