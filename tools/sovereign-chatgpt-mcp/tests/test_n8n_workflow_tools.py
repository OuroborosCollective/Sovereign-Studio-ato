from __future__ import annotations

import inspect
from types import NoneType
from typing import Any, get_args, get_type_hints

import pytest

import n8n_workflow_tools as workflow_tools
from command_contract import standing_owner_delegation_approved
from n8n_workflow_runtime import CIEvidenceWatchSpec


class FakeMCP:
    def __init__(self) -> None:
        self.registered: list[tuple[Any, Any]] = []

    def tool(self, *, annotations: Any):
        def decorator(function: Any) -> Any:
            self.registered.append((function, annotations))
            return function

        return decorator


class FakeBroker:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any], int]] = []

    def call(
        self,
        action: str,
        arguments: dict[str, Any],
        timeout: int = 30,
    ) -> dict[str, Any]:
        self.calls.append((action, arguments, timeout))
        return self.result


def _registered(
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, Any] | None = None,
) -> tuple[FakeMCP, FakeBroker]:
    monkeypatch.setattr(workflow_tools, "_REGISTERED", False)
    mcp = FakeMCP()
    broker = FakeBroker(result or {"ok": True, "status": "TEST_RESULT"})
    workflow_tools.register(mcp, broker)
    return mcp, broker


def test_registration_exposes_exactly_plan_and_apply_with_effect_annotations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp, _ = _registered(monkeypatch)

    assert [function.__name__ for function, _ in mcp.registered] == [
        "n8n_workflow_plan",
        "n8n_workflow_apply",
    ]
    assert len(mcp.registered) == 2

    plan_annotations = mcp.registered[0][1]
    assert plan_annotations.readOnlyHint is True
    assert plan_annotations.destructiveHint is False
    assert plan_annotations.idempotentHint is True
    assert plan_annotations.openWorldHint is False

    apply_annotations = mcp.registered[1][1]
    assert apply_annotations.readOnlyHint is False
    assert apply_annotations.destructiveHint is True
    assert apply_annotations.idempotentHint is False
    assert apply_annotations.openWorldHint is True

    public_names = {function.__name__ for function, _ in mcp.registered}
    assert not any(
        forbidden in name
        for name in public_names
        for forbidden in ("delete", "credential", "test")
    )


def test_public_schema_is_lane_operation_and_spec_allowlisted() -> None:
    plan_hints = get_type_hints(workflow_tools.n8n_workflow_plan)
    apply_hints = get_type_hints(workflow_tools.n8n_workflow_apply)

    assert get_args(plan_hints["lane_id"]) == ("sovereign", "aurion")
    assert get_args(plan_hints["operation"]) == (
        "inventory",
        "create_draft",
        "update_draft",
        "activate",
        "pause",
    )
    assert set(get_args(plan_hints["spec"])) == {
        CIEvidenceWatchSpec,
        NoneType,
    }

    assert apply_hints["lane_id"] == plan_hints["lane_id"]
    assert apply_hints["operation"] == plan_hints["operation"]
    assert set(get_args(apply_hints["spec"])) == {
        CIEvidenceWatchSpec,
        NoneType,
    }
    assert apply_hints["confirmation_sha256"] is str
    assert apply_hints["owner_approved"] is bool

    apply_parameters = inspect.signature(
        workflow_tools.n8n_workflow_apply
    ).parameters
    assert apply_parameters["confirmation_sha256"].default is inspect.Parameter.empty
    assert apply_parameters["owner_approved"].default is inspect.Parameter.empty
    assert set(apply_parameters) == {
        "lane_id",
        "operation",
        "confirmation_sha256",
        "owner_approved",
        "workflow_id",
        "spec",
    }


def test_apply_description_declares_standing_delegation_not_one_time_receipt() -> None:
    description = inspect.getdoc(workflow_tools.n8n_workflow_apply) or ""

    assert "standing private-owner delegation" in description
    assert "not an independently issued or one-time approval receipt" in description


def test_standing_owner_delegation_intersects_server_mode_and_caller_attestation() -> None:
    assert standing_owner_delegation_approved(
        private_owner_mode=False,
        caller_attestation=True,
    ) is False
    assert standing_owner_delegation_approved(
        private_owner_mode=True,
        caller_attestation=False,
    ) is False
    assert standing_owner_delegation_approved(
        private_owner_mode=True,
        caller_attestation=True,
    ) is True


def test_plan_forwards_exact_typed_payload_to_read_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, broker = _registered(
        monkeypatch,
        {"ok": True, "status": "N8N_WORKFLOW_PLAN_READY"},
    )
    spec = CIEvidenceWatchSpec.model_construct()

    result = workflow_tools.n8n_workflow_plan(
        lane_id="sovereign",
        operation="create_draft",
        spec=spec,
    )

    assert result == {"ok": True, "status": "N8N_WORKFLOW_PLAN_READY"}
    assert broker.calls == [
        (
            "n8n_workflow_plan",
            {
                "lane_id": "sovereign",
                "operation": "create_draft",
                "workflow_id": None,
                "spec": spec.model_dump(mode="json"),
            },
            60,
        )
    ]


def test_apply_forwards_confirmation_and_explicit_owner_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, broker = _registered(
        monkeypatch,
        {"ok": True, "status": "N8N_WORKFLOW_APPLIED"},
    )
    spec = CIEvidenceWatchSpec.model_construct()
    confirmation_sha256 = "a" * 64

    result = workflow_tools.n8n_workflow_apply(
        lane_id="aurion",
        operation="update_draft",
        workflow_id="workflow-17",
        spec=spec,
        confirmation_sha256=confirmation_sha256,
        owner_approved=True,
    )

    assert result == {"ok": True, "status": "N8N_WORKFLOW_APPLIED"}
    assert broker.calls == [
        (
            "n8n_workflow_apply",
            {
                "lane_id": "aurion",
                "operation": "update_draft",
                "workflow_id": "workflow-17",
                "spec": spec.model_dump(mode="json"),
                "confirmation_sha256": confirmation_sha256,
                "owner_approved": True,
            },
            180,
        )
    ]


def test_only_apply_enters_the_host_mutation_queue() -> None:
    from command_contract import is_mutating_action

    assert is_mutating_action("n8n_workflow_apply") is True
    assert is_mutating_action("n8n_workflow_plan") is False
