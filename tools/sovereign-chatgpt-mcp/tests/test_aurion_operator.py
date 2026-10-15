from __future__ import annotations

from copy import deepcopy
import json
import subprocess

import pytest

from aurion_operator import AurionOperatorRuntime
from broker import BrokerRuntime
from command_contract import is_mutating_action


REVISION = "4" * 40
IMAGE_ID = "sha256:" + "a" * 64
CONTAINER_ID = "b" * 64


def runtime_identity() -> dict:
    return {
        "ok": True,
        "status": "AURION_RUNTIME_VERIFIED",
        "expectedRevision": REVISION,
        "observedRevision": REVISION,
        "container": "echoes-of-aurion-aurion-1",
        "containerId": CONTAINER_ID,
        "image": f"echoes-of-aurion:{REVISION}",
        "imageId": IMAGE_ID,
        "composeProject": "echoes-of-aurion",
        "composeService": "aurion",
        "running": True,
        "health": "healthy",
        "revisionBound": True,
        "mutationPerformed": False,
        "secretValuesReturned": False,
    }


def account_readback(role: str = "user") -> dict:
    return {
        "ok": True,
        "status": "AURION_ACCOUNT_ROLE_READBACK_VERIFIED",
        "runtimeIdentity": runtime_identity(),
        "account": {"id": 7, "openId": "local:thosu", "role": role},
        "readbackSha256": "d" * 64,
        "readbackVerified": True,
        "localCredentialsRead": False,
        "mutationPerformed": False,
        "secretValuesReturned": False,
    }


