from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.fleet_attempts import create_worker_attempt
from agent_runtime.fleet_supervisor import FleetContractError, FleetTask, build_fleet_plan, create_worker_assignment
from agent_runtime.live_workspace import (
    ChatBubbleV1,
    DesktopRuntimeContractV1,
    LiveWorkspaceControlLeaseV1,
    LiveWorkspaceSessionV1,
    VisualProjectionEventV1,
    WorkspaceEvidenceAnchorV1,
    WorkspaceReadbackV1,
)

BASE = "a" * 40
HEAD = "b" * 40
HASH_A = "c" * 64
HASH_B = "d" * 64
HASH_C = "e" * 64


def active_assignment():
    task = FleetTask(
        task_id="live-workspace",
        source_type="issue",
        source_id="1615",
        expected_base_revision=BASE,
        expected_head_revision=HEAD,
        independence_proven=True,
    )
    plan = build_fleet_plan(
        integration_id="live-workspace-contract",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        architecture_receipt_hashes=[HASH_A],
        tasks=[task],
    )
    return create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id=task.task_id,
        controller_run_id="run-live-workspace",
        workspace_id="job-live-workspace",
        workspace_branch="sovereign/live-workspace",
        run_envelope_hash=HASH_B,
        capability_manifest_hash=HASH_C,
    )


def readback(*, assignment, head: str = HEAD, worktree_hash: str = HASH_A, controller_state: str = "RUNNING", runtime_hash: str | None = None):
    return WorkspaceReadbackV1.from_dict({
        "repository": "OuroborosCollective/Sovereign-Studio-ato",
        "workspaceId": assignment.workspace_id,
        "worktreeIdentityHash": worktree_hash,
        "observedHeadRevision": head,
        "fleetPlanHash": assignment.plan_hash,
        "controllerStateRef": HASH_B,
        "controllerState": controller_state,
        "workspacePathOwner": assignment.workspace_id,
        "desktopRuntimeIdentityHash": runtime_hash,
    })


def bind_session(*, runtime=None):
    assignment = active_assignment()
    attempt = create_worker_attempt(assignment, attempt_sequence=1)
    return LiveWorkspaceSessionV1.bind(
        assignment=assignment,
        attempt=attempt,
        active_attempt=attempt,
        workspace_readback=readback(assignment=assignment, runtime_hash=runtime.runtime_identity_hash if runtime else None),
        projection_source_hashes=[HASH_A, HASH_B],
        desktop_runtime=runtime,
    ), assignment, attempt


def test_live_session_is_deterministic_and_non_authoritative() -> None:
    session, assignment, attempt = bind_session()
    repeat = LiveWorkspaceSessionV1.bind(
        assignment=assignment,
        attempt=attempt,
        active_attempt=attempt,
        workspace_readback=readback(assignment=assignment),
        projection_source_hashes=[HASH_B, HASH_A],
    )

    assert session == repeat
    assert session.session_id.startswith("livews-")
    assert session.to_dict()["projectionState"] == "LIVE"
    assert session.to_dict()["authoritative"] is False
    assert session.workspace_id == assignment.workspace_id
    assert session.attempt_id == attempt.attempt_id


def test_bind_rejects_wrong_attempt_workspace_head_and_terminal_controller() -> None:
    session, assignment, attempt = bind_session()
    other_attempt = create_worker_attempt(assignment, attempt_sequence=2)
    with pytest.raises(FleetContractError, match="future worker attempt"):
        LiveWorkspaceSessionV1.bind(
            assignment=assignment,
            attempt=other_attempt,
            active_attempt=attempt,
            workspace_readback=readback(assignment=assignment),
            projection_source_hashes=[HASH_A],
        )
    with pytest.raises(FleetContractError, match="head"):
        LiveWorkspaceSessionV1.bind(
            assignment=assignment,
            attempt=attempt,
            active_attempt=attempt,
            workspace_readback=readback(assignment=assignment, head=BASE),
            projection_source_hashes=[HASH_A],
        )
    with pytest.raises(FleetContractError, match="live-bindable"):
        LiveWorkspaceSessionV1.bind(
            assignment=assignment,
            attempt=attempt,
            active_attempt=attempt,
            workspace_readback=readback(assignment=assignment, controller_state="COMPLETED_UNVERIFIED"),
            projection_source_hashes=[HASH_A],
        )
    assert session.projection_state == "LIVE"


def test_reconciliation_fails_closed_for_retry_worktree_head_or_controller_drift() -> None:
    session, assignment, attempt = bind_session()
    newer = create_worker_attempt(assignment, attempt_sequence=2)
    stale = session.reconcile(active_attempt=newer, workspace_readback=readback(assignment=assignment, head=BASE, worktree_hash=HASH_B))
    assert stale.projection_state == "STALE"
    assert set(stale.blockers) == {"ACTIVE_ATTEMPT_CHANGED", "GIT_HEAD_CHANGED", "WORKTREE_CHANGED"}

    terminal = session.reconcile(active_attempt=attempt, workspace_readback=readback(assignment=assignment, controller_state="FAILED"))
    assert terminal.projection_state == "STALE"
    assert terminal.blockers == ("CONTROLLER_STATE_CHANGED",)


