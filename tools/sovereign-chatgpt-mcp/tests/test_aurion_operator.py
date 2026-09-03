from __future__ import annotations

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
