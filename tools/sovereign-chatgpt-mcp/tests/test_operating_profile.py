from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import continuity
import launcher
import operating_profile



def _registered_tools() -> dict[str, object]:
    return {tool.name: tool for tool in launcher.mcp._tool_manager.list_tools()}



def test_profile_is_loaded_registered_and_enforced_for_every_mutable_tool() -> None:
    status = operating_profile.sovereign_operating_profile_status()
    profile, _profile_sha256 = operating_profile._load_profile()
    report = launcher.OPERATING_PROFILE_ENFORCEMENT
    tools = _registered_tools()

    assert status.ok is True
    assert status.status == "OPERATING_PROFILE_ENFORCED"
    assert status.profileId == "sovereign-mcp-optimal-operation"
    assert status.profileVersion == "1.1.2"
    assert status.invariants["continuityReadRequiredBeforeMutation"] is False
    assert status.invariants["continuityLedgerRequiredBeforeRepositoryFinalization"] is False
    assert len(status.profileSha256) == 64
    assert len(status.registrySnapshotSha256) == 64
    assert status.missingGovernanceTools == []
    assert status.forbiddenToolsPresent == []
    assert status.toolsWithoutOutputSchema == []
    assert status.unenforcedMutableTools == []
    assert report.ok is True
    assert report.enforcedToolCount == report.mutableToolCount
    assert status.enforcedToolCount == status.mutableToolCount
    assert profile["routeIsolation"]["freeRoute"] == "FreeLLM direct transport only"
    assert profile["routeIsolation"]["paidRoute"] == "Paid OpenRouter direct transport only"
    assert profile["routeIsolation"]["legacyLiteLLMTransportAllowed"] is False
    assert "sovereign_continuity_context_read" in tools
    assert "sovereign_continuity_status" in tools
    assert "sovereign_operating_profile_status" in tools
    assert "sovereign_mission_preflight" in tools

    for tool in tools.values():
        if tool.annotations.readOnlyHint:
            continue
        assert tool.meta["sovereign/operatingProfileEnforced"] is True
        assert getattr(tool.fn, "__sovereign_operating_profile_wrapped__", False) is True



def test_read_only_mission_preflight_compiles_and_validates_live_contracts() -> None:
    result = operating_profile.sovereign_mission_preflight(
        mission_summary="Inspect the live MCP registry and prove its current contract snapshot.",
        required_capabilities=["mcp"],
        allowed_effects=["read"],
        required_evidence=["registry", "output schema", "contract hash"],
        max_nodes=4,
    )

    assert result.ok is True
    assert result.status == "MISSION_PREFLIGHT_VALID"
    assert result.selectedTools
    assert result.proposal["proposal"]["initial_pipeline"]["auto_execute"] is False
    assert result.validation["status"] == "MCP_TOOLCHAIN_VALID"
    assert result.mutationPerformed is False
    assert result.secretValuesReturned is False



def test_mutating_mission_preflight_does_not_depend_on_continuity_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(continuity, "_READ_STATE", None)

    result = operating_profile.sovereign_mission_preflight(
        mission_summary="Prepare an isolated repository workspace for a revision-bound code repair.",
        required_capabilities=["repository"],
        allowed_effects=["workspace-write"],
        required_evidence=["exact revision"],
        max_nodes=4,
    )

    assert result.status != "MISSION_PREFLIGHT_BLOCKED_BY_OPERATING_PROFILE"
    assert all(not str(item.get("family") or "").startswith("CONTINUITY_") for item in result.findings)