def test_desktop_contract_rejects_host_authority_and_requires_split_scopes() -> None:
    allowed = DesktopRuntimeContractV1.from_dict({
        "runtimeIdentityHash": HASH_A,
        "imageDigest": "sha256:" + HASH_B,
        "privileged": False,
        "dockerSocketMounted": False,
        "hostNamespaces": False,
        "noNewPrivileges": True,
        "capabilitiesDropped": True,
        "readOnlyRootFilesystem": True,
        "workspaceId": "job-live-workspace",
        "inputScopeHash": HASH_B,
        "viewScopeHash": HASH_C,
    })
    assert allowed.to_dict()["authoritative"] is False
    unsafe = allowed.to_dict()
    unsafe["privileged"] = True
    with pytest.raises(FleetContractError, match="host authority"):
        DesktopRuntimeContractV1.from_dict(unsafe)
    unsafe = allowed.to_dict()
    unsafe["viewScopeHash"] = HASH_B
    with pytest.raises(FleetContractError, match="distinct"):
        DesktopRuntimeContractV1.from_dict(unsafe)


def test_visual_observation_is_bound_but_never_a_success_receipt() -> None:
    session, _, _ = bind_session()
    event = VisualProjectionEventV1.create(
        session=session,
        event_type="FRAME_OBSERVED",
        action_id="tool-call-1",
        observation_hash=HASH_A,
    )
    payload = event.to_dict()
    assert payload["claim"] == "OBSERVED"
    assert payload["authoritative"] is False
    with pytest.raises(FleetContractError, match="unknown visual"):
        VisualProjectionEventV1.create(session=session, event_type="RUNTIME_VERIFIED", action_id="tool-call-1", observation_hash=HASH_A)


def test_evidence_anchor_requires_canonical_receipts_and_attempt_binding() -> None:
    session, _, _ = bind_session()
    observed = VisualProjectionEventV1.create(session=session, event_type="TERMINAL_VIEW_PROJECTED", action_id="tool-call-1", observation_hash=HASH_A)
    anchor = WorkspaceEvidenceAnchorV1.create(
        session=session,
        claim_type="TEST_PROCESS_EXIT_0",
        verdict="VERIFIED",
        source_receipt_hashes=[HASH_B],
        source_revision=HEAD,
        observation_event=observed,
    )
    assert anchor.to_dict()["sourceReceiptHashes"] == [HASH_B]
    assert anchor.to_dict()["authoritative"] is False
    with pytest.raises(FleetContractError, match="canonical evidence receipts"):
        WorkspaceEvidenceAnchorV1.create(
            session=session,
            claim_type="TEST_PROCESS_EXIT_0",
            verdict="VERIFIED",
            source_receipt_hashes=[],
            source_revision=HEAD,
        )


def test_takeover_and_give_back_require_fresh_readback_and_fail_closed_on_drift() -> None:
    session, assignment, attempt = bind_session()
    fresh = session.reconcile(active_attempt=attempt, workspace_readback=readback(assignment=assignment))
    lease = LiveWorkspaceControlLeaseV1.issue_takeover(
        session=session,
        owner_subject_hash=HASH_A,
        input_scope_hash=HASH_B,
        reconciliation=fresh,
    )
    assert lease.state == "USER_CONTROLLED"
    stale = session.reconcile(active_attempt=attempt, workspace_readback=readback(assignment=assignment, head=BASE))
    assert lease.give_back(stale).state == "BLOCKED_STALE_STATE"
    assert lease.give_back(fresh).state == "AGENT_CONTROLLED_REBOUND"


def test_chat_is_limited_to_typed_bubbles_and_firewalls_internal_reasoning() -> None:
    bubble = ChatBubbleV1.create(bubble_kind="MATERIAL_BLOCKER", text="Der gebundene Workspace ist nicht mehr aktuell.", canonical_reference_hashes=[HASH_A])
    assert bubble.to_dict()["bubbleKind"] == "MATERIAL_BLOCKER"
    with pytest.raises(FleetContractError, match="forbidden"):
        ChatBubbleV1.create(bubble_kind="STATUS_STREAM", text="laufender Status", canonical_reference_hashes=[])
    with pytest.raises(FleetContractError, match="internal reasoning"):
        ChatBubbleV1.create(bubble_kind="REQUIRED_QUESTION", text="Reasoning: internal chain-of-thought", canonical_reference_hashes=[])


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts/sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_live_workspace_contract_is_byte_identical_in_deployment_mirror() -> None:
    root = _repo_root()
    canonical = root / "backend/agent_runtime/live_workspace.py"
    mirror = root / "scripts/sovereign-backend/agent_runtime/live_workspace.py"
    assert canonical.read_bytes() == mirror.read_bytes()
