from __future__ import annotations

import pytest

import openai_project_access_tools as access_tools


class FakeMCP:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.open_world: dict[str, bool] = {}

    def tool(self, *, annotations):
        def decorator(function):
            self.names.append(function.__name__)
            self.open_world[function.__name__] = bool(annotations.openWorldHint)
            return function

        return decorator


class FakeBroker:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls: list[tuple[str, dict, int]] = []

    def call(self, action: str, arguments: dict, timeout: int = 30) -> dict:
        self.calls.append((action, arguments, timeout))
        return self.result


class FakeController:
    def list_runs(self, limit: int = 20) -> dict:
        assert limit == 5
        return {
            "runs": [
                {
                    "run_id": "run-" + "a" * 32,
                    "status": "COMPLETED",
                    "source": "agents-sdk",
                    "next_action": "NONE",
                    "lease_active": False,
                    "updated_at": "2026-07-17T18:00:00Z",
                }
            ]
        }


def test_openai_access_plan_accepts_only_non_secret_complete_metadata() -> None:
    result = access_tools.openai_project_access_plan(
        operation="rotate",
        organization_id="org-confirmed",
        project_id="proj-confirmed",
        project_name="Sovereign Studio",
        human_owner_reference="owner:26487",
        service_account_name="sovereign-litellm-production",
        environment="production",
        target="litellm",
        permission_intent="litellm-provider",
        secret_store_reference="owner-store:openai-provider",
        required_models=["gpt-confirmed-fast", "gpt-confirmed-balanced"],
        budget_alerts=[50, 100, 250],
        rotation_days=90,
    )

    assert result["ok"] is True
    assert result["status"] == "OPENAI_ACCESS_PLAN_READY"
    assert result["record"]["serviceAccountName"] == "sovereign-litellm-production"
    assert result["ownerMutationRequired"] is True
    assert result["externalMutationPerformed"] is False
    assert result["providerPermissionVerified"] is False
    assert result["secretValuesAccepted"] is False
    assert any("second canary" in gate for gate in result["requiredGates"])


def test_openai_access_plan_reports_missing_authoritative_bindings() -> None:
    result = access_tools.openai_project_access_plan(
        operation="verify",
        project_name="Sovereign Studio",
        human_owner_reference="owner:26487",
        service_account_name="sovereign-agents-staging",
        environment="staging",
        target="agents-sdk",
        permission_intent="agents-runtime",
        secret_store_reference="owner-store:openai-provider",
        required_models=[],
        budget_alerts=[],
    )

    assert result["ok"] is False
    assert result["status"] == "OPENAI_ACCESS_PLAN_BLOCKED"
    assert "organization_id_not_yet_evidenced" in result["blockers"]
    assert "project_id_not_yet_evidenced" in result["blockers"]
    assert "required_models_not_declared" in result["blockers"]
    assert "budget_alert_thresholds_not_declared" in result["blockers"]


def test_openai_access_plan_blocks_secret_shaped_metadata() -> None:
    secret_like = "sk-" + "proj-" + "x" * 30
    with pytest.raises(ValueError, match="safe non-secret"):
        access_tools.openai_project_access_plan(
            operation="setup",
            organization_id="org-confirmed",
            project_id="proj-confirmed",
            project_name="Sovereign Studio",
            human_owner_reference="owner:26487",
            service_account_name="sovereign-mcp-production",
            environment="production",
            target="mcp",
            permission_intent="inference-only",
            secret_store_reference=secret_like,
            budget_alerts=[100],
        )


def test_runtime_evidence_aggregates_provider_and_agents_without_secret_values(monkeypatch) -> None:
    provider_runtime = {
        "ok": True,
        "status": "OPENAI_PROJECT_RUNTIME_VERIFIED",
        "projectAttributionVerified": True,
        "providerKeyValueReturned": False,
        "secretValuesExposed": False,
    }
    broker = FakeBroker(provider_runtime)
    controller = FakeController()
    monkeypatch.setattr(access_tools, "_BROKER", broker)
    monkeypatch.setattr(access_tools, "_CONTROLLER", controller)

    result = access_tools.openai_project_access_runtime_evidence()

    assert result["ok"] is True
    assert result["status"] == "OPENAI_PROJECT_ACCESS_EVIDENCE_READY"
    assert result["organizationProjectAttributionVerified"] is True
    assert result["agentsSdk"]["evidencePresent"] is True
    assert result["agentsSdk"]["latestRun"]["status"] == "COMPLETED"
    assert result["providerKeyValueReturned"] is False
    assert result["secretValuesExposed"] is False
    assert broker.calls == [("openai_project_runtime_evidence", {}, 180)]


def test_registration_exposes_only_plan_and_read_evidence(monkeypatch) -> None:
    monkeypatch.setattr(access_tools, "_REGISTERED", False)
    mcp = FakeMCP()
    access_tools.register(mcp, FakeBroker({}), FakeController())

    assert mcp.names == [
        "openai_project_access_plan",
        "openai_project_access_runtime_evidence",
    ]
    assert mcp.open_world == {
        "openai_project_access_plan": False,
        "openai_project_access_runtime_evidence": True,
    }
