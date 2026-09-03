from __future__ import annotations

from aurion_operator import AurionOperatorRuntime
from broker import BrokerRuntime
from command_contract import is_mutating_action


REVISION = "4" * 40
IMAGE_ID = "sha256:" + "a" * 64
CONTAINER_ID = "b" * 64
PROPOSAL_SHA = "c" * 64


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
    account = {"id": 7, "openId": "local:thosu", "role": role}
    return {
        "ok": True,
        "status": "AURION_ACCOUNT_ROLE_READBACK_VERIFIED",
        "runtimeIdentity": runtime_identity(),
        "account": account,
        "readbackSha256": "d" * 64,
        "readbackVerified": True,
        "localCredentialsRead": False,
        "mutationPerformed": False,
        "secretValuesReturned": False,
    }


def test_account_role_plan_is_bounded_to_one_local_users_row(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setattr(runtime, "account_role_readback", lambda **kwargs: account_readback("user"))

    result = runtime.account_role_plan(open_id="local:thosu", role="admin", expected_revision=REVISION)

    assert result["ok"] is True
    assert result["status"] == "AURION_ACCOUNT_ROLE_PLAN_READY"
    assert result["account"] == {"id": 7, "openId": "local:thosu", "role": "user"}
    assert result["requestedRole"] == "admin"
    assert len(result["confirmationSha256"]) == 64
    assert "localCredentials" in result["excluded"]
    assert result["mutationPerformed"] is False
    assert result["secretValuesReturned"] is False


def test_account_role_readback_rejects_non_local_identity_before_db_helper(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setattr(runtime, "runtime_identity", lambda expected_revision: runtime_identity())
    monkeypatch.setattr(
        runtime,
        "_exec_node_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DB helper must not execute")),
    )

    result = runtime.account_role_readback(open_id="oauth:thosu", expected_revision=REVISION)

    assert result["ok"] is False
    assert result["failureFamily"] == "AURION_ACCOUNT_ID_INVALID"


