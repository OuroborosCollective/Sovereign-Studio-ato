import base64
from dataclasses import replace
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sys
import time

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.desktop_worker import (
    ComputerUseObservationReceiptV1,
    ComputerUseRequestV1,
    DesktopInputGrantV1,
    DesktopViewGatewayReadbackV1,
    DesktopViewGrantV1,
    DesktopWorkerAdmissionV1,
    DesktopWorkerReadbackV1,
    DesktopWorkerSensorReceiptV1,
)
from agent_runtime.fleet_attempts import create_worker_attempt
from agent_runtime.fleet_supervisor import FleetContractError, FleetTask, build_fleet_plan, create_worker_assignment
from agent_runtime.live_workspace import (
    DesktopRuntimeContractV1,
    LiveWorkspaceControlLeaseV1,
    LiveWorkspaceSessionV1,
    SessionReconciliationV1,
    WorkspaceReadbackV1,
)


BASE = "a" * 40
HEAD = "b" * 40
HASH_A = "c" * 64
HASH_B = "d" * 64
HASH_C = "e" * 64
HASH_D = "f" * 64
NOW = 1_787_438_705


def _session():
    task = FleetTask(
        task_id="desktop-worker",
        source_type="issue",
        source_id="1617",
        expected_base_revision=BASE,
        expected_head_revision=HEAD,
        independence_proven=True,
    )
    plan = build_fleet_plan(
        integration_id="desktop-worker-contract",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        architecture_receipt_hashes=[HASH_A],
        tasks=[task],
    )
    assignment = create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id=task.task_id,
        controller_run_id="run-desktop-worker",
        workspace_id="job-desktop-worker",
        workspace_branch="sovereign/desktop-worker",
        run_envelope_hash=HASH_B,
        capability_manifest_hash=HASH_C,
    )
    attempt = create_worker_attempt(assignment, attempt_sequence=1)
    runtime = DesktopRuntimeContractV1.from_dict(
        {
            "runtimeIdentityHash": HASH_A,
            "imageDigest": "sha256:" + HASH_B,
            "privileged": False,
            "dockerSocketMounted": False,
            "hostNamespaces": False,
            "noNewPrivileges": True,
            "capabilitiesDropped": True,
            "readOnlyRootFilesystem": True,
            "workspaceId": assignment.workspace_id,
            "inputScopeHash": HASH_B,
            "viewScopeHash": HASH_C,
        }
    )
    readback = WorkspaceReadbackV1.from_dict(
        {
            "repository": "OuroborosCollective/Sovereign-Studio-ato",
            "workspaceId": assignment.workspace_id,
            "worktreeIdentityHash": HASH_D,
            "observedHeadRevision": HEAD,
            "fleetPlanHash": assignment.plan_hash,
            "controllerStateRef": HASH_C,
            "controllerState": "RUNNING",
            "workspacePathOwner": assignment.workspace_id,
            "desktopRuntimeIdentityHash": runtime.runtime_identity_hash,
        }
    )
    session = LiveWorkspaceSessionV1.bind(
        assignment=assignment,
        attempt=attempt,
        active_attempt=attempt,
        workspace_readback=readback,
        projection_source_hashes=[HASH_A, HASH_B],
        desktop_runtime=runtime,
    )
    reconciliation = session.reconcile(active_attempt=attempt, workspace_readback=readback)
    return session, reconciliation, runtime


