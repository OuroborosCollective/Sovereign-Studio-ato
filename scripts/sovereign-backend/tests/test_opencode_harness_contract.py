from __future__ import annotations

from pathlib import Path
import json
import sys

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.opencode_harness_contract import (
    OPENCODE_CANARY_RECEIPT_SCHEMA,
    OX_ALPHA_OPENCODE_MODEL,
    OX_ALPHA_PROVIDER_MODEL,
    build_opencode_harness_binding,
    build_ox_alpha_harness_candidate,
)


def _route(provider_model: str = "openai/gpt-5.4-mini") -> dict:
    return {
        "id": "route-1",
        "enabled": True,
        "config": {
            "transport": "openrouter",
            "apiBase": "https://openrouter.ai/api/v1",
            "direct": True,
            "providerModel": provider_model,
            "catalogVerified": True,
            "transportCanaryVerified": True,
            "selectable": True,
            "providerPolicy": {
                "require_parameters": True,
                "allow_fallbacks": False,
                "data_collection": "deny",
                "zdr": True,
            },
        },
    }


def _receipt(provider_model: str = "openai/gpt-5.4-mini", *, tool_mutation_verified: bool = False) -> dict:
    return {
        "schemaVersion": OPENCODE_CANARY_RECEIPT_SCHEMA,
        "harness": "opencode-sdk",
        "transport": "openrouter",
        "providerModel": provider_model,
        "opencodeModel": f"openrouter/{provider_model}",
        "serverHealthy": True,
        "structuredOutputVerified": True,
        "ephemeralSandboxVerified": True,
        "sandboxProjectRemainedEmpty": True,
        "projectConfigDisabledConfigured": True,
        "toolPermissionsConfiguredDenyAll": True,
        "toolMutationVerified": tool_mutation_verified,
        "inputSha256": "1" * 64,
        "outputSha256": "2" * 64,
        "sessionIdSha256": "3" * 64,
        "opencodeVersion": "test-version",
    }


def test_structured_sdk_canary_does_not_promote_mutating_executor() -> None:
    binding = build_opencode_harness_binding(_route(), _receipt())

    assert binding["structuredCanaryVerified"] is True
    assert binding["toolMutationVerified"] is False
    assert binding["executorEligible"] is False
    assert "opencode_tool_mutation_canary_missing" in binding["blockers"]
    assert len(binding["canaryReceiptSha256"]) == 64


def test_exact_route_and_canary_model_must_match() -> None:
    binding = build_opencode_harness_binding(_route(), _receipt("anthropic/claude-sonnet-4"))

    assert binding["structuredCanaryVerified"] is False
    assert binding["executorEligible"] is False
    assert "opencode_sdk_canary_provider_model_mismatch" in binding["blockers"]


def test_structured_canary_requires_ephemeral_deny_all_sandbox_evidence() -> None:
    receipt = _receipt()
    receipt["sandboxProjectRemainedEmpty"] = False

    binding = build_opencode_harness_binding(_route(), receipt)

    assert binding["structuredCanaryVerified"] is False
    assert binding["executorEligible"] is False
    assert "opencode_sdk_sandbox_mutation_detected" in binding["blockers"]


def test_private_provider_policy_is_required_for_harness_binding() -> None:
    route = _route()
    route["config"]["providerPolicy"]["data_collection"] = "allow"

    binding = build_opencode_harness_binding(route, _receipt())

    assert binding["executorEligible"] is False
    assert "route_not_direct_verified_private_openrouter" in binding["blockers"]


def test_ox_alpha_is_a_named_candidate_but_not_invented_as_available() -> None:
    candidate = build_ox_alpha_harness_candidate(None)

    assert candidate["providerModel"] == OX_ALPHA_PROVIDER_MODEL
    assert candidate["opencodeModel"] == OX_ALPHA_OPENCODE_MODEL
    assert candidate["executorEligible"] is False
    assert candidate["blockers"] == ["ox_alpha_verified_route_missing"]


def test_ox_alpha_can_only_bind_to_the_exact_provider_model() -> None:
    binding = build_ox_alpha_harness_candidate(_route(), _receipt())

    assert binding["executorEligible"] is False
    assert "ox_alpha_provider_model_mismatch" in binding["blockers"]


def test_backend_and_deployment_opencode_contract_are_byte_identical() -> None:
    canonical = REPO_ROOT / "backend/agent_runtime/opencode_harness_contract.py"
    deployment = REPO_ROOT / "scripts/sovereign-backend/agent_runtime/opencode_harness_contract.py"

    assert canonical.read_bytes() == deployment.read_bytes()


def test_sdk_sidecar_is_pinned_and_keeps_the_openrouter_secret_out_of_source() -> None:
    package = json.loads((REPO_ROOT / "scripts/opencode-harness/package.json").read_text(encoding="utf-8"))
    source = (REPO_ROOT / "scripts/opencode-harness/src/canary.mjs").read_text(encoding="utf-8")

    assert package["dependencies"]["@opencode-ai/sdk"] == "1.18.21"
    assert package["dependencies"]["opencode-ai"] == "1.18.21"
    assert "createOpencode" in source
    assert "{file:${keyFile}}" in source
    assert "client.auth.set" not in source
    assert "readFile" not in source
    assert "SOVEREIGN_OPENCODE_WORKSPACE" not in source
    assert "mkdtemp" in source
    assert "OPENCODE_DISABLE_PROJECT_CONFIG = 'true'" in source
    assert "OPENCODE_PERMISSION = JSON.stringify({ '*': 'deny' })" in source
    assert "permission: { '*': 'deny' }" in source
    assert "sandboxProjectEntries.length !== 0" in source
    assert "toolMutationVerified: false" in source
    assert "Do not modify files, run shell commands, or perform external actions." in source