def test_plan_is_bounded_to_one_local_users_row(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setattr(runtime, "account_role_readback", lambda **kwargs: account_readback("user"))
    result = runtime.account_role_plan(open_id="local:thosu", role="admin", expected_revision=REVISION)
    assert result["ok"] is True
    assert result["account"] == {"id": 7, "openId": "local:thosu", "role": "user"}
    assert result["requestedRole"] == "admin"
    assert len(result["confirmationSha256"]) == 64
    assert "localCredentials" in result["excluded"]
    assert result["mutationPerformed"] is False


def test_readback_rejects_non_local_identity_before_docker_or_db(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setattr(runtime, "runtime_identity", lambda *_: (_ for _ in ()).throw(AssertionError("runtime must not execute")))
    result = runtime.account_role_readback(open_id="oauth:thosu", expected_revision=REVISION)
    assert result["ok"] is False
    assert result["failureFamily"] == "AURION_ACCOUNT_ID_INVALID"


def test_apply_requires_owner_and_private_write_gate(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.delenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", raising=False)
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", raising=False)
    denied = runtime.account_role_apply(
        open_id="local:thosu", role="admin", expected_revision=REVISION,
        confirmation_sha256="e" * 64, owner_approved=False,
    )
    disabled = runtime.account_role_apply(
        open_id="local:thosu", role="admin", expected_revision=REVISION,
        confirmation_sha256="e" * 64, owner_approved=True,
    )
    assert denied["failureFamily"] == "OWNER_APPROVAL_REQUIRED"
    assert disabled["failureFamily"] == "AURION_WRITE_DISABLED"


def test_apply_replans_and_requires_db_and_runtime_readback(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", "1")
    plan = {
        "ok": True,
        "runtimeIdentity": runtime_identity(),
        "account": {"id": 7, "openId": "local:thosu", "role": "user"},
        "requestedRole": "admin",
        "confirmationSha256": "e" * 64,
    }
    monkeypatch.setattr(runtime, "account_role_plan", lambda **kwargs: plan)
    monkeypatch.setattr(runtime, "runtime_identity", lambda *_: runtime_identity())
    monkeypatch.setattr(runtime, "account_role_readback", lambda **kwargs: account_readback("admin"))
    monkeypatch.setattr(runtime, "_exec_node_json", lambda *args, **kwargs: {
        "ok": True,
        "payload": {
            "before": {"id": 7, "openId": "local:thosu", "role": "user"},
            "after": {"id": 7, "openId": "local:thosu", "role": "admin"},
            "mutationPerformed": True,
        },
    })
    result = runtime.account_role_apply(
        open_id="local:thosu", role="admin", expected_revision=REVISION,
        confirmation_sha256="e" * 64, owner_approved=True,
    )
    assert result["ok"] is True
    assert result["status"] == "AURION_ACCOUNT_ROLE_APPLIED_VERIFIED"
    assert result["after"]["role"] == "admin"
    assert result["identityPreserved"] is True
    assert result["readbackVerified"] is True
    assert result["localCredentialsRead"] is False


def test_aurion_apply_is_host_queue_mutation_and_owner_intersection_is_preserved(monkeypatch) -> None:
    assert is_mutating_action("aurion_account_role_apply")
    runtime = BrokerRuntime()
    approvals: list[bool] = []

    def apply(**kwargs):
        approvals.append(bool(kwargs["owner_approved"]))
        return {"ok": bool(kwargs["owner_approved"]), "status": "AURION_TEST"}

    monkeypatch.setattr(runtime.aurion, "account_role_apply", apply)
    args = {
        "open_id": "local:thosu",
        "role": "admin",
        "expected_revision": REVISION,
        "confirmation_sha256": "e" * 64,
        "owner_approved": True,
    }
    runtime.private_owner_mode = False
    runtime.dispatch("aurion_account_role_apply", args, execution_origin="host_worker")
    runtime.private_owner_mode = True
    runtime.dispatch("aurion_account_role_apply", args, execution_origin="host_worker")
    assert approvals == [False, True]


OIDC_OPEN_ID = "0123456789abcdef" * 4
OTHER_OIDC_OPEN_ID = "fedcba9876543210" * 4


class AurionProcessAdapter:
    """Synthetic responses only at the subprocess/Docker adapter boundary."""

    def __init__(self, open_id: str) -> None:
        self.account = {"id": 7, "openId": open_id, "role": "user"}
        self.other_account = {"id": 8, "openId": OTHER_OIDC_OPEN_ID, "role": "user"}
        self.container_id = CONTAINER_ID
        self.image_id = IMAGE_ID
        self.revision = REVISION
        self.calls: list[list[str]] = []
        self.writes: list[list[str]] = []
        self.read_rows: list[dict] | None = None
        self.post_write_change: str | None = None

    def __call__(self, argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        if argv == ["docker", "inspect", "echoes-of-aurion-aurion-1"]:
            payload = [{
                "Id": self.container_id,
                "Image": self.image_id,
                "Config": {
                    "Image": f"echoes-of-aurion:{self.revision}",
                    "Labels": {
                        "com.docker.compose.project": "echoes-of-aurion",
                        "com.docker.compose.service": "aurion",
                    },
                },
                "State": {"Running": True, "Health": {"Status": "healthy"}},
            }]
        else:
            assert argv[:5] == ["docker", "exec", "echoes-of-aurion-aurion-1", "node", "-e"]
            assert argv[6] == "--"
            args = argv[7:]
            selected = self.other_account if args[0] == OTHER_OIDC_OPEN_ID else self.account
            if len(args) == 1:
                payload = {"rows": deepcopy(self.read_rows if self.read_rows is not None else [selected])}
            else:
                assert len(args) == 3
                self.writes.append(args)
                before = deepcopy(selected)
                selected["role"] = args[1]
                payload = {"before": before, "after": deepcopy(selected), "mutationPerformed": True}
                if self.post_write_change == "id":
                    selected["id"] = 99
                elif self.post_write_change == "openId":
                    selected["openId"] = OTHER_OIDC_OPEN_ID
                elif self.post_write_change == "role":
                    selected["role"] = "user"
                elif self.post_write_change == "containerId":
                    self.container_id = "c" * 64
                elif self.post_write_change == "imageId":
                    self.image_id = "sha256:" + "d" * 64
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")


@pytest.mark.parametrize("open_id", ["local:thosu", OIDC_OPEN_ID])
def test_real_operator_plan_and_apply_preserve_exact_account_and_runtime_contract(monkeypatch, open_id: str) -> None:
    adapter = AurionProcessAdapter(open_id)
    runtime = AurionOperatorRuntime(runner=adapter)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", "1")

    readback = runtime.account_role_readback(open_id=open_id, expected_revision=REVISION)
    assert readback["account"] == {"id": 7, "openId": open_id, "role": "user"}
    assert readback["readbackVerified"] is True
    plan = runtime.account_role_plan(open_id=open_id, role="admin", expected_revision=REVISION)
    assert plan["mutationPerformed"] is False
    assert adapter.writes == []
    assert plan["scope"] == ["users.id", "users.openId", "users.role"]
    assert {"localCredentials", "passwordHash", "FusionAuth", "other-users"} <= set(plan["excluded"])

    result = runtime.account_role_apply(
        open_id=open_id, role="admin", expected_revision=REVISION,
        confirmation_sha256=plan["confirmationSha256"], owner_approved=True,
    )
    assert result["status"] == "AURION_ACCOUNT_ROLE_APPLIED_VERIFIED"
    assert result["ok"] is True
    assert result["before"] == readback["account"]
    assert result["after"] == {"id": 7, "openId": open_id, "role": "admin"}
    assert result["identityPreserved"] is True
    assert result["readbackVerified"] is True
    assert result["localCredentialsRead"] is False
    assert result["secretValuesReturned"] is False
    assert adapter.writes == [[open_id, "admin", "user"]]


@pytest.mark.parametrize("open_id", [
    "", "local:", "local:" + "a" * 33, "local:bad handle", "local:bad/handle",
    "oauth:thosu", "oidc:" + OIDC_OPEN_ID,
    "A" * 64, "a" * 63, "a" * 65, "g" * 64,
    "0123456789abcdeF" * 4, "a" * 31 + " " + "a" * 32,
])
def test_invalid_account_ids_stop_before_subprocess_adapter(open_id: str) -> None:
    adapter = AurionProcessAdapter(open_id)
    result = AurionOperatorRuntime(runner=adapter).account_role_readback(
        open_id=open_id, expected_revision=REVISION,
    )
    assert result["failureFamily"] == "AURION_ACCOUNT_ID_INVALID"
    assert result["mutationPerformed"] is False
    assert adapter.calls == []


@pytest.mark.parametrize("owner_approved,private_mode,write_enabled,family", [
    (False, "1", "1", "OWNER_APPROVAL_REQUIRED"),
    (True, "0", "1", "AURION_WRITE_DISABLED"),
    (True, "1", "0", "AURION_WRITE_DISABLED"),
])
def test_oidc_account_does_not_create_owner_or_write_authority(
    monkeypatch, owner_approved: bool, private_mode: str, write_enabled: str, family: str,
) -> None:
    adapter = AurionProcessAdapter(OIDC_OPEN_ID)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", private_mode)
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", write_enabled)
    result = AurionOperatorRuntime(runner=adapter).account_role_apply(
        open_id=OIDC_OPEN_ID, role="admin", expected_revision=REVISION,
        confirmation_sha256="e" * 64, owner_approved=owner_approved,
    )
    assert result["failureFamily"] == family
    assert adapter.calls == []


@pytest.mark.parametrize("changed", ["accountId", "currentRole", "targetAccount", "containerId", "imageId", "revision"])
def test_oidc_confirmation_cannot_replay_after_account_or_runtime_changes(monkeypatch, changed: str) -> None:
    adapter = AurionProcessAdapter(OIDC_OPEN_ID)
    runtime = AurionOperatorRuntime(runner=adapter)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", "1")
    plan = runtime.account_role_plan(open_id=OIDC_OPEN_ID, role="admin", expected_revision=REVISION)
    target_open_id = OIDC_OPEN_ID
    if changed == "accountId":
        adapter.account["id"] = 99
    elif changed == "currentRole":
        adapter.account["role"] = "admin"
    elif changed == "targetAccount":
        target_open_id = OTHER_OIDC_OPEN_ID
    elif changed == "containerId":
        adapter.container_id = "c" * 64
    elif changed == "imageId":
        adapter.image_id = "sha256:" + "d" * 64
    elif changed == "revision":
        adapter.revision = "5" * 40
    result = runtime.account_role_apply(
        open_id=target_open_id, role="admin", expected_revision=REVISION,
        confirmation_sha256=plan["confirmationSha256"], owner_approved=True,
    )
    assert result["ok"] is False
    expected_family = "AURION_RUNTIME_IDENTITY_MISMATCH" if changed == "revision" else "CONFIRMATION_MISMATCH"
    assert result["failureFamily"] == expected_family
    assert adapter.writes == []


@pytest.mark.parametrize("rows,family", [
    ([], "AURION_ACCOUNT_CARDINALITY_MISMATCH"),
    ([{"id": 7, "openId": OIDC_OPEN_ID, "role": "user"}] * 2, "AURION_ACCOUNT_CARDINALITY_MISMATCH"),
    ([{"id": 7, "openId": OTHER_OIDC_OPEN_ID, "role": "user"}], "AURION_ACCOUNT_ROW_INVALID"),
])
def test_oidc_readback_requires_one_exact_existing_row(rows: list[dict], family: str) -> None:
    adapter = AurionProcessAdapter(OIDC_OPEN_ID)
    adapter.read_rows = rows
    result = AurionOperatorRuntime(runner=adapter).account_role_plan(
        open_id=OIDC_OPEN_ID, role="admin", expected_revision=REVISION,
    )
    assert result["failureFamily"] == family
    assert adapter.writes == []


@pytest.mark.parametrize("changed", ["id", "openId", "role", "containerId", "imageId"])
def test_oidc_apply_cannot_claim_verified_without_independent_readback(monkeypatch, changed: str) -> None:
    adapter = AurionProcessAdapter(OIDC_OPEN_ID)
    runtime = AurionOperatorRuntime(runner=adapter)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", "1")
    plan = runtime.account_role_plan(open_id=OIDC_OPEN_ID, role="admin", expected_revision=REVISION)
    adapter.post_write_change = changed
    result = runtime.account_role_apply(
        open_id=OIDC_OPEN_ID, role="admin", expected_revision=REVISION,
        confirmation_sha256=plan["confirmationSha256"], owner_approved=True,
    )
    assert result["ok"] is False
    assert result["status"] == "AURION_ACCOUNT_ROLE_APPLIED_UNVERIFIED"
    assert result["failureFamily"] == "AURION_ACCOUNT_POST_WRITE_READBACK_FAILED"
    assert result["mutationPerformed"] is True
    assert result["readbackVerified"] is False


def test_oidc_apply_still_rejects_direct_broker_socket_mutation() -> None:
    result = BrokerRuntime().dispatch("aurion_account_role_apply", {
        "open_id": OIDC_OPEN_ID,
        "role": "admin",
        "expected_revision": REVISION,
        "confirmation_sha256": "e" * 64,
        "owner_approved": True,
    })
    assert result["failure_family"] == "INBOUND_MUTATION_FORBIDDEN"