def _readback(session, runtime, **overrides):
    value = {
        "runtimeIdentityHash": runtime.runtime_identity_hash,
        "containerIdentityHash": HASH_B,
        "imageDigest": runtime.image_digest,
        "runtimeSourceRevision": session.observed_head_revision,
        "sessionBindingHash": session.session_binding_hash,
        "attemptId": session.attempt_id,
        "attemptHash": session.attempt_hash,
        "workspaceId": session.workspace_id,
        "worktreeIdentityHash": session.worktree_identity_hash,
        "observedHeadRevision": session.observed_head_revision,
        "inputScopeHash": runtime.input_scope_hash,
        "viewScopeHash": runtime.view_scope_hash,
        "networkIdentityHash": HASH_C,
        "egressPolicyHash": HASH_D,
        "mounts": [
            {
                "kind": "ATTEMPT_WORKSPACE",
                "target": "/workspace",
                "sourceIdentityHash": session.worktree_identity_hash,
                "writable": True,
            },
            {"kind": "TMPFS", "target": "/tmp", "writable": True},
            {"kind": "TMPFS", "target": "/run", "writable": True},
            {"kind": "TMPFS", "target": "/home/desktop", "writable": True},
        ],
        "privileged": False,
        "dockerSocketMounted": False,
        "hostNamespaces": False,
        "noNewPrivileges": True,
        "capabilitiesDropped": True,
        "readOnlyRootFilesystem": True,
        "publicPortCount": 0,
        "egressDefaultDeny": True,
        "llmRoutingPresent": False,
        "productionCredentialsPresent": False,
        "lifecycleState": "RUNNING",
        "streamReady": True,
        "inputServiceReady": True,
        "restartCount": 0,
        "observedAtEpoch": NOW - 5,
    }
    value.update(overrides)
    return DesktopWorkerReadbackV1.from_dict(value)


def _sensor(session, reconciliation, observed):
    return DesktopWorkerSensorReceiptV1.from_verified_patchmon_docker(
        session=session,
        readback=observed,
        reconciliation=reconciliation,
        source_receipt_hash=HASH_A,
        source_revision=session.observed_head_revision,
    )


def _admit(session, reconciliation, runtime, observed, *, sensor=None, trusted_now_epoch=NOW):
    return DesktopWorkerAdmissionV1.admit(
        session=session,
        reconciliation=reconciliation,
        runtime_contract=runtime,
        readback=observed,
        sensor_receipt=sensor or _sensor(session, reconciliation, observed),
        expected_network_identity_hash=HASH_C,
        expected_egress_policy_hash=HASH_D,
        trusted_now_epoch=trusted_now_epoch,
    )


def _admission():
    session, reconciliation, runtime = _session()
    observed = _readback(session, runtime)
    return session, reconciliation, runtime, observed, _admit(session, reconciliation, runtime, observed)


def _gateway(session, admission, **overrides):
    value = {
        "gatewayRuntimeIdentityHash": HASH_D,
        "gatewayContainerIdentityHash": HASH_A,
        "imageDigest": admission.image_digest,
        "sessionId": session.session_id,
        "sessionBindingHash": session.session_binding_hash,
        "admissionId": admission.admission_id,
        "runtimeIdentityHash": admission.runtime_identity_hash,
        "workerContainerIdentityHash": admission.container_identity_hash,
        "viewScopeHash": admission.view_scope_hash,
        "attemptId": session.attempt_id,
        "attemptHash": session.attempt_hash,
        "worktreeIdentityHash": session.worktree_identity_hash,
        "observedHeadRevision": session.observed_head_revision,
        "networkIdentityHashes": [HASH_A, HASH_B],
        "workerBackplaneNetworkIdentityHash": HASH_A,
        "viewClientNetworkIdentityHash": HASH_B,
        "egressDefaultDeny": True,
        "networksInternalOnly": True,
        "privileged": False,
        "dockerSocketMounted": False,
        "hostNamespaces": False,
        "noNewPrivileges": True,
        "capabilitiesDropped": True,
        "readOnlyRootFilesystem": True,
        "publicPortCount": 0,
        "workspaceMounted": False,
        "controlSocketMounted": False,
        "authenticatedStreamMode": True,
        "lifecycleState": "RUNNING",
        "restartCount": 0,
        "observedAtEpoch": NOW - 3,
    }
    value.update(overrides)
    return DesktopViewGatewayReadbackV1.from_dict(value)


def _view(session, admission, **overrides):
    return DesktopViewGrantV1.issue(
        session=session,
        admission=admission,
        gateway_readback=_gateway(session, admission, **overrides),
        expected_worker_backplane_network_identity_hash=HASH_A,
        expected_view_client_network_identity_hash=HASH_B,
        subject_hash=HASH_A,
        issued_at_epoch=NOW - 5,
        expires_at_epoch=NOW + 300,
        trusted_now_epoch=NOW,
    )