def test_account_role_apply_requires_owner_and_write_gate(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.delenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", raising=False)
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", raising=False)

    blocked_owner = runtime.account_role_apply(
        open_id="local:thosu",
        role="admin",
        expected_revision=REVISION,
        confirmation_sha256="e" * 64,
        owner_approved=False,
    )
    blocked_write = runtime.account_role_apply(
        open_id="local:thosu",
        role="admin",
        expected_revision=REVISION,
        confirmation_sha256="e" * 64,
        owner_approved=True,
    )

    assert blocked_owner["failureFamily"] == "OWNER_APPROVAL_REQUIRED"
    assert blocked_write["failureFamily"] == "AURION_WRITE_DISABLED"


def test_account_role_apply_replans_and_requires_post_write_readback(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", "1")
    plan = {
        "ok": True,
        "status": "AURION_ACCOUNT_ROLE_PLAN_READY",
        "runtimeIdentity": runtime_identity(),
        "account": {"id": 7, "openId": "local:thosu", "role": "user"},
        "requestedRole": "admin",
        "confirmationSha256": "e" * 64,
    }
    monkeypatch.setattr(runtime, "account_role_plan", lambda **kwargs: plan)
    monkeypatch.setattr(runtime, "runtime_identity", lambda expected_revision: runtime_identity())
    monkeypatch.setattr(runtime, "account_role_readback", lambda **kwargs: account_readback("admin"))
    monkeypatch.setattr(
        runtime,
        "_exec_node_json",
        lambda *args, **kwargs: {
            "ok": True,
            "status": "AURION_DB_RESPONSE_READY",
            "payload": {
                "before": {"id": 7, "openId": "local:thosu", "role": "user"},
                "after": {"id": 7, "openId": "local:thosu", "role": "admin"},
                "mutationPerformed": True,
            },
        },
    )

    result = runtime.account_role_apply(
        open_id="local:thosu",
        role="admin",
        expected_revision=REVISION,
        confirmation_sha256="e" * 64,
        owner_approved=True,
    )

    assert result["ok"] is True
    assert result["status"] == "AURION_ACCOUNT_ROLE_APPLIED_VERIFIED"
    assert result["after"]["role"] == "admin"
    assert result["identityPreserved"] is True
    assert result["readbackVerified"] is True
    assert result["localCredentialsRead"] is False
    assert result["mutationPerformed"] is True


def test_genkit_config_rejects_arbitrary_remote_host(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setenv("SOVEREIGN_AURION_GENKIT_BASE_URL", "https://evil.example/api")
    monkeypatch.setattr(runtime, "runtime_identity", lambda expected_revision: runtime_identity())

    result = runtime.genkit_status(expected_revision=REVISION)

    assert result["ok"] is False
    assert result["failureFamily"] == "AURION_GENKIT_CONFIG_INVALID"


def test_genkit_proposal_requires_proposal_hash_and_exact_revision(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setattr(runtime, "runtime_identity", lambda expected_revision: runtime_identity())
    monkeypatch.setattr(
        runtime,
        "_genkit_config",
        lambda: {"configured": True, "proposalPath": "/internal/genkit/propose"},
    )
    monkeypatch.setattr(
        runtime,
        "_genkit_request",
        lambda method, path, payload=None: {
            "ok": True,
            "httpStatus": 200,
            "response": {
                "sourceRevision": REVISION,
                "proposalSha256": PROPOSAL_SHA,
                "proposal": {"kind": "world-design", "summary": "add a lantern"},
                "mutationPerformed": False,
            },
            "responseSha256": "f" * 64,
            "authConfigured": True,
        },
    )

    result = runtime.genkit_propose(
        intent="Setze eine Laterne an den Weg, aber nur als Vorschlag.",
        expected_revision=REVISION,
        context={"zone": "observatory_threshold"},
    )

    assert result["ok"] is True
    assert result["status"] == "AURION_GENKIT_PROPOSAL_VERIFIED"
    assert result["proposalSha256"] == PROPOSAL_SHA
    assert result["revisionBound"] is True
    assert result["worldMutationClaimed"] is False
    assert result["mutationPerformed"] is False


def test_genkit_apply_requires_receipt_target_readback_and_preserved_runtime(monkeypatch) -> None:
    runtime = AurionOperatorRuntime()
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_GENKIT_WRITE", "1")
    monkeypatch.setattr(runtime, "runtime_identity", lambda expected_revision: runtime_identity())
    monkeypatch.setattr(
        runtime,
        "_genkit_config",
        lambda: {"configured": True, "applyPath": "/internal/genkit/apply"},
    )
    plan = runtime.genkit_apply_plan(proposal_sha256=PROPOSAL_SHA, expected_revision=REVISION)
    assert plan["ok"] is True
    monkeypatch.setattr(
        runtime,
        "_genkit_request",
        lambda method, path, payload=None: {
            "ok": True,
            "httpStatus": 200,
            "response": {
                "sourceRevision": REVISION,
                "applied": True,
                "receipt": {"proposalSha256": PROPOSAL_SHA, "effect": "world-design"},
                "targetReadback": {"zone": "observatory_threshold", "objectCount": 1},
                "targetReadbackVerified": True,
            },
            "responseSha256": "1" * 64,
            "authConfigured": True,
        },
    )

    result = runtime.genkit_apply(
        proposal_sha256=PROPOSAL_SHA,
        expected_revision=REVISION,
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert result["ok"] is True
    assert result["status"] == "AURION_GENKIT_APPLIED_VERIFIED"
    assert result["readbackVerified"] is True
    assert result["identityPreserved"] is True
    assert result["receiptSha256"]
    assert result["targetReadbackSha256"]
    assert result["mutationPerformed"] is True


def test_aurion_mutations_are_host_queue_actions_and_owner_intersection_is_preserved(monkeypatch) -> None:
    assert is_mutating_action("aurion_account_role_apply")
    assert is_mutating_action("aurion_genkit_apply")
    runtime = BrokerRuntime()
    approvals: list[bool] = []

    def apply(**kwargs):
        approvals.append(bool(kwargs["owner_approved"]))
        return {"ok": bool(kwargs["owner_approved"]), "status": "AURION_TEST"}

    monkeypatch.setattr(runtime.aurion, "account_role_apply", apply)
    arguments = {
        "open_id": "local:thosu",
        "role": "admin",
        "expected_revision": REVISION,
        "confirmation_sha256": "e" * 64,
        "owner_approved": True,
    }

    runtime.private_owner_mode = False
    runtime.dispatch("aurion_account_role_apply", arguments, execution_origin="host_worker")
    runtime.private_owner_mode = True
    runtime.dispatch("aurion_account_role_apply", arguments, execution_origin="host_worker")

    assert approvals == [False, True]
