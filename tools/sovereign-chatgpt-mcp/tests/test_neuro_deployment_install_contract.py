from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from jsonschema import Draft202012Validator
import yaml


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
INSTALLER = ROOT / "deploy" / "install-on-vps.sh"
WORKFLOW = REPOSITORY / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml"
REMOTE_INSTALL = (
    ROOT / "deploy" / "install-and-verify-private-mcp-on-vps.sh"
)


EXPECTED_NEURO_TOOLS = {
    "neuro_event_commit",
    "neuro_event_route_preview",
    "neuro_runtime_contract_status",
    "teaching_lesson_simulate",
    "teaching_package_assess",
}

EXPECTED_COMPATIBLE_PREDECESSOR_DRIFT = {
    "mcp_diagnostic_chain_plan",
    "mcp_toolchain_compile",
    "runtime_runbook_generate",
    "sovereign_mission_preflight",
    "tool_recommend_for_mission",
}

# Deterministic fixture for the currently accepted predecessor contract surface.
# The installer still verifies the real deployed predecessor independently at runtime.
BASELINE_PREDECESSOR_SEMANTIC_SHA256 = (
    "9398f21e81234a30eeb8159e772bdca64a47417ce495e8d98d2a05bb13e54c11"
)


def test_launcher_preserves_every_existing_registration_and_adds_one_teacher_registration() -> None:
    launcher = (ROOT / "launcher.py").read_text("utf-8")
    tree = ast.parse(launcher)
    registrations: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        function = node.value.func
        if (
            isinstance(function, ast.Attribute)
            and function.attr == "register"
            and isinstance(function.value, ast.Name)
        ):
            registrations.append(function.value.id)

    assert registrations == [
        "database_evidence_tools",
        "deterministic_architecture_tools",
        "enterprise_backend_tools",
        "freemium_product_architect_tools",
        "tool_extensions",
        "repository_skill_tools",
        "repository_intelligence_tools",
        "skill_supply_chain_tools",
        "openai_project_access_tools",
        "operational_governance_tools",
        "neuro_teaching_tools",
        "operational_assurance_tools",
        "proven_learning_tools",
        "toolchain_composition",
        "continuity",
        "operating_profile",
    ]
    assert launcher.count("neuro_teaching_tools.register(server.mcp, server.runtime)") == 1


def test_teacher_register_function_exposes_exactly_five_additive_tools() -> None:
    source = (ROOT / "neuro_teaching_tools.py").read_text("utf-8")
    tree = ast.parse(source)
    register = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "register"
    )
    registered: list[str] = []
    for node in ast.walk(register):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Call):
            continue
        decorator = node.func
        if not (
            isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "mcp"
            and decorator.func.attr == "tool"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
        ):
            continue
        registered.append(node.args[0].id)

    assert set(registered) == EXPECTED_NEURO_TOOLS
    assert len(registered) == 5


def test_compose_reuses_the_existing_service_port_network_and_bounded_state_volume() -> None:
    compose_path = ROOT / "docker-compose.yml"
    compose_text = compose_path.read_text("utf-8")
    compose = yaml.safe_load(compose_text)

    assert set(compose["services"]) == {"sovereign-chatgpt-mcp"}
    service = compose["services"]["sovereign-chatgpt-mcp"]
    assert service["ports"] == ["127.0.0.1:8090:8090"]
    assert service["networks"] == ["supabase_default"]
    assert "/opt/sovereign-chatgpt-tools/tool-routing-state:/var/lib/sovereign-tool-routing" in service["volumes"]
    assert service["environment"]["SOVEREIGN_NEURO_RUNTIME_STATE_ROOT"] == "/var/lib/sovereign-tool-routing/neuro-runtime"
    assert str(service["environment"]["SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED"]) == "1"
    assert str(service["environment"]["SOVEREIGN_NEURO_GLOBAL_MAX_EVENTS"]) == "100000"
    assert str(service["environment"]["SOVEREIGN_NEURO_GLOBAL_MAX_BYTES"]) == "268435456"
    assert str(service["environment"]["SOVEREIGN_NEURO_OUTCOME_MAX_EVENTS"]) == "90000"
    assert str(service["environment"]["SOVEREIGN_NEURO_OUTCOME_MAX_BYTES"]) == "268435456"
    assert compose_text.count("SOVEREIGN_NEURO_RUNTIME_STATE_ROOT:") == 1
    assert "/var/run/docker.sock" not in compose_text