def _worker_response(request, *, status="OBSERVED", observed_at_epoch=NOW):
    return {
        "status": status,
        "requestHash": request.request_hash,
        "sessionId": request.session_id,
        "sessionBindingHash": request.session_binding_hash,
        "admissionId": request.admission_id,
        "grantId": request.grant_id,
        "subjectHash": request.subject_hash,
        "scopeHash": request.scope_hash,
        "runtimeIdentityHash": request.runtime_identity_hash,
        "containerIdentityHash": request.container_identity_hash,
        "imageDigest": request.image_digest,
        "attemptId": request.attempt_id,
        "attemptHash": request.attempt_hash,
        "worktreeIdentityHash": request.worktree_identity_hash,
        "observedHeadRevision": request.observed_head_revision,
        "inputKind": request.input_kind,
        "observationHash": HASH_A,
        "observedAtEpoch": observed_at_epoch,
    }


def test_admission_binds_one_exact_runtime_attempt_workspace_and_topology() -> None:
    session, reconciliation, runtime, observed, admission = _admission()

    assert admission.session_id == session.session_id
    assert admission.session_binding_hash == session.session_binding_hash
    assert admission.runtime_identity_hash == runtime.runtime_identity_hash
    assert admission.runtime_source_revision == session.observed_head_revision
    assert admission.worktree_identity_hash == session.worktree_identity_hash
    assert admission.to_dict()["sensorReceiptHash"] == _sensor(session, reconciliation, observed).sensor_receipt_hash
    assert admission.to_dict()["status"] == "ADMITTED"
    assert admission.to_dict()["authoritative"] is False
    assert observed.to_dict()["topologyHash"] == admission.topology_hash


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("privileged", True, "security readback"),
        ("dockerSocketMounted", True, "security readback"),
        ("hostNamespaces", True, "security readback"),
        ("noNewPrivileges", False, "security readback"),
        ("capabilitiesDropped", False, "security readback"),
        ("readOnlyRootFilesystem", False, "security readback"),
        ("publicPortCount", 1, "network exposure"),
        ("egressDefaultDeny", False, "network exposure"),
        ("llmRoutingPresent", True, "LLM routing"),
        ("productionCredentialsPresent", True, "production credentials"),
        ("restartCount", 1, "restart"),
    ],
)
def test_admission_rejects_unsafe_runtime_state(field: str, value, message: str) -> None:
    session, reconciliation, runtime = _session()
    observed = _readback(session, runtime)
    payload = observed.to_dict()
    payload[field] = value
    unsafe = DesktopWorkerReadbackV1.from_dict(payload)

    with pytest.raises(FleetContractError, match=message):
        _admit(session, reconciliation, runtime, unsafe)


def test_admission_requires_integral_typed_fresh_sensor_and_session_binding() -> None:
    session, reconciliation, runtime = _session()
    observed = _readback(session, runtime)
    with pytest.raises(FleetContractError, match="trusted PatchMon/Docker sensor receipt"):
        DesktopWorkerAdmissionV1.admit(
            session=session,
            reconciliation=reconciliation,
            runtime_contract=runtime,
            readback=observed,
            sensor_receipt={"sourceKind": "PATCHMON_DOCKER_OTBA"},
            expected_network_identity_hash=HASH_C,
            expected_egress_policy_hash=HASH_D,
            trusted_now_epoch=NOW,
        )
    tampered = replace(_sensor(session, reconciliation, observed), sensor_receipt_hash=HASH_B)
    with pytest.raises(FleetContractError, match="integrity"):
        _admit(session, reconciliation, runtime, observed, sensor=tampered)
    foreign_session = SessionReconciliationV1(
        session_id="other-session",
        session_binding_hash=reconciliation.session_binding_hash,
        projection_state="LIVE",
        blockers=(),
        fresh_readback_hash=reconciliation.fresh_readback_hash,
    )
    with pytest.raises(FleetContractError, match="fresh LIVE"):
        _admit(session, foreign_session, runtime, observed)
    with pytest.raises(FleetContractError, match="view and input scopes"):
        _admit(
            session,
            reconciliation,
            runtime,
            _readback(session, runtime, viewScopeHash=runtime.input_scope_hash),
        )
    stale = _readback(session, runtime, observedAtEpoch=NOW - 301)
    with pytest.raises(FleetContractError, match="freshness"):
        _admit(session, reconciliation, runtime, stale)