def test_argument_gate_requires_owner_revision_confirmation_and_blocks_secret_shapes() -> None:
    parameters = {
        "type": "object",
        "properties": {
            "owner_approved": {"type": "boolean"},
            "expected_head_sha": {"type": "string"},
            "confirmation_sha256": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["expected_head_sha", "confirmation_sha256"],
    }
    findings = operating_profile._validate_invocation_arguments(
        "example_external_write",
        "external-write",
        parameters,
        {
            "owner_approved": False,
            "expected_head_sha": "not-a-sha",
            "confirmation_sha256": "",
            "body": "secret sk-abcdefghijklmnopqrstuvwx",
        },
    )
    families = {item["family"] for item in findings}
    assert families == {
        "OPERATING_PROFILE_OWNER_APPROVAL_REQUIRED",
        "OPERATING_PROFILE_EXACT_REVISION_INVALID",
        "OPERATING_PROFILE_CONFIRMATION_MISSING",
        "OPERATING_PROFILE_SECRET_SHAPED_ARGUMENT_BLOCKED",
    }


@pytest.mark.parametrize(
    "key",
    [
        "access_token",
        "provider_api_key",
        "client_secret_value",
        "githubToken",
        "databasePassword",
        "client_secret_value_data",
        "access_token_raw_value",
        "provider_api_key_material_bytes",
        "database_password_text_string",
        "authorization_header",
        "auth_header",
        "session_cookie",
        "client_secret_json",
        "access_token_payload",
    ],
)
def test_shared_secret_gate_blocks_secret_shaped_mapping_keys(key: str) -> None:
    arguments = {key: "opaque-protected-value"}
    assert operating_profile._contains_secret_shaped_value(arguments) is True
    findings = operating_profile._validate_invocation_arguments(
        "example_workspace_write",
        "workspace-write",
        {"type": "object", "properties": {key: {"type": "string"}}},
        arguments,
    )
    assert {item["family"] for item in findings} == {
        "OPERATING_PROFILE_SECRET_SHAPED_ARGUMENT_BLOCKED"
    }


def test_repository_source_mutation_allows_identifier_text_but_blocks_concrete_secret_literals() -> None:
    source_identifier_text = "to" + "ken = os.getenv('PROTECTED_VALUE_NAME')"
    source_findings = operating_profile._validate_invocation_arguments(
        "repository_apply_search_replace",
        "workspace-write",
        {"type": "object", "properties": {"blocks": {"type": "array"}}},
        {"blocks": [{"search": "before", "replace": source_identifier_text}]},
    )
    assert "OPERATING_PROFILE_SECRET_SHAPED_ARGUMENT_BLOCKED" not in {
        item["family"] for item in source_findings
    }

    concrete_literal = "gh" + "p_" + ("a" * 24)
    literal_findings = operating_profile._validate_invocation_arguments(
        "repository_apply_search_replace",
        "workspace-write",
        {"type": "object", "properties": {"blocks": {"type": "array"}}},
        {"blocks": [{"search": "before", "replace": concrete_literal}]},
    )
    assert "OPERATING_PROFILE_SECRET_SHAPED_ARGUMENT_BLOCKED" in {
        item["family"] for item in literal_findings
    }


def test_shared_secret_gate_preserves_counters_and_false_no_secret_attestations() -> None:
    assert operating_profile._contains_secret_shaped_value(
        {
            "inputTokens": 12,
            "token_count": 12,
            "argumentValuesRecorded": False,
            "secretValuesRecorded": False,
            "secretValuesReturned": False,
        }
    ) is False
    assert operating_profile._contains_secret_shaped_value(
        {"secretValuesReturned": True}
    ) is True


@pytest.mark.parametrize(
    "literal",
    [
        "Authorization: Basic dXNlcjpwYXNzd29yZA==",
        "client_secret=protected-value",
        "access_token=protected-value",
        "Cookie: session=protected-value",
        "Set-Cookie: session=protected-value",
        "https://user:protected-value@example.invalid/path",
    ],
)
def test_shared_secret_gate_blocks_protected_string_literals(literal: str) -> None:
    assert operating_profile._contains_secret_shaped_value({"note": literal}) is True



def test_real_mutation_wrapper_blocks_before_broker_execution() -> None:
    merge_tool = _registered_tools()["repository_merge_pr"]
    with pytest.raises(operating_profile.OperatingProfileBlocked) as exc_info:
        merge_tool.fn(
            pr_number=1,
            expected_head_sha="a" * 40,
            merge_method="squash",
            self_update_after_merge=True,
            owner_approved=False,
            mark_ready_if_draft=False,
            allow_unrelated_android_pending=False,
        )

    payload = json.loads(str(exc_info.value))
    assert payload["status"] == "MUTATION_BLOCKED_BY_OPERATING_PROFILE"
    assert payload["failureFamily"] == "OPERATING_PROFILE_OWNER_APPROVAL_REQUIRED"
    assert payload["tool"] == "repository_merge_pr"
    assert payload["mutationPerformed"] is False
    assert payload["secretValuesReturned"] is False



def test_ci_and_vps_release_contract_require_live_profile_and_negative_canary() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")
    assert isinstance(yaml.safe_load(workflow), dict)
    installer = (Path(__file__).resolve().parents[1] / "deploy" / "install-on-vps.sh").read_text("utf-8")

    assert "operating_profile.py" in workflow
    assert "continuity.py" in workflow
    assert "config/sovereign-mcp-operating-profile.json" in workflow
    assert "config/sovereign-continuity-policy.json" in workflow
    assert "continuity-data/CONTEXT.md" in workflow
    assert "continuity-data/LEDGER.jsonl" in workflow
    assert "assert continuity_read.status == 'CONTINUITY_CONTEXT_BOUND'" not in workflow
    assert "Continuity provenance is advisory and is not a validation or release gate." in workflow
    assert "skills/sovereign-mcp-optimal-operation/SKILL.md" in workflow
    assert "OPERATING_PROFILE_ENFORCEMENT" in workflow
    assert "OPERATING_PROFILE_ENFORCED" in workflow
    assert "operating_profile_enforced" in workflow
    assert "negativeMutationCanary" not in workflow
    assert "operating_profile.py" in installer
    assert "continuity.py" in installer
    assert "/app/config/sovereign-mcp-operating-profile.json" in installer
    assert "/app/config/sovereign-continuity-policy.json" in installer
    assert "/app/continuity-data/CONTEXT.md" in installer
    assert "/app/continuity-data/LEDGER.jsonl" in installer
    assert "/app/skills/sovereign-mcp-optimal-operation/SKILL.md" in installer
    assert "OPERATING_PROFILE_ENFORCED" in installer
    assert "INSTALL_STAGE=\"verify_operating_profile_canaries\"" in installer
    assert "CONTINUITY_ADVISORY_UNAVAILABLE" in installer
    assert "continuity_enforced" not in installer
    assert '"continuity_advisory":true' in installer
    assert "MISSION_PREFLIGHT_VALID" in installer
    assert "MUTATION_BLOCKED_BY_OPERATING_PROFILE" in installer
    assert "OPERATING_PROFILE_OWNER_APPROVAL_REQUIRED" in installer
    assert "negativeMutationCanary" in installer
    assert installer.count("INSTALL_STAGE=\"verify_operating_profile_canaries\"") == 1
    assert installer.count("negativeMutationCanary") == 1