def test_installer_binds_revision_policy_permissions_and_preserves_predecessor_surface(
    tmp_path: Path,
) -> None:
    script = INSTALLER.read_text("utf-8")
    syntax = subprocess.run(
        ["bash", "-n", str(INSTALLER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    assert 'NEURO_RUNTIME_STATE_HOST_DIR="$INSTALL_ROOT/tool-routing-state/neuro-runtime"' in script
    assert 'install -d -m 0700 -o "$MCP_UID" -g "$MCP_GID" "$NEURO_RUNTIME_STATE_HOST_DIR"' in script
    assert '[[ -d "$NEURO_RUNTIME_STATE_HOST_DIR" && ! -L "$NEURO_RUNTIME_STATE_HOST_DIR" ]]' in script
    assert 'chmod 0700 "$NEURO_RUNTIME_STATE_HOST_DIR"' in script
    assert 'set_value "$MANAGED_ENV" SOVEREIGN_SOURCE_REVISION "$EXPECTED_REVISION"' in script
    assert 'set_value "$MANAGED_ENV" SOVEREIGN_NEURO_POLICY_SHA256 "$NEURO_POLICY_SHA256"' in script
    assert script.index('set_value "$MANAGED_ENV" SOVEREIGN_SOURCE_REVISION') < script.index(
        'docker compose up -d --no-build --force-recreate --remove-orphans'
    )
    assert script.index('set_value "$MANAGED_ENV" SOVEREIGN_NEURO_POLICY_SHA256') < script.index(
        'docker compose up -d --no-build --force-recreate --remove-orphans'
    )

    assert 'EXPECTED_MCP_TOOL_COUNT="249"' in script
    assert 'INSTALL_STAGE="capture_previous_mcp_tool_surface"' in script
    assert 'INSTALL_STAGE="verify_mcp_tool_surface_preservation"' in script
    assert "mcp_tool_contract_registry(include_schemas=True)" in script
    assert '"schemaVersion": "sovereign.mcp-deployment-contract-surface.v1"' in script
    assert '"changedCompatibleContracts": changed_compatible_contracts' in script
    assert '"incompatibleContractCount": len(incompatible_contracts)' in script
    assert '"semanticCompatibilityVerified": predecessor_captured' in script
    assert "SOVEREIGN_MCP_ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR" in script
    assert '"attested-first-install-no-predecessor"' in script
    assert "--pull never" in script
    assert "--no-healthcheck" in script
    assert "--network none" in script
    assert "--read-only" in script
    assert "--user 10001:10001" in script
    assert "--cap-drop ALL" in script
    assert "--security-opt no-new-privileges" in script
    assert "timeout --signal=TERM --kill-after=10s 120s" in script
    assert 'PREVIOUS_MCP_INTROSPECTION_CONTAINER="sovereign-mcp-predecessor-introspection-$$"' in script
    assert 'docker rm -f "$PREVIOUS_MCP_INTROSPECTION_CONTAINER"' in script
    assert 'bounded predecessor introspection container was not cleaned' in script
    assert '[[ "$PREVIOUS_MCP_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]' in script
    assert 'predecessor MCP existed but registry capture was not verified' in script
    assert 'MCP_SURFACE_ADVISORY_FILE="$ROLLBACK_DIR/mcp-tool-surface-advisory.err"' in script
    assert 'PREDECESSOR_SEMANTIC_COMPATIBILITY_VERIFIED=0' in script
    assert 'SOVEREIGN_MCP_TOOL_SURFACE_ADVISORY:%s' in script
    assert '"semantic_compatibility_verified":%s' in script
    assert '"semantic_compatibility_blocking":false' in script
    assert '"first_install_attested":%s' in script
    assert "if not old_capabilities <= new_capabilities:" in script
    assert 'canonical(old["effect"]) != canonical(new["effect"])' in script
    assert 'canonical(old["annotations"]) != canonical(new["annotations"])' in script
    assert 'old["parameters"],\n                new["parameters"]' in script
    assert "allow_input_enum_widening=True" in script
    assert 'new["outputSchema"],\n                old["outputSchema"]' in script
    assert "allow_input_enum_widening=False" in script
    assert 'canonical(old["description"]) != canonical(new["description"])' in script
    assert script.index('INSTALL_STAGE="capture_previous_mcp_tool_surface"') < script.index(
        "docker rm -f sovereign-chatgpt-mcp"
    )
    assert 'replacement MCP removed predecessor tools' in script
    assert '244-tool predecessor did not receive exactly the five approved additions' in script
    assert "previous_count = 0\nadditions = []" in script
    assert "changed_compatible_contracts: list[str] = []" in script
    assert "incompatible_contracts: list[dict[str, Any]] = []" in script
    assert "if predecessor_captured:" in script
    assert script.index('PREVIOUS_MCP_IMAGE_DIGEST="$(read_mcp_value SOVEREIGN_MCP_IMAGE') < script.index(
        "ROLLBACK_ARMED=1"
    )
    assert 'set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$PREVIOUS_MCP_IMAGE_DIGEST"' in script
    assert script.index('INSTALL_STAGE="verify_mcp_tool_surface_preservation"') < script.rindex(
        "ROLLBACK_ARMED=0"
    )
    for tool_name in EXPECTED_NEURO_TOOLS:
        assert f'"{tool_name}"' in script

    capture_section = script.split('INSTALL_STAGE="capture_previous_mcp_tool_surface"', 1)[1].split(
        'INSTALL_STAGE="replace_mcp_container"', 1
    )[0]
    assert "--volume" not in capture_section
    assert " -v " not in capture_section
    resolver_start = script.index("resolve_previous_mcp_registry_capture_mode() {")
    resolver_end = script.index("\nclassify_mcp_image_pull_failure()", resolver_start)
    resolver = script[resolver_start:resolver_end]
    resolver_harness = f"""
set -Eeuo pipefail
fail() {{ printf '%s\\n' "$*" >&2; exit 1; }}
docker() {{
  if [[ "$1" == "container" && "$2" == "ls" ]]; then
    [[ "${{MOCK_DISCOVERY_FAILURE:-0}}" != "1" ]] || return 70
    printf '%s' "${{MOCK_CONTAINER_NAMES:-}}"
    return 0
  fi
  if [[ "$1" == "container" && "$2" == "inspect" ]]; then
    printf '%s\\n' "${{MOCK_RUNNING_STATE:-}}"
    return 0
  fi
  return 71
}}
{resolver}
resolve_previous_mcp_registry_capture_mode
"""

    def resolved_capture_mode(
        *, container_names: str, running_state: str, first_install_attested: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", resolver_harness],
            env={
                **os.environ,
                "MOCK_CONTAINER_NAMES": container_names,
                "MOCK_RUNNING_STATE": running_state,
                "ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR": first_install_attested,
            },
            capture_output=True,
            text=True,
            check=False,
        )

    unhealthy_running = resolved_capture_mode(
        container_names="sovereign-chatgpt-mcp",
        running_state="true",
        first_install_attested="0",
    )
    assert unhealthy_running.returncode == 0, unhealthy_running.stderr
    assert unhealthy_running.stdout.strip() == "running-container"
    stopped = resolved_capture_mode(
        container_names="sovereign-chatgpt-mcp",
        running_state="false",
        first_install_attested="0",
    )
    assert stopped.returncode == 0, stopped.stderr
    assert stopped.stdout.strip() == "immutable-image-offline"
    unattested_absence = resolved_capture_mode(
        container_names="",
        running_state="",
        first_install_attested="0",
    )
    assert unattested_absence.returncode != 0
    assert "explicit first-install attestation is required" in unattested_absence.stderr
    attested_absence = resolved_capture_mode(
        container_names="",
        running_state="",
        first_install_attested="1",
    )
    assert attested_absence.returncode == 0, attested_absence.stderr
    assert attested_absence.stdout.strip() == "attested-first-install-no-predecessor"

    capture_marker = (
        'if ! "${PREVIOUS_MCP_REGISTRY_CAPTURE_COMMAND[@]}" <<\'PY\' '
        '> "$PREVIOUS_MCP_REGISTRY_FILE"\n'
    )
    capture_program = script.split(capture_marker, 1)[1].split("\nPY\n  then", 1)[0]
    legacy_module_root = tmp_path / "legacy-fastmcp"
    legacy_module_root.mkdir()
    (legacy_module_root / "launcher.py").write_text(
        textwrap.dedent(
            """
            from types import SimpleNamespace

            class ToolManager:
                def list_tools(self):
                    return [
                        SimpleNamespace(
                            name="workspace_prepare",
                            description="Create an isolated repository workspace.",
                            annotations=SimpleNamespace(
                                readOnlyHint=False,
                                destructiveHint=False,
                                idempotentHint=False,
                                openWorldHint=False,
                            ),
                            parameters={
                                "type": "object",
                                "properties": {"base_branch": {"type": "string"}},
                                "additionalProperties": False,
                            },
                            output_schema={
                                "type": "object",
                                "properties": {"workspace_id": {"type": "string"}},
                            },
                        ),
                        SimpleNamespace(
                            name="repository_issue_list",
                            description="List current open GitHub issues with authenticated readback.",
                            annotations=SimpleNamespace(
                                readOnlyHint=True,
                                destructiveHint=False,
                                idempotentHint=True,
                                openWorldHint=True,
                            ),
                            parameters={
                                "type": "object",
                                "properties": {"limit": {"type": "integer"}},
                            },
                            output_schema={
                                "type": "object",
                                "properties": {"issues": {"type": "array"}},
                            },
                        ),
                    ]

            mcp = SimpleNamespace(_tool_manager=ToolManager())
            """
        ).strip()
        + "\n",
        "utf-8",
    )
    legacy_capture = subprocess.run(
        [sys.executable, "-c", capture_program],
        cwd=legacy_module_root,
        env={**os.environ, "PYTHONPATH": str(legacy_module_root)},
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert legacy_capture.returncode == 0, legacy_capture.stderr
    legacy_registry = json.loads(legacy_capture.stdout.strip().splitlines()[-1])
    assert legacy_registry["captureProvenance"] == "legacy-fastmcp-introspection-v1"
    assert legacy_registry["capabilityMetadata"] == "deterministically-derived-from-name-and-description"
    assert legacy_registry["toolCount"] == 2
    assert [item["name"] for item in legacy_registry["tools"]] == [
        "repository_issue_list",
        "workspace_prepare",
    ]
    legacy_issue_list = legacy_registry["tools"][0]
    assert legacy_issue_list["effect"] == "read"
    assert legacy_issue_list["parameters"]["properties"]["limit"]["type"] == "integer"
    assert legacy_issue_list["outputSchema"]["properties"]["issues"]["type"] == "array"
    assert {"repository", "ci"} <= set(legacy_issue_list["capabilities"])
    legacy_workspace_prepare = legacy_registry["tools"][1]
    assert legacy_workspace_prepare["effect"] == "workspace-write"
    assert legacy_workspace_prepare["parameters"]["additionalProperties"] is False
    assert legacy_workspace_prepare["outputSchema"]["properties"]["workspace_id"]["type"] == "string"
    assert "repository" in legacy_workspace_prepare["capabilities"]

    comparator_section = script.split(
        'INSTALL_STAGE="verify_mcp_tool_surface_preservation"', 1
    )[1].split('INSTALL_STAGE="verify_isolated_neuro_runtime_canary"', 1)[0]
    comparator_marker = (
        'python3 - "$PREVIOUS_MCP_REGISTRY_FILE" "$NEW_MCP_REGISTRY_FILE" '
        '"$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" "$EXPECTED_MCP_TOOL_COUNT" <<\'PY\'\n'
    )
    comparator = comparator_section.split(comparator_marker, 1)[1].rsplit("\nPY", 1)[0]

    policy_sha256 = hashlib.sha256(
        (ROOT / "config" / "sovereign-continuity-policy.json").read_bytes()
    ).hexdigest()
    runtime_environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "SOVEREIGN_MCP_WORKSPACE_ROOT": str(tmp_path / "workspaces"),
        "SOVEREIGN_TOOL_RANKING_STATE_ROOT": str(tmp_path / "tool-ranking"),
        "SOVEREIGN_NEURO_RUNTIME_STATE_ROOT": str(tmp_path / "neuro-runtime"),
        "SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED": "0",
        "SOVEREIGN_SOURCE_REVISION": "a" * 40,
        "SOVEREIGN_NEURO_POLICY_SHA256": policy_sha256,
        "SOVEREIGN_ANDROID_NATIVE_BUILD_MODE": "github_actions",
        "SOVEREIGN_KAPPA_POS": "1000000",
    }
    registry_process = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from dataclasses import asdict
import json

import launcher
import operational_governance_tools

registry = operational_governance_tools.mcp_tool_contract_registry(include_schemas=True)
payload = asdict(registry)
tools = sorted(payload["tools"], key=lambda item: item["name"])
print(json.dumps({
    "schemaVersion": "sovereign.mcp-deployment-contract-surface.v1",
    "registrySnapshotSha256": registry.registrySnapshotSha256,
    "toolCount": len(tools),
    "tools": tools,
}, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
""",
        ],
        cwd=ROOT,
        env=runtime_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert registry_process.returncode == 0, registry_process.stderr
    current_registry = json.loads(registry_process.stdout.strip().splitlines()[-1])
    assert current_registry["toolCount"] == 249

    predecessor_registry = json.loads(json.dumps(current_registry))
    predecessor_registry["tools"] = [
        item for item in predecessor_registry["tools"] if item["name"] not in EXPECTED_NEURO_TOOLS
    ]
    predecessor_registry["toolCount"] = len(predecessor_registry["tools"])
    predecessor_registry["registrySnapshotSha256"] = "0" * 64
    enum_extensions_removed: set[str] = set()

    def remove_additive_capability_enum_values(value: object, *, tool_name: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "enum" and isinstance(child, list):
                    narrowed = [item for item in child if item not in {"teaching", "neuro"}]
                    if narrowed != child:
                        value[key] = narrowed
                        enum_extensions_removed.add(tool_name)
                else:
                    remove_additive_capability_enum_values(child, tool_name=tool_name)
        elif isinstance(value, list):
            for child in value:
                remove_additive_capability_enum_values(child, tool_name=tool_name)

    for contract in predecessor_registry["tools"]:
        if contract["name"] in EXPECTED_COMPATIBLE_PREDECESSOR_DRIFT:
            remove_additive_capability_enum_values(contract, tool_name=contract["name"])
    assert enum_extensions_removed == EXPECTED_COMPATIBLE_PREDECESSOR_DRIFT
    assert predecessor_registry["toolCount"] == 244

    semantic_fields = (
        "name",
        "capabilities",
        "effect",
        "annotations",
        "parameters",
        "outputSchema",
        "description",
    )
    predecessor_semantics = [
        {field: contract.get(field) for field in semantic_fields}
        for contract in predecessor_registry["tools"]
    ]
    predecessor_semantic_sha256 = hashlib.sha256(
        json.dumps(
            predecessor_semantics,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert predecessor_semantic_sha256 == BASELINE_PREDECESSOR_SEMANTIC_SHA256

    predecessor_path = tmp_path / "predecessor-registry.json"
    current_path = tmp_path / "current-registry.json"
    predecessor_path.write_text(json.dumps(predecessor_registry), "utf-8")
    current_path.write_text(json.dumps(current_registry), "utf-8")
    compatibility = subprocess.run(
        [
            sys.executable,
            "-c",
            comparator,
            str(predecessor_path),
            str(current_path),
            "1",
            "249",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert compatibility.returncode == 0, compatibility.stderr
    compatibility_receipt = json.loads(compatibility.stdout.strip().splitlines()[-1])
    assert set(compatibility_receipt["additions"]) == EXPECTED_NEURO_TOOLS
    assert set(compatibility_receipt["changedCompatibleContracts"]) == (
        EXPECTED_COMPATIBLE_PREDECESSOR_DRIFT
    )
    assert compatibility_receipt["predecessorToolsRemoved"] == []
    assert compatibility_receipt["predecessorToolsRemovedCount"] == 0
    assert compatibility_receipt["incompatibleContracts"] == []
    assert compatibility_receipt["incompatibleContractCount"] == 0
    assert compatibility_receipt["semanticCompatibilityVerified"] is True

    incompatible_registry = json.loads(json.dumps(current_registry))
    incompatible_contract = next(
        item for item in incompatible_registry["tools"] if item["name"] == "mcp_self_update_status"
    )
    incompatible_contract["parameters"].setdefault("required", []).append(
        "__new_deployment_requirement"
    )
    incompatible_path = tmp_path / "incompatible-registry.json"
    incompatible_path.write_text(json.dumps(incompatible_registry), "utf-8")
    rejected = subprocess.run(
        [
            sys.executable,
            "-c",
            comparator,
            str(predecessor_path),
            str(incompatible_path),
            "1",
            "249",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert rejected.returncode != 0
    assert "backward-incompatible predecessor contracts" in rejected.stderr
    assert "schema keywords changed outside the approved input enum widening" in rejected.stderr

    property_predecessor = json.loads(json.dumps(predecessor_registry))
    property_replacement = json.loads(json.dumps(current_registry))
    old_property_contract = next(
        item for item in property_predecessor["tools"] if item["name"] == "mcp_self_update_status"
    )
    new_property_contract = next(
        item for item in property_replacement["tools"] if item["name"] == "mcp_self_update_status"
    )
    old_property_contract["parameters"] = {
        "type": "object",
        "additionalProperties": True,
    }
    new_property_contract["parameters"] = {
        "type": "object",
        "properties": {"newOptional": {"type": "string"}},
        "additionalProperties": True,
    }
    property_predecessor_path = tmp_path / "property-predecessor-registry.json"
    property_replacement_path = tmp_path / "property-replacement-registry.json"
    property_predecessor_path.write_text(json.dumps(property_predecessor), "utf-8")
    property_replacement_path.write_text(json.dumps(property_replacement), "utf-8")
    rejected_property_restriction = subprocess.run(
        [
            sys.executable,
            "-c",
            comparator,
            str(property_predecessor_path),
            str(property_replacement_path),
            "1",
            "249",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert rejected_property_restriction.returncode != 0
    assert "schema keywords changed outside the approved input enum widening" in (
        rejected_property_restriction.stderr
    )

    one_of_predecessor = json.loads(json.dumps(predecessor_registry))
    one_of_replacement = json.loads(json.dumps(current_registry))
    old_one_of_contract = next(
        item for item in one_of_predecessor["tools"] if item["name"] == "mcp_self_update_status"
    )
    new_one_of_contract = next(
        item for item in one_of_replacement["tools"] if item["name"] == "mcp_self_update_status"
    )
    old_one_of_contract["parameters"] = {"oneOf": [{"type": "string"}]}
    new_one_of_contract["parameters"] = {
        "oneOf": [{"type": "string"}, {"type": "string"}]
    }
    one_of_predecessor_path = tmp_path / "one-of-predecessor-registry.json"
    one_of_replacement_path = tmp_path / "one-of-replacement-registry.json"
    one_of_predecessor_path.write_text(json.dumps(one_of_predecessor), "utf-8")
    one_of_replacement_path.write_text(json.dumps(one_of_replacement), "utf-8")
    rejected_one_of_drift = subprocess.run(
        [
            sys.executable,
            "-c",
            comparator,
            str(one_of_predecessor_path),
            str(one_of_replacement_path),
            "1",
            "249",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert rejected_one_of_drift.returncode != 0
    assert "parameters.oneOf: constraint changed outside the approved input enum widening" in (
        rejected_one_of_drift.stderr
    )

    output_predecessor = json.loads(json.dumps(predecessor_registry))
    output_replacement = json.loads(json.dumps(current_registry))
    old_output_contract = next(
        item for item in output_predecessor["tools"] if item["name"] == "mcp_self_update_status"
    )
    new_output_contract = next(
        item for item in output_replacement["tools"] if item["name"] == "mcp_self_update_status"
    )
    old_output_contract["outputSchema"] = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
        "additionalProperties": False,
    }
    new_output_contract["outputSchema"] = {
        "type": "object",
        "properties": {"x": {"type": ["string", "number"]}},
        "required": ["x"],
        "additionalProperties": False,
    }
    output_predecessor_path = tmp_path / "output-predecessor-registry.json"
    output_replacement_path = tmp_path / "output-replacement-registry.json"
    output_predecessor_path.write_text(json.dumps(output_predecessor), "utf-8")
    output_replacement_path.write_text(json.dumps(output_replacement), "utf-8")
    rejected_output_broadening = subprocess.run(
        [
            sys.executable,
            "-c",
            comparator,
            str(output_predecessor_path),
            str(output_replacement_path),
            "1",
            "249",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert rejected_output_broadening.returncode != 0
    assert "schema must remain exact for predecessor output compatibility" in (
        rejected_output_broadening.stderr
    )

    def assert_draft202012_witness_is_rejected(
        *, label: str, old_schema: dict[str, object], new_schema: dict[str, object], witness: object
    ) -> None:
        Draft202012Validator.check_schema(old_schema)
        Draft202012Validator.check_schema(new_schema)
        assert Draft202012Validator(old_schema).is_valid(witness), label
        assert not Draft202012Validator(new_schema).is_valid(witness), label

        witness_predecessor = json.loads(json.dumps(predecessor_registry))
        witness_replacement = json.loads(json.dumps(current_registry))
        next(
            item
            for item in witness_predecessor["tools"]
            if item["name"] == "mcp_self_update_status"
        )["parameters"] = old_schema
        next(
            item
            for item in witness_replacement["tools"]
            if item["name"] == "mcp_self_update_status"
        )["parameters"] = new_schema
        old_path = tmp_path / f"{label}-predecessor.json"
        new_path = tmp_path / f"{label}-replacement.json"
        old_path.write_text(json.dumps(witness_predecessor), "utf-8")
        new_path.write_text(json.dumps(witness_replacement), "utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                comparator,
                str(old_path),
                str(new_path),
                "1",
                "249",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode != 0, (label, result.stdout, result.stderr)
        assert "backward-incompatible predecessor contracts" in result.stderr

    draft202012_witnesses = [
        (
            "pattern-property-explicit-restriction",
            {
                "type": "object",
                "patternProperties": {".*": {}},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "patternProperties": {".*": {}},
                "properties": {"x": {"type": "string"}},
                "additionalProperties": False,
            },
            {"x": 1},
        ),
        (
            "pattern-property-removal",
            {
                "type": "object",
                "patternProperties": {".*": {}},
                "additionalProperties": False,
            },
            {"type": "object", "additionalProperties": False},
            {"x": 1},
        ),
        (
            "prefix-items-two-to-one",
            {"type": "array", "prefixItems": [{}, {}], "items": False},
            {"type": "array", "prefixItems": [{}], "items": False},
            [1, 2],
        ),
        (
            "prefix-items-removal",
            {"type": "array", "prefixItems": [{}], "items": False},
            {"type": "array", "items": False},
            [1],
        ),
        (
            "contains-minimum-default",
            {"type": "array", "contains": {"type": "string"}, "minContains": 0},
            {"type": "array", "contains": {"type": "string"}},
            [],
        ),
        (
            "contains-widening-max-count",
            {
                "type": "array",
                "contains": {"type": "string"},
                "maxContains": 1,
            },
            {
                "type": "array",
                "contains": {"type": ["string", "number"]},
                "maxContains": 1,
            },
            ["a", 1],
        ),
        (
            "all-of-unevaluated-properties",
            {
                "type": "object",
                "allOf": [{"properties": {"x": {}}}],
                "unevaluatedProperties": False,
            },
            {"type": "object", "unevaluatedProperties": False},
            {"x": 1},
        ),
        (
            "contains-unevaluated-items",
            {
                "type": "array",
                "contains": {"type": "string"},
                "unevaluatedItems": False,
            },
            {"type": "array", "unevaluatedItems": False},
            ["a"],
        ),
        (
            "items-unevaluated-items",
            {"type": "array", "items": {}, "unevaluatedItems": False},
            {"type": "array", "unevaluatedItems": False},
            [1],
        ),
        (
            "additional-unevaluated-properties",
            {
                "type": "object",
                "additionalProperties": {},
                "unevaluatedProperties": False,
            },
            {"type": "object", "unevaluatedProperties": False},
            {"x": 1},
        ),
    ]
    for label, old_schema, new_schema, witness in draft202012_witnesses:
        assert_draft202012_witness_is_rejected(
            label=label,
            old_schema=old_schema,
            new_schema=new_schema,
            witness=witness,
        )

    description_replacement = json.loads(json.dumps(current_registry))
    next(
        item
        for item in description_replacement["tools"]
        if item["name"] == "mcp_self_update_status"
    )["description"] += " Changed routing text."
    description_path = tmp_path / "description-replacement-registry.json"
    description_path.write_text(json.dumps(description_replacement), "utf-8")
    rejected_description_drift = subprocess.run(
        [
            sys.executable,
            "-c",
            comparator,
            str(predecessor_path),
            str(description_path),
            "1",
            "249",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert rejected_description_drift.returncode != 0
    assert "description changed" in rejected_description_drift.stderr


def test_installer_runs_a_clean_real_registry_neuro_canary_without_selected_tool_execution() -> None:
    script = INSTALLER.read_text("utf-8")
    canary = script.split('INSTALL_STAGE="verify_isolated_neuro_runtime_canary"', 1)[1].split(
        'INSTALL_STAGE="verify_operating_profile_canaries"', 1
    )[0]

    assert 'TemporaryDirectory(' in canary
    assert 'dir="/var/lib/sovereign-tool-routing"' in canary
    assert 'SOVEREIGN_NEURO_RUNTIME_STATE_ROOT' in canary
    assert 'SOVEREIGN_TOOL_RANKING_STATE_ROOT' in canary
    assert 'SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED"] = "0"' in canary
    assert 'SOVEREIGN_EXPECTED_CANARY_REVISION' in canary
    assert 'SOVEREIGN_NEURO_POLICY_SHA256' in canary
    assert 'tool_manager.call_tool(tool_name, arguments, convert_result=False)' in canary
    assert 'call_registered("neuro_runtime_contract_status", {})' in canary
    assert '"foundation_event_kind": "unknown_canary_kind"' in canary
    assert '"foundation_event_kind": "work_request"' in canary
    assert '"mission_summary": "Read MCP runtime status."' in canary
    assert '"required_capabilities": ["runtime"]' in canary
    assert '"allowed_effects": ["read"]' in canary
    assert '[contract["name"] for contract in selected_contracts] == ["mcp_self_update_status"]' in canary
    assert 'registered_tool.fn = forbidden_selected_tool_call' in canary
    assert 'assert len(set(guarded_tool_names)) == 244' in canary
    assert '__sovereign_success_tracking__' in canary
    assert '__sovereign_operating_profile_wrapped__' in canary
    assert 'guarded_tool_calls == []' in canary
    assert 'call_registered(\n            "teaching_package_assess"' in canary
    assert 'call_registered(\n            "teaching_lesson_simulate"' in canary
    assert 'source_path = repository / "docs" / "runtime.md"' in canary
    assert '"locator": "docs/runtime.md#L3"' in canary
    assert '"content_hash": source_sha256' in canary
    assert '"content_hash": "c" * 64' not in canary
    assert 'package_path.read_bytes() == package_bytes' in canary
    assert 'package_path.stat().st_mtime_ns == package_mtime_ns' in canary
    assert 'source_path.read_bytes() == source_bytes' in canary
    assert 'source_path.stat().st_mtime_ns == source_mtime_ns' in canary
    assert 'repository_tree_after == repository_tree_before' in canary
    assert 'assert tracked_canary_tools == {"neuro_event_commit"}' in canary
    assert 'tracking_contract["telemetryScope"] == "mutable-tool-outcomes-only"' in canary
    assert 'tracking_contract["readOnlyCallsPersisted"] is False' in canary
    assert 'NEURO_EVENT_COMMITTED' in canary
    assert 'NEURO_EVENT_ALREADY_COMMITTED' in canary
    assert 'Tampered mission.' in canary
    assert 'UPDATE projections SET value_hash' in canary
    assert 'failureFamily"] == "ChainIntegrityError"' in canary
    assert 'not temporary_root.exists()' in canary
    assert '"selectedToolsExecuted": False' in canary
    assert '"registeredToolSurfaceVerified": True' in canary
    assert '"teacherAssessmentVerified": True' in canary
    assert '"teacherLessonSimulationVerified": True' in canary
    assert '"teachingSourceProvenanceVerified": True' in canary
    assert '"teachingPackageUnchanged": True' in canary
    assert '"telemetryScope": "mutable-tool-outcomes-only"' in canary
    assert '"readOnlyCallsPersisted": False' in canary
    assert '"persistedOutcomeTools": persisted_outcome_tools' in canary
    assert '"isolatedStateCleaned": True' in canary
    assert '"neuro_functional_canary":true' in script
    assert '"neuro_selected_tools_executed":false' in script
    assert '"registered_tool_surface_canary":true' in script
    assert '"teaching_functional_canary":true' in script
    assert '"teaching_source_provenance_canary":true' in script
    assert '"teaching_package_mutated":false' in script
    assert '"tool_outcome_telemetry_scope":"mutable-tool-outcomes-only"' in script
    assert '"read_only_tool_calls_persisted":false' in script
    assert '"canary_persisted_outcome_tools":["neuro_event_commit"]' in script


def test_exact_embedded_neuro_canary_runs_against_the_real_local_registry(tmp_path: Path) -> None:
    script = INSTALLER.read_text("utf-8")
    section = script.split('INSTALL_STAGE="verify_isolated_neuro_runtime_canary"', 1)[1].split(
        'INSTALL_STAGE="verify_operating_profile_canaries"', 1
    )[0]
    marker = 'sovereign-chatgpt-mcp python - <<\'PY\'\n'
    embedded = section.split(marker, 1)[1].rsplit("\nPY", 1)[0]
    embedded = embedded.replace(
        'dir="/var/lib/sovereign-tool-routing"',
        'dir=os.environ["SOVEREIGN_CANARY_TEST_PARENT"]',
    )

    revision = "a" * 40
    policy_sha256 = hashlib.sha256(
        (ROOT / "config" / "sovereign-continuity-policy.json").read_bytes()
    ).hexdigest()
    canary_parent = tmp_path / "mounted-routing-state"
    canary_parent.mkdir(mode=0o700)
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "SOVEREIGN_CANARY_TEST_PARENT": str(canary_parent),
        "SOVEREIGN_EXPECTED_CANARY_REVISION": revision,
        "SOVEREIGN_SOURCE_REVISION": revision,
        "SOVEREIGN_NEURO_POLICY_SHA256": policy_sha256,
        "SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED": "0",
        "SOVEREIGN_MCP_WORKSPACE_ROOT": str(tmp_path / "workspaces"),
        "SOVEREIGN_TOOL_RANKING_STATE_ROOT": str(tmp_path / "tool-ranking"),
        "SOVEREIGN_MCP_HOST": "127.0.0.1",
        "SOVEREIGN_MCP_PORT": "8090",
        "SOVEREIGN_MCP_REPOSITORY": "OuroborosCollective/Sovereign-Studio-ato",
        "SOVEREIGN_ANDROID_NATIVE_BUILD_MODE": "github_actions",
        "SOVEREIGN_KAPPA_POS": "1000000",
    }
    completed = subprocess.run(
        [sys.executable, "-c", embedded],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout.strip().splitlines()[-1])
    assert receipt == {
        "canonicalReadbackVerified": True,
        "commitReplayVerified": True,
        "guardedPredecessorToolCount": 244,
        "isolatedStateCleaned": True,
        "previewProposalOnly": True,
        "persistedOutcomeTools": ["neuro_event_commit"],
        "quarantineNoMutation": True,
        "readOnlyCallsPersisted": False,
        "registeredToolSurfaceVerified": True,
        "registryToolCount": 249,
        "selectedToolsExecuted": False,
        "status": "NEURO_DEPLOYMENT_CANARY_VERIFIED",
        "tamperDetected": True,
        "teacherAssessmentVerified": True,
        "teacherLessonSimulationVerified": True,
        "teachingSourceProvenanceVerified": True,
        "teachingPackageUnchanged": True,
        "telemetryScope": "mutable-tool-outcomes-only",
    }
    assert list(canary_parent.iterdir()) == []
    assert list((tmp_path / "workspaces").iterdir()) == []


def test_ci_packages_and_independently_reads_back_the_neuro_runtime(tmp_path: Path) -> None:
    workflow = WORKFLOW.read_text("utf-8")
    remote_install = REMOTE_INSTALL.read_text("utf-8")
    deployment_surface = workflow + "\n" + remote_install

    for path in (
        "neuro_architecture_contract.py",
        "neuromorphic_runtime.py",
        "foundation_runtime.py",
        "neuro_teaching_tools.py",
        "skills/sovereign-neuro-teaching-runtime/SKILL.md",
    ):
        assert path in workflow
    assert "assert len(tool_names) == 249" in workflow
    assert "assert len(tool_names - expected_tools) == 244" in deployment_surface
    assert "SOVEREIGN_SOURCE_REVISION: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow
    assert workflow.count("ref: ${{ env.SOVEREIGN_SOURCE_REVISION }}") == 2
    assert '--expected-head "${SOVEREIGN_SOURCE_REVISION}"' in workflow
    assert '--label "org.opencontainers.image.revision=${SOVEREIGN_SOURCE_REVISION}"' in workflow
    assert 'test "$REVISION_LABEL" = "$SOVEREIGN_SOURCE_REVISION"' in workflow
    assert '-e SOVEREIGN_EXPECTED_WORKFLOW_REVISION="$EXPECTED_REVISION"' in deployment_surface
    assert "assert revision == os.environ.get('SOVEREIGN_EXPECTED_WORKFLOW_REVISION'), revision" in deployment_surface
    assert "status = neuro_teaching_tools.neuro_runtime_contract_status()" in deployment_surface
    assert "assert status.status == 'NEURO_RUNTIME_CONTRACT_READY'" in deployment_surface
    assert "assert status.data['admissions']['pending'] == 0" in deployment_surface
    assert "'neuro_runtime_verified': neuro_runtime_state == 'ready'" in deployment_surface
    assert "SOVEREIGN_NEURO_GLOBAL_MAX_EVENTS" in workflow
    assert "SOVEREIGN_NEURO_OUTCOME_MAX_EVENTS" in workflow
    assert "tool_manager.call_tool(tool_name, arguments, convert_result=False)" in deployment_surface
    assert '"registered_tool_surface_canary":true' in deployment_surface
    assert '"teaching_functional_canary":true' in deployment_surface
    assert '"teaching_source_provenance_canary":true' in deployment_surface
    assert '"teaching_package_mutated":false' in deployment_surface
    assert "mcp_tool_contract_registry(include_schemas=True)" in deployment_surface
    assert '"changedCompatibleContracts": changed_compatible_contracts' in deployment_surface
    assert '"incompatibleContractCount": len(incompatible_contracts)' in deployment_surface
    assert '"semanticCompatibilityVerified": predecessor_captured' in deployment_surface
    assert '"tool_outcome_telemetry_scope":"mutable-tool-outcomes-only"' in deployment_surface
    assert '"read_only_tool_calls_persisted":false' in deployment_surface
    assert '"canary_persisted_outcome_tools":\\["neuro_event_commit"\\]' in deployment_surface
    assert "SOVEREIGN_MCP_ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR=0" in deployment_surface
    assert "receipt.get('predecessor_container_present') is not predecessor_observed" in deployment_surface
    assert "'predecessor_contract_gate': predecessor_contract_gate" in deployment_surface
    assert "payload.get('semantic_compatibility_verified') is True" in deployment_surface
    assert "payload.get('first_install_attested') is False" in deployment_surface

    writer_marker = 'cat > "$STATUS_WRITER" <<\'PY\'\n'
    writer = textwrap.dedent(
        remote_install.split(writer_marker, 1)[1].split("\nPY", 1)[0]
    )

    def run_status_writer(
        receipt: dict[str, object],
        *,
        label: str,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        receipt_path = tmp_path / f"{label}-receipt.json"
        status_path = tmp_path / f"{label}-status.json"
        receipt_path.write_text(json.dumps(receipt), "utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                writer,
                str(status_path),
                str(receipt_path),
                "a" * 40,
                f"ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp@sha256:{'b' * 64}",
                f"sha256:{'c' * 64}",
                "1000000",
                "d" * 64,
                "running healthy",
                "ready",
                "active",
                "ready",
                "visible",
                "visible",
                "active",
                "forbidden",
                "ready",
                "ready",
                "not_required",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed, status_path

    predecessor_receipt = {
        "predecessor_container_present": True,
        "predecessor_registry_capture_mode": "immutable-image-offline",
        "previous_tool_surface_compared": True,
        "semantic_compatibility_verified": True,
        "first_install_without_predecessor": False,
        "first_install_attested": False,
    }
    predecessor_status, predecessor_status_path = run_status_writer(
        predecessor_receipt,
        label="predecessor",
    )
    assert predecessor_status.returncode == 0, predecessor_status.stderr
    predecessor_evidence = json.loads(predecessor_status_path.read_text("utf-8"))
    assert predecessor_evidence["status"] == "UPDATED"
    assert predecessor_evidence["predecessor_contract_gate"] is True
    assert predecessor_evidence["semantic_compatibility_verified"] is True

    incompatible_receipt = {**predecessor_receipt, "semantic_compatibility_verified": False}
    incompatible_status, incompatible_status_path = run_status_writer(
        incompatible_receipt,
        label="incompatible",
    )
    assert incompatible_status.returncode != 0
    assert "predecessor_contract_gate" in incompatible_status.stderr
    assert not incompatible_status_path.exists()

    first_install_receipt = {
        "predecessor_container_present": False,
        "predecessor_registry_capture_mode": "attested-first-install-no-predecessor",
        "previous_tool_surface_compared": False,
        "semantic_compatibility_verified": False,
        "first_install_without_predecessor": True,
        "first_install_attested": True,
    }
    first_install_status, first_install_status_path = run_status_writer(
        first_install_receipt,
        label="first-install",
    )
    assert first_install_status.returncode == 0, first_install_status.stderr
    first_install_evidence = json.loads(first_install_status_path.read_text("utf-8"))
    assert first_install_evidence["status"] == "UPDATED"
    assert first_install_evidence["predecessor_contract_gate"] is True
    assert first_install_evidence["first_install_attested"] is True