def test_admission_rejects_digest_attempt_mount_network_stream_and_source_drift() -> None:
    session, reconciliation, runtime = _session()
    with pytest.raises(FleetContractError, match="contradicts"):
        _admit(session, reconciliation, runtime, _readback(session, runtime, imageDigest="sha256:" + HASH_C))
    with pytest.raises(FleetContractError, match="source revision"):
        _admit(session, reconciliation, runtime, _readback(session, runtime, runtimeSourceRevision=BASE))
    with pytest.raises(FleetContractError, match="active workspace session"):
        _admit(session, reconciliation, runtime, _readback(session, runtime, attemptId="attempt-" + ("0" * 24)))
    with pytest.raises(FleetContractError, match="attempt workspace mount"):
        _admit(
            session,
            reconciliation,
            runtime,
            _readback(
                session,
                runtime,
                mounts=[
                    {
                        "kind": "ATTEMPT_WORKSPACE",
                        "target": "/workspace",
                        "sourceIdentityHash": HASH_A,
                        "writable": True,
                    }
                ],
            ),
        )
    with pytest.raises(FleetContractError, match="network or egress"):
        _admit(session, reconciliation, runtime, _readback(session, runtime, networkIdentityHash=HASH_A))
    with pytest.raises(FleetContractError, match="unavailable"):
        _admit(session, reconciliation, runtime, _readback(session, runtime, streamReady=False))


def test_view_requires_hardened_gateway_and_cannot_send_input_or_cross_principal() -> None:
    session, _, _, _, admission = _admission()
    with pytest.raises(FleetContractError, match="gateway security"):
        _view(session, admission, authenticatedStreamMode=False)
    with pytest.raises(FleetContractError, match="gateway security"):
        _view(session, admission, egressDefaultDeny=False)
    with pytest.raises(FleetContractError, match="expected private networks"):
        _view(
            session,
            admission,
            workerBackplaneNetworkIdentityHash=HASH_C,
            networkIdentityHashes=[HASH_C, HASH_B],
        )
    view = _view(session, admission)
    request = ComputerUseRequestV1.create(
        session=session,
        admission=admission,
        grant=view,
        subject_hash=HASH_A,
        action_id="view-1",
        input_kind="viewport_readback",
        payload={},
        requested_at_epoch=NOW - 3,
    )

    assert request.to_dict()["rawPayloadReturned"] is False
    assert request.to_dict()["inputKind"] == "VIEWPORT_READBACK"
    with pytest.raises(FleetContractError, match="principal"):
        ComputerUseRequestV1.create(
            session=session,
            admission=admission,
            grant=view,
            subject_hash=HASH_B,
            action_id="view-other-principal",
            input_kind="screenshot",
            payload={},
            requested_at_epoch=NOW - 3,
        )
    with pytest.raises(FleetContractError, match="input operations"):
        ComputerUseRequestV1.create(
            session=session,
            admission=admission,
            grant=view,
            subject_hash=HASH_A,
            action_id="input-1",
            input_kind="click",
            payload={"x": 0.5, "y": 0.5, "button": 1},
            requested_at_epoch=NOW - 3,
        )


def test_input_delivery_requires_current_lease_and_give_back_revokes_existing_request() -> None:
    session, reconciliation, _, _, admission = _admission()
    lease = LiveWorkspaceControlLeaseV1.issue_takeover(
        session=session,
        owner_subject_hash=HASH_A,
        input_scope_hash=admission.input_scope_hash,
        reconciliation=reconciliation,
    )
    grant = DesktopInputGrantV1.issue(
        session=session,
        admission=admission,
        control_lease=lease,
        issued_at_epoch=NOW - 5,
        expires_at_epoch=NOW + 300,
    )
    request = ComputerUseRequestV1.create(
        session=session,
        admission=admission,
        grant=grant,
        subject_hash=HASH_A,
        reconciliation=reconciliation,
        control_lease=lease,
        action_id="input-2",
        input_kind="type",
        payload={"text": "pytest -q"},
        requested_at_epoch=NOW - 3,
    )

    assert request.payload["text"] == "pytest -q"
    assert "pytest -q" not in str(request.to_dict())
    payload = request.worker_payload(
        admission=admission,
        reconciliation=reconciliation,
        control_lease=lease,
        trusted_now_epoch=NOW,
    )
    assert payload["containerIdentityHash"] == admission.container_identity_hash
    assert payload["imageDigest"] == admission.image_digest
    assert payload["controlLeaseId"] == lease.lease_id
    returned = lease.give_back(reconciliation)
    with pytest.raises(FleetContractError, match="current user-control"):
        request.worker_payload(
            admission=admission,
            reconciliation=reconciliation,
            control_lease=returned,
            trusted_now_epoch=NOW,
        )
    with pytest.raises(FleetContractError, match="principal"):
        ComputerUseRequestV1.create(
            session=session,
            admission=admission,
            grant=grant,
            subject_hash=HASH_B,
            reconciliation=reconciliation,
            control_lease=lease,
            action_id="input-other-principal",
            input_kind="click",
            payload={"x": 0.5, "y": 0.5, "button": 1},
            requested_at_epoch=NOW - 3,
        )
    with pytest.raises(FleetContractError, match="expired"):
        ComputerUseRequestV1.create(
            session=session,
            admission=admission,
            grant=grant,
            subject_hash=HASH_A,
            reconciliation=reconciliation,
            control_lease=lease,
            action_id="input-expired",
            input_kind="keypress",
            payload={"key": "CTRL+L"},
            requested_at_epoch=NOW + 301,
        )


def test_worker_receipt_binds_every_runtime_and_never_creates_a_verified_effect() -> None:
    session, reconciliation, _, _, admission = _admission()
    view = _view(session, admission)
    request = ComputerUseRequestV1.create(
        session=session,
        admission=admission,
        grant=view,
        subject_hash=HASH_A,
        action_id="screenshot-1",
        input_kind="screenshot",
        payload={},
        requested_at_epoch=NOW - 3,
    )
    receipt = ComputerUseObservationReceiptV1.from_worker(
        request=request,
        admission=admission,
        worker_response=_worker_response(request),
    )
    assert receipt.to_dict()["targetEffectVerified"] is False
    response = _worker_response(request)
    response["imageDigest"] = "sha256:" + HASH_C
    with pytest.raises(FleetContractError, match="binding"):
        ComputerUseObservationReceiptV1.from_worker(
            request=request,
            admission=admission,
            worker_response=response,
        )
    response = _worker_response(request)
    response["status"] = "SENT"
    with pytest.raises(FleetContractError, match="status"):
        ComputerUseObservationReceiptV1.from_worker(
            request=request,
            admission=admission,
            worker_response=response,
        )
    response = _worker_response(request)
    response["status"] = "VERIFIED"
    with pytest.raises(FleetContractError, match="may not claim verification"):
        ComputerUseObservationReceiptV1.from_worker(
            request=request,
            admission=admission,
            worker_response=response,
        )


def test_view_gateway_capability_requires_every_exact_binding() -> None:
    root = _repo_root()
    gateway_path = root / "tools/sovereign-desktop-worker/desktop-view-gateway.py"
    specification = importlib.util.spec_from_file_location("desktop_view_gateway_test", gateway_path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    now = int(time.time())
    config = {
        "key": b"x" * 32,
        "sessionId": "desktop-gateway-test",
        "sessionBindingHash": HASH_A,
        "admissionId": "desktop-admission-" + ("a" * 24),
        "viewScopeHash": HASH_B,
        "runtimeIdentityHash": HASH_C,
        "containerIdentityHash": HASH_D,
        "gatewayRuntimeIdentityHash": HASH_A,
        "gatewayContainerIdentityHash": HASH_B,
        "gatewayImageDigest": "sha256:" + HASH_C,
        "workerBackplaneNetworkIdentityHash": HASH_D,
        "viewClientNetworkIdentityHash": HASH_A,
        "attemptId": "attempt-" + ("b" * 24),
        "attemptHash": HASH_B,
        "worktreeIdentityHash": HASH_C,
        "observedHeadRevision": HEAD,
    }
    claims = {
        **{key: value for key, value in config.items() if key != "key"},
        "grantId": "desktop-view-" + ("c" * 24),
        "subjectHash": HASH_D,
        "issuedAtEpoch": now - 1,
        "expiresAtEpoch": now + 60,
        "nonce": "test-nonce",
    }
    body = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    token += "." + base64.urlsafe_b64encode(hmac.new(config["key"], body, hashlib.sha256).digest()).decode("ascii").rstrip("=")
    verified_claims = module._verify_token(token, config)
    assert verified_claims["grantId"] == claims["grantId"]
    module._consume_nonce(verified_claims, config)
    with pytest.raises(ValueError, match="already consumed"):
        module._consume_nonce(module._verify_token(token, config), config)
    claims["gatewayContainerIdentityHash"] = HASH_D
    bad_body = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    bad_token = base64.urlsafe_b64encode(bad_body).decode("ascii").rstrip("=")
    bad_token += "." + base64.urlsafe_b64encode(hmac.new(config["key"], bad_body, hashlib.sha256).digest()).decode("ascii").rstrip("=")
    with pytest.raises(ValueError, match="binding"):
        module._verify_token(bad_token, config)
    claims["gatewayContainerIdentityHash"] = config["gatewayContainerIdentityHash"]
    claims["observedHeadRevision"] = BASE
    bad_body = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    bad_token = base64.urlsafe_b64encode(bad_body).decode("ascii").rstrip("=")
    bad_token += "." + base64.urlsafe_b64encode(hmac.new(config["key"], bad_body, hashlib.sha256).digest()).decode("ascii").rstrip("=")
    with pytest.raises(ValueError, match="binding"):
        module._verify_token(bad_token, config)


def test_desktop_control_retains_effect_and_revoked_lease_replay_protection() -> None:
    root = _repo_root()
    control_path = root / "tools/sovereign-desktop-worker/desktop-control.py"
    specification = importlib.util.spec_from_file_location("desktop_control_test", control_path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    expiration = int(time.time()) + 120
    module._CONSUMED_EFFECT_REQUESTS.clear()
    module._REVOKED_INPUT_LEASES.clear()
    module._ACTIVE_INPUT_LEASE = None
    module._record_activity = lambda: None
    first_hash = "a" * 64
    module._reserve_effect_request(first_hash, expires_at_epoch=expiration)
    for index in range(1, module.MAX_CONSUMED_EFFECT_REQUESTS):
        module._reserve_effect_request(f"{index:064x}", expires_at_epoch=expiration)
    with pytest.raises(ValueError, match="already consumed"):
        module._reserve_effect_request(first_hash, expires_at_epoch=expiration)
    with pytest.raises(ValueError, match="cache is exhausted"):
        module._reserve_effect_request("f" * 64, expires_at_epoch=expiration)
    bindings = {
        "sessionId": "desktop-control-test",
        "sessionBindingHash": HASH_A,
        "admissionId": "desktop-admission-" + ("a" * 24),
        "runtimeIdentityHash": HASH_A,
        "containerIdentityHash": HASH_B,
        "imageDigest": "sha256:" + HASH_C,
        "attemptId": "attempt-" + ("d" * 24),
        "attemptHash": HASH_D,
        "worktreeIdentityHash": HASH_A,
        "observedHeadRevision": HEAD,
        "inputScopeHash": HASH_B,
    }
    user_controlled = {
        "operation": "LEASE_UPDATE",
        **bindings,
        "controlLeaseState": "USER_CONTROLLED",
        "grantId": "desktop-input-" + ("b" * 24),
        "controlLeaseId": "livelease-" + ("c" * 24),
        "controlLeaseReadbackHash": HASH_C,
        "subjectHash": HASH_D,
        "grantExpiresAtEpoch": expiration,
    }
    gave_back = {
        "operation": "LEASE_UPDATE",
        **bindings,
        "controlLeaseState": "AGENT_CONTROLLED_REBOUND",
    }
    pre_admission_bindings = dict(bindings)
    pre_admission_bindings["admissionId"] = ""
    with pytest.raises(ValueError, match="admission"):
        module._apply_lease_update(user_controlled, pre_admission_bindings)
    module._apply_lease_update(user_controlled, bindings)
    module._apply_lease_update(gave_back, bindings)
    assert module._ACTIVE_INPUT_LEASE is None
    with pytest.raises(ValueError, match="revoked"):
        module._apply_lease_update(user_controlled, bindings)


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts/sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_desktop_worker_contract_is_byte_identical_in_deployment_mirror() -> None:
    root = _repo_root()
    assert (
        root / "backend/agent_runtime/desktop_worker.py"
    ).read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/desktop_worker.py"
    ).read_bytes()


def test_native_desktop_worker_assets_are_digest_bound_and_non_privileged() -> None:
    root = _repo_root()
    dockerfile = (root / "tools/sovereign-desktop-worker/Dockerfile").read_text(encoding="utf-8")
    compose = (root / "tools/sovereign-desktop-worker/compose.yaml").read_text(encoding="utf-8")
    entrypoint = (root / "tools/sovereign-desktop-worker/desktop-entrypoint").read_text(encoding="utf-8")
    control = (root / "tools/sovereign-desktop-worker/desktop-control.py").read_text(encoding="utf-8")
    gateway = (root / "tools/sovereign-desktop-worker/desktop-view-gateway.py").read_text(encoding="utf-8")
    validator = (root / "tools/sovereign-desktop-worker/operator-validate.py").read_text(encoding="utf-8")
    canary = (root / ".github/workflows/sovereign-desktop-worker.yml").read_text(encoding="utf-8")

    for name, source in {
        "desktop-control.py": control,
        "desktop-view-gateway.py": gateway,
        "operator-validate.py": validator,
    }.items():
        compile(source, name, "exec")

    assert "FROM debian:12.13-slim@sha256:67b30a61dc87758f0caf819646104f29ecbda97d920aaf5edc834128ac8493d3" in dockerfile
    assert "USER desktop" in dockerfile and "desktop-controller" in dockerfile
    assert "firefox-esr" in dockerfile and "mousepad" in dockerfile and "xterm" in dockerfile and "git" in dockerfile
    assert "privileged: false" in compose
    assert "read_only: true" in compose
    assert "cap_drop:" in compose and "ALL" in compose
    assert "no-new-privileges:true" in compose
    assert "/var/run/docker.sock" not in compose
    assert "ports:" not in compose
    assert compose.count("internal: true") == 2
    assert "x11vnc" in entrypoint and "websockify" in entrypoint and "watchdog" in entrypoint
    assert "shell_root" not in control and "docker" not in control
    assert "VERIFIED" not in control and "SO_PEERCRED" in control and "LEASE_UPDATE" in control
    assert "DESKTOP_CONTROL_SOCKET" not in gateway and "view_token" in gateway
    assert "gatewayRuntimeIdentityHash" in gateway and "_consume_nonce" in gateway
    assert "repository digest reference" in validator and "RepoDigests" in validator
    assert 'Path(required_path("DESKTOP_VIEW_GATEWAY_KEY_FILE")).resolve()' in validator
    assert 'Path(required("DESKTOP_VIEW_GATEWAY_KEY_FILE")).resolve()' not in validator
    assert "DESKTOP_VIEW_GATEWAY_RUNTIME_IDENTITY_HASH" in compose
    assert "DESKTOP_WORKER_BACKPLANE_NETWORK_IDENTITY_HASH" in compose
    assert "DESKTOP_VIEW_CLIENT_NETWORK_IDENTITY_HASH" in compose
    assert "/run:rw,nosuid,nodev,noexec,size=32m,uid=10001,gid=10001,mode=0711" in compose
    assert "--tmpfs /run:rw,nosuid,nodev,noexec,size=32m,uid=10001,gid=10001,mode=0711" in canary
    assert "--read-only" in canary and "--cap-drop ALL" in canary
    assert "--local-canary-only" in canary and "DESKTOP_LOCAL_IMAGE_READBACK_REF" in canary
    assert 'fields["requestHash"] = stable_hash(fields)\n          fields["payload"] = payload' in canary
    assert '"admissionId": os.environ["DESKTOP_GATEWAY_ADMISSION_ID"]' in canary
    assert canary.index('python3 tools/sovereign-desktop-worker/operator-validate.py --require-gateway --local-canary-only') < canary.index('view_token="$(')
    assert canary.index('view_token="$(') < canary.index('sudo chown 10002:10002 "$key_file"')
    assert canary.index('sudo chown 10002:10002 "$key_file"') < canary.index('gateway="desktop-view-gateway-canary-$GITHUB_RUN_ID"')
    assert 'sudo rm -rf -- "$attempt_parent"' in canary
    assert "--network none" not in canary
    assert "--entrypoint curl" not in canary
    assert "http.client.HTTPConnection" in canary
    assert "CANARY_VIEW_TOKEN" in canary
    assert "continuity" not in canary.casefold()
    assert "workflow_dispatch:" in canary
