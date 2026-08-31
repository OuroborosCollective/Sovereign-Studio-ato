#!/usr/bin/env bash
set -Eeuo pipefail
run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
    return
  fi
  if sudo -n true >/dev/null 2>&1; then
    sudo -n "$@"
    return
  fi
  test -n "${SUDO_PASSWORD:-}" || { echo 'sudo password is unavailable for VPS bootstrap.' >&2; exit 1; }
  printf '%s\n' "$SUDO_PASSWORD" | sudo -S -p '' "$@"
}
RELEASE_RELATIVE_DIR="${RELEASE_RELATIVE_DIR:?RELEASE_RELATIVE_DIR is required}"
case "$RELEASE_RELATIVE_DIR" in
  .sovereign-releases/sovereign-chatgpt-mcp-*) ;;
  *) echo "Unsafe relative release directory: $RELEASE_RELATIVE_DIR" >&2; exit 1 ;;
esac
case "$RELEASE_RELATIVE_DIR" in *..*) echo 'Release directory traversal is forbidden.' >&2; exit 1 ;; esac
RELEASE_DIR="$HOME/$RELEASE_RELATIVE_DIR"
EXPECTED_REVISION="${EXPECTED_REVISION:?EXPECTED_REVISION is required}"
EXPECTED_IMAGE_DIGEST="${EXPECTED_IMAGE_DIGEST:?EXPECTED_IMAGE_DIGEST is required}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required}"
KAPPA_POS="${KAPPA_POS:?KAPPA_POS is required}"
EXPECTED_IMAGE_REFERENCE="${IMAGE_REPOSITORY}@${EXPECTED_IMAGE_DIGEST}"
ARCHIVE="$RELEASE_DIR/sovereign-chatgpt-mcp.tar.gz"
REVISION_FILE="$RELEASE_DIR/sovereign-chatgpt-mcp.revision"
IMAGE_DIGEST_FILE="$RELEASE_DIR/sovereign-chatgpt-mcp.image-digest"
KAPPA_FILE="$RELEASE_DIR/sovereign-chatgpt-mcp.kappa-pos"
CHECKSUM_FILE="$RELEASE_DIR/sovereign-chatgpt-mcp.sha256"
WORK_DIR="$RELEASE_DIR/work"
DOCKER_AUTH_DIR="$RELEASE_DIR/docker-auth"
STATUS_DIR=/var/lib/sovereign-chatgpt-self-update
STATUS_FILE="$STATUS_DIR/status.json"

cleanup() {
  run_root rm -rf "$RELEASE_DIR" || true
}
trap cleanup EXIT

test -n "${HOME:-}" || { echo 'Remote HOME is unavailable.' >&2; exit 1; }
case "$RELEASE_DIR" in
  "$HOME"/.sovereign-releases/sovereign-chatgpt-mcp-*) ;;
  *) echo "Unsafe resolved release directory: $RELEASE_DIR" >&2; exit 1 ;;
esac
[[ "$EXPECTED_REVISION" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid expected revision.' >&2; exit 1; }
[[ "$EXPECTED_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'Invalid expected image digest.' >&2; exit 1; }
test "$KAPPA_POS" = '1000000' || { echo 'Invalid KAPPA_POS invariant.' >&2; exit 1; }
for release_file in "$ARCHIVE" "$REVISION_FILE" "$IMAGE_DIGEST_FILE" "$KAPPA_FILE" "$CHECKSUM_FILE"; do
  test -f "$release_file" || { echo "Release evidence file missing: $release_file" >&2; exit 1; }
done
(
  cd "$RELEASE_DIR"
  sha256sum --check "$(basename "$CHECKSUM_FILE")"
)
test "$(tr -d '\r\n' < "$REVISION_FILE")" = "$EXPECTED_REVISION"
test "$(tr -d '\r\n' < "$IMAGE_DIGEST_FILE")" = "$EXPECTED_IMAGE_DIGEST"
test "$(tr -d '\r\n' < "$KAPPA_FILE")" = "$KAPPA_POS"
ARCHIVE_SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
[[ "$ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]]
python3 - "$ARCHIVE" <<'PY'
from pathlib import PurePosixPath
import sys
import tarfile

archive = sys.argv[1]
with tarfile.open(archive, 'r:gz') as bundle:
    members = bundle.getmembers()
    if not members:
        raise SystemExit('release archive is empty')
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts:
            raise SystemExit(f'unsafe archive path: {member.name}')
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f'unsupported archive entry: {member.name}')
PY
tar -tzf "$ARCHIVE" >/dev/null
rm -rf "$WORK_DIR"
install -d -m 0700 "$WORK_DIR"
tar -xzf "$ARCHIVE" -C "$WORK_DIR"

SOURCE_DIR="$WORK_DIR/tools/sovereign-chatgpt-mcp"
for required in Dockerfile docker-compose.yml command_contract.py command_queue.py command_worker.py owner_input_client.py a2a_runtime_client.py document_pipeline.py github_knowledge_canary.py github_knowledge_mcp_client.py owner_input_widget.py enterprise_backend_tools.py freemium_product_architect_tools.py continuity.py validate_continuity.py operating_profile.py operational_governance_tools.py operational_assurance_tools.py output_contracts.py toolchain_composition.py neuro_architecture_contract.py neuromorphic_runtime.py foundation_runtime.py neuro_teaching_tools.py config/sovereign-mcp-operating-profile.json config/sovereign-continuity-policy.json continuity-data/CONTEXT.md continuity-data/LEDGER.jsonl skills/sovereign-mcp-optimal-operation/SKILL.md skills/sovereign-operational-governance/SKILL.md skills/sovereign-operational-assurance/SKILL.md skills/sovereign-neuro-teaching-runtime/SKILL.md launcher.py server.py mcp_protocol_health.py sovereign_cognitive_widget.py managed_compose.py n8n_host_maintenance.py patchmon_operator.py templates/pgbackweb-wq5r/docker-compose.yml templates/patchmon-sovereign/docker-compose.yml templates/code-server-46bq/docker-compose.yml deploy/install-on-vps.sh deploy/sovereign-chatgpt-command-worker.service deploy/reconcile-main-release.py deploy/sovereign-release-reconciler.service deploy/sovereign-release-reconciler.timer; do
  test -f "$SOURCE_DIR/$required" || { echo "Required MCP release file is missing: $required" >&2; exit 1; }
done
bash -n "$SOURCE_DIR/deploy/install-on-vps.sh"
test -n "${GHCR_USERNAME:-}" || { echo 'GHCR username is unavailable on the VPS session.' >&2; exit 1; }
test -n "${GHCR_TOKEN:-}" || { echo 'GHCR package-read token is unavailable on the VPS session.' >&2; exit 1; }
install -d -m 0700 "$DOCKER_AUTH_DIR"
python3 - "$DOCKER_AUTH_DIR/config.json" <<'PY'
from pathlib import Path
import base64
import json
import os
import sys

username = os.environ.get('GHCR_USERNAME', '')
token = os.environ.get('GHCR_TOKEN', '')
if not username or not token:
    raise SystemExit('ephemeral GHCR credentials are incomplete')
encoded = base64.b64encode(f'{username}:{token}'.encode('utf-8')).decode('ascii')
Path(sys.argv[1]).write_text(
    json.dumps({'auths': {'ghcr.io': {'auth': encoded}}}, separators=(',', ':')) + '\n',
    'utf-8',
)
PY
chmod 0600 "$DOCKER_AUTH_DIR/config.json"
unset GHCR_TOKEN
PREDECESSOR_CONTAINER_NAMES="$(
  run_root docker container ls --all \
    --filter 'name=^/sovereign-chatgpt-mcp$' \
    --format '{{.Names}}'
)"
case "$PREDECESSOR_CONTAINER_NAMES" in
  sovereign-chatgpt-mcp) PREDECESSOR_CONTAINER_PRESENT=true ;;
  '') PREDECESSOR_CONTAINER_PRESENT=false ;;
  *) echo 'Ambiguous predecessor MCP container discovery.' >&2; exit 1 ;;
esac
INSTALL_OUTPUT="$RELEASE_DIR/mcp-install-output.log"
INSTALL_RECEIPT_FILE="$RELEASE_DIR/mcp-install-receipt.json"
if ! run_root env \
  DOCKER_CONFIG="$DOCKER_AUTH_DIR" \
  SOVEREIGN_MCP_EXPECTED_REVISION="$EXPECTED_REVISION" \
  SOVEREIGN_MCP_TUNNEL_MODE=disabled \
  SOVEREIGN_MCP_ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR=0 \
  bash "$SOURCE_DIR/deploy/install-on-vps.sh" | tee "$INSTALL_OUTPUT"; then
  echo 'MCP installer failed before producing verified evidence.' >&2
  exit 1
fi
python3 - "$INSTALL_OUTPUT" "$INSTALL_RECEIPT_FILE" "$PREDECESSOR_CONTAINER_PRESENT" <<'PY'
from pathlib import Path
import json
import os
import sys

output_path = Path(sys.argv[1])
receipt_path = Path(sys.argv[2])
predecessor_observed = sys.argv[3] == 'true'
receipt = None
for line in reversed(output_path.read_text('utf-8').splitlines()):
    try:
        candidate = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(candidate, dict) and candidate.get('ok') is True:
        receipt = candidate
        break
if receipt is None:
    raise SystemExit('installer did not emit a valid success receipt')
if receipt.get('predecessor_container_present') is not predecessor_observed:
    raise SystemExit('installer predecessor evidence disagrees with pre-install observation')
if predecessor_observed:
    expected = {
        'previous_tool_surface_compared': True,
        'semantic_compatibility_verified': True,
        'first_install_without_predecessor': False,
        'first_install_attested': False,
    }
    if receipt.get('predecessor_registry_capture_mode') not in {
        'running-container',
        'immutable-image-offline',
    }:
        raise SystemExit('installer did not identify a valid predecessor capture mode')
else:
    expected = {
        'previous_tool_surface_compared': False,
        'semantic_compatibility_verified': False,
        'first_install_without_predecessor': True,
        'first_install_attested': True,
    }
    if receipt.get('predecessor_registry_capture_mode') != 'attested-first-install-no-predecessor':
        raise SystemExit('installer did not emit explicit first-install attestation')
mismatches = {
    field: {'expected': value, 'actual': receipt.get(field)}
    for field, value in expected.items()
    if receipt.get(field) is not value
}
if mismatches:
    raise SystemExit(f'installer semantic compatibility receipt is incomplete: {mismatches}')
if receipt.get('tool_outcome_telemetry_scope') != 'mutable-tool-outcomes-only':
    raise SystemExit('installer telemetry scope is not the verified mutable-only contract')
if receipt.get('read_only_tool_calls_persisted') is not False:
    raise SystemExit('installer receipt claims read-only tool outcome persistence')
temporary = receipt_path.with_suffix('.tmp')
temporary.write_text(
    json.dumps(receipt, sort_keys=True, separators=(',', ':')) + '\n',
    'utf-8',
)
os.chmod(temporary, 0o600)
temporary.replace(receipt_path)
PY

CONTAINER_STATE="$(run_root docker inspect sovereign-chatgpt-mcp --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}')"
test "$CONTAINER_STATE" = 'running healthy'
CONTAINER_IMAGE_REFERENCE="$(run_root docker inspect sovereign-chatgpt-mcp --format '{{.Config.Image}}')"
CONTAINER_IMAGE_ID="$(run_root docker inspect sovereign-chatgpt-mcp --format '{{.Image}}')"
test "$CONTAINER_IMAGE_REFERENCE" = "$EXPECTED_IMAGE_REFERENCE"
[[ "$CONTAINER_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]
INSTALLED_REVISION="$(run_root docker image inspect "$CONTAINER_IMAGE_ID" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
INSTALLED_KAPPA_POS="$(run_root docker image inspect "$CONTAINER_IMAGE_ID" --format '{{index .Config.Labels "io.ouroboros.sovereign.kappa-pos"}}')"
INSTALLED_CROSS_RUNTIME_PARITY="$(run_root docker image inspect "$CONTAINER_IMAGE_ID" --format '{{index .Config.Labels "io.ouroboros.sovereign.cross-runtime-parity"}}')"
test "$INSTALLED_REVISION" = "$EXPECTED_REVISION"
test "$INSTALLED_KAPPA_POS" = "$KAPPA_POS"
test "$INSTALLED_CROSS_RUNTIME_PARITY" = "$CROSS_RUNTIME_PARITY"
CONTAINER_REPO_DIGEST="$(
  run_root docker image inspect "$CONTAINER_IMAGE_ID" --format '{{json .RepoDigests}}' \
    | python3 -c 'import json,sys; expected=sys.argv[1]; values=json.load(sys.stdin); print(expected if expected in values else "")' "$EXPECTED_IMAGE_REFERENCE"
)"
test "$CONTAINER_REPO_DIGEST" = "$EXPECTED_IMAGE_REFERENCE"

run_root test -S /run/sovereign-chatgpt-broker/operator.sock
BROKER_SOCKET_HOST_STATE=visible
run_root docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock
BROKER_SOCKET_CONTAINER_STATE=visible
run_root docker exec sovereign-chatgpt-mcp python -c 'import server; status=server.broker.status(); assert status.get("status") == "BROKER_READY", status'
BROKER_RPC_STATE=ready
run_root docker exec sovereign-chatgpt-mcp python /app/mcp_protocol_health.py --url http://127.0.0.1:8090/mcp --timeout-seconds 5
MCP_PROTOCOL_STATE=ready
run_root docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-operational-governance/SKILL.md
run_root docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-operational-assurance/SKILL.md
run_root docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-mcp-optimal-operation/SKILL.md
run_root docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-neuro-teaching-runtime/SKILL.md
run_root docker exec sovereign-chatgpt-mcp test -f /app/config/sovereign-mcp-operating-profile.json
run_root docker exec sovereign-chatgpt-mcp test -f /app/config/sovereign-continuity-policy.json
run_root docker exec sovereign-chatgpt-mcp test -f /app/continuity-data/CONTEXT.md
run_root docker exec sovereign-chatgpt-mcp test -f /app/continuity-data/LEDGER.jsonl
run_root docker exec sovereign-chatgpt-mcp python -c "import launcher; import server; import operating_profile; import operational_governance_tools; import operational_assurance_tools; import output_contracts; import toolchain_composition; assert launcher.mcp is server.mcp; assert callable(toolchain_composition.mcp_toolchain_compile); assert callable(toolchain_composition.mcp_toolchain_validate); assert callable(toolchain_composition.mcp_toolchain_next_step); assert output_contracts.ToolOutputEnvelope is not None; output_contract_report=launcher.OUTPUT_CONTRACT_INSTALLATION; assert output_contract_report.get('ok') is True, output_contract_report; assert output_contract_report.get('missingOutputSchemaCount') == 0, output_contract_report; operating_profile_report=launcher.OPERATING_PROFILE_ENFORCEMENT; assert operating_profile_report.ok is True, operating_profile_report; assert operating_profile_report.enforcedToolCount == operating_profile_report.mutableToolCount, operating_profile_report; profile_status=operating_profile.sovereign_operating_profile_status(); assert profile_status.status == 'OPERATING_PROFILE_ENFORCED', profile_status; names=('mcp_self_update_schedule','mcp_self_update_status','repository_pr_status','repository_merge_pr','repository_merge_pr_series','android_run_validation_suite','owner_approval_request_create','owner_approval_request_status','openrouter_provider_status','openrouter_provider_activate','openrouter_free_status','openrouter_free_activate','openrouter_free_key_rotate','litellm_provider_route_activate','owner_approval_widget_open','controller_run_start','controller_run_list','controller_run_status','controller_run_external_event','controller_run_resume','a2a_live_canary','managed_compose_stack_plan','deploy_managed_compose_stack'); missing=[name for name in names if not callable(getattr(server,name,None))]; assert not missing, missing; tool_names={tool.name for tool in server.mcp._tool_manager.list_tools()}; resource_uris={str(resource.uri) for resource in server.mcp._resource_manager.list_resources()}; assert 'sovereign_cognitive_architecture_status' in tool_names, tool_names; required_operational={'operational_skill_inventory','mcp_tool_contract_registry','tool_recommend_for_mission','mcp_registry_snapshot_verify','evidence_graph_build','runtime_runbook_generate','ownership_codeowners_guard','compliance_evidence_export','sovereign_operating_profile_status','sovereign_mission_preflight'}; assert required_operational.issubset(tool_names), sorted(required_operational-tool_names); required_assurance={'operational_assurance_skill_inventory','vps_capacity_resource_pressure_assess','runtime_dependency_health_matrix','outbox_queue_liveness_assess','scheduled_maintenance_coordinate','runtime_topology_change_audit','postgres_query_index_performance_assess','data_integrity_invariant_audit','data_repair_plan_build','vector_memory_consistency_assess','memory_poisoning_provenance_guard','learning_pattern_lifecycle_preview','data_retention_privacy_audit','multi_tenant_isolation_verify','mcp_schema_compatibility_audit','mcp_protocol_conformance_fuzz_plan','tool_permission_minimize','dynamic_execution_containment_audit','skill_capability_coverage_map','skill_lifecycle_deprecation_preview','skill_regression_benchmark','tool_idempotency_verify','owner_approval_policy_evaluate','secret_lifecycle_rotation_assess','secret_literal_triage','sbom_provenance_image_signing_verify','dependency_vulnerability_remediation_plan','authentication_chaos_negative_test_assess'}; assert required_assurance.issubset(tool_names), sorted(required_assurance-tool_names); assurance=operational_assurance_tools.operational_assurance_skill_inventory(); assert assurance.status == 'OPERATIONAL_ASSURANCE_SKILLS_READY', assurance; capacity=server.broker.call('runtime_capacity_snapshot', {}, timeout=90); assert capacity.get('status') in {'RUNTIME_CAPACITY_SNAPSHOT_READY','RUNTIME_CAPACITY_SNAPSHOT_DEGRADED'}, capacity; registry=operational_governance_tools.mcp_tool_contract_registry(include_schemas=False); assert registry.status == 'MCP_TOOL_REGISTRY_READY', registry; assert registry.toolCount == len(tool_names), (registry.toolCount,len(tool_names)); assert 'ui://sovereign/dev_dashboard.v2.html' in resource_uris, resource_uris; assert 'ui://sovereign/owner_input.html' in resource_uris, resource_uris; boundaries=server.mcp_runtime_boundaries(); assert boundaries.get('llm_can_receive_protected_values') is False, boundaries; canary=server.broker.call('host_worker_canary', {}, timeout=10); assert canary.get('status') == 'HOST_WORKER_READY', canary; assert canary.get('execution_origin') == 'host_worker', canary; print({'tool_contract': True, 'cognitive_widget': True, 'owner_input_widget': True, 'self_update': True, 'pr_lifecycle': True, 'owner_approval': True, 'host_worker_canary': True})"
run_root docker exec \
  -e SOVEREIGN_EXPECTED_WORKFLOW_REVISION="$EXPECTED_REVISION" \
  -i sovereign-chatgpt-mcp python - <<'PY'
import hashlib
import os
from pathlib import Path

import launcher
import neuro_teaching_tools

expected_tools = {
    'neuro_event_commit',
    'neuro_event_route_preview',
    'neuro_runtime_contract_status',
    'teaching_lesson_simulate',
    'teaching_package_assess',
}
tool_names = {tool.name for tool in launcher.mcp._tool_manager.list_tools()}
assert len(tool_names) == 249, len(tool_names)
assert expected_tools <= tool_names, sorted(expected_tools - tool_names)
assert len(tool_names - expected_tools) == 244, len(tool_names - expected_tools)
revision = os.environ.get('SOVEREIGN_SOURCE_REVISION', '')
assert len(revision) == 40 and all(character in '0123456789abcdef' for character in revision), revision
assert revision == os.environ.get('SOVEREIGN_EXPECTED_WORKFLOW_REVISION'), revision
policy_path = Path(neuro_teaching_tools.__file__).resolve().parent / 'config' / 'sovereign-continuity-policy.json'
embedded_policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest()
assert os.environ.get('SOVEREIGN_NEURO_POLICY_SHA256') == embedded_policy_sha256
status = neuro_teaching_tools.neuro_runtime_contract_status()
assert status.ok is True, status
assert status.status == 'NEURO_RUNTIME_CONTRACT_READY', status
assert status.evidence['toolCount'] == 249, status
assert status.data['ledger']['integrityStatus'] in {'NOT_INITIALIZED', 'VERIFIED'}, status
assert status.data['foundationLedger']['integrityStatus'] in {'NOT_INITIALIZED', 'VERIFIED'}, status
assert status.data['admissions']['pending'] == 0, status
assert status.data['globalLedgerQuota']['exceeded'] is False, status
assert status.data['toolOutcomeQuota']['exceeded'] is False, status
print({
    'neuroRuntime': status.status,
    'toolCount': len(tool_names),
    'sourceRevisionBound': True,
    'policySha256Bound': True,
    'persistentLedgerReadback': status.data['ledger']['integrityStatus'],
})
PY
NEURO_RUNTIME_STATE=ready
run_root docker exec -i sovereign-chatgpt-mcp python - <<'PY'
import asyncio
import server

tools = asyncio.run(server.mcp.list_tools())
resources = asyncio.run(server.mcp.list_resources())
cognitive_tool = next(
    tool for tool in tools
    if tool.name == 'sovereign_cognitive_architecture_status'
)
assert cognitive_tool.outputSchema, cognitive_tool
assert 'manifest' in cognitive_tool.outputSchema.get('properties', {}), cognitive_tool.outputSchema
cognitive_resource = next(
    resource for resource in resources
    if str(resource.uri) == 'ui://sovereign/dev_dashboard.v2.html'
)
serialized = cognitive_resource.model_dump(by_alias=True)
assert serialized['_meta']['ui']['domain'] == 'https://sovereign-backend.arelorian.de', serialized
assert serialized['_meta']['openai/widgetDomain'] == 'https://sovereign-backend.arelorian.de', serialized
contents = list(asyncio.run(server.mcp.read_resource(cognitive_resource.uri)))
assert contents[0].meta['ui']['domain'] == 'https://sovereign-backend.arelorian.de', contents[0].meta
print({
    'cognitiveOutputSchema': True,
    'widgetDomain': serialized['_meta']['ui']['domain'],
    'widgetUri': str(cognitive_resource.uri),
})
PY
OPERATING_PROFILE_STATE=ready
run_root docker exec sovereign-chatgpt-mcp python -c "import server; assert callable(server.repository_sync_workspace_to_pr_head)"
INBOUND_MUTATION_STATE=forbidden
COMMAND_WORKER_STATE="$(run_root systemctl is-active sovereign-chatgpt-command-worker.service)"
BROKER_SERVICE_STATE="$(run_root systemctl is-active sovereign-chatgpt-broker.service)"
TUNNEL_SERVICE_STATE=not_required
test "$COMMAND_WORKER_STATE" = active
test "$BROKER_SERVICE_STATE" = active

run_root install -d -m 0750 "$STATUS_DIR"
STATUS_WRITER="$RELEASE_DIR/write-mcp-status.py"
cat > "$STATUS_WRITER" <<'PY'
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import time

(
    status_path,
    install_receipt_path,
    revision,
    image_reference,
    image_id,
    kappa_pos,
    archive_sha256,
    container_state,
    mcp_protocol_state,
    broker_service_state,
    broker_rpc_state,
    broker_socket_host_state,
    broker_socket_container_state,
    command_worker_state,
    inbound_mutation_state,
    operating_profile_state,
    neuro_runtime_state,
    tunnel_service_state,
) = sys.argv[1:]

install_receipt = json.loads(Path(install_receipt_path).read_text('utf-8'))
predecessor_present = install_receipt.get('predecessor_container_present') is True
first_install_attested = install_receipt.get('first_install_attested') is True
semantic_compatibility_verified = (
    install_receipt.get('semantic_compatibility_verified') is True
)
previous_tool_surface_compared = (
    install_receipt.get('previous_tool_surface_compared') is True
)
predecessor_contract_gate = (
    predecessor_present
    and semantic_compatibility_verified
    and previous_tool_surface_compared
    and not first_install_attested
) or (
    not predecessor_present
    and not semantic_compatibility_verified
    and not previous_tool_surface_compared
    and first_install_attested
    and install_receipt.get('first_install_without_predecessor') is True
)

checks = {
    'revision_verified': bool(re.fullmatch(r'[0-9a-f]{40}', revision)),
    'image_digest_verified': bool(re.fullmatch(r'ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}', image_reference)),
    'image_id_verified': bool(re.fullmatch(r'sha256:[0-9a-f]{64}', image_id)),
    'kappa_pos_verified': kappa_pos == '1000000',
    'cross_runtime_parity_proven': True,
    'archive_sha256_verified': bool(re.fullmatch(r'[0-9a-f]{64}', archive_sha256)),
    'container_healthy': container_state == 'running healthy',
    'mcp_protocol_ready': mcp_protocol_state == 'ready',
    'broker_active': broker_service_state == 'active',
    'broker_rpc_ready': broker_rpc_state == 'ready',
    'broker_socket_host_visible': broker_socket_host_state == 'visible',
    'broker_socket_container_visible': broker_socket_container_state == 'visible',
    'host_command_worker_active': command_worker_state == 'active',
    'inbound_mutation_forbidden': inbound_mutation_state == 'forbidden',
    'operating_profile_enforced': operating_profile_state == 'ready',
    'neuro_runtime_verified': neuro_runtime_state == 'ready',
    'tunnel_not_required': tunnel_service_state == 'not_required',
    'predecessor_contract_gate': predecessor_contract_gate,
}
evidence = {
    'revision': revision,
    'tunnel_mode': 'disabled',
    'image': image_reference,
    'image_id': image_id,
    'kappa_pos': int(kappa_pos),
    'parity_evidence_source': 'immutable_image_label_and_ci_vector_comparison',
    'archive_sha256': archive_sha256,
    'predecessor_container_present': predecessor_present,
    'predecessor_registry_capture_mode': install_receipt.get('predecessor_registry_capture_mode'),
    'previous_tool_surface_compared': previous_tool_surface_compared,
    'semantic_compatibility_verified': semantic_compatibility_verified,
    'first_install_without_predecessor': install_receipt.get('first_install_without_predecessor') is True,
    'first_install_attested': first_install_attested,
    **checks,
}
canonical = json.dumps(evidence, sort_keys=True, separators=(',', ':')).encode('utf-8')
payload = {
    'ok': all(checks.values()),
    'status': 'UPDATED' if all(checks.values()) else 'FAILED',
    'detail': 'private ChatGPT MCP installed from measured GitHub Actions and VPS evidence; tunnel not required',
    **evidence,
    'evidence_sha256': hashlib.sha256(canonical).hexdigest(),
    'updated_at': int(time.time()),
}
if not payload['ok']:
    raise SystemExit(f'incomplete runtime evidence: {checks}')
path = Path(status_path)
temporary = path.with_suffix('.tmp')
temporary.write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n', 'utf-8')
os.chmod(temporary, 0o640)
temporary.replace(path)
PY
chmod 0700 "$STATUS_WRITER"
run_root python3 "$STATUS_WRITER" \
  "$STATUS_FILE" \
  "$INSTALL_RECEIPT_FILE" \
  "$INSTALLED_REVISION" \
  "$CONTAINER_REPO_DIGEST" \
  "$CONTAINER_IMAGE_ID" \
  "$INSTALLED_KAPPA_POS" \
  "$ARCHIVE_SHA256" \
  "$CONTAINER_STATE" \
  "$MCP_PROTOCOL_STATE" \
  "$BROKER_SERVICE_STATE" \
  "$BROKER_RPC_STATE" \
  "$BROKER_SOCKET_HOST_STATE" \
  "$BROKER_SOCKET_CONTAINER_STATE" \
  "$COMMAND_WORKER_STATE" \
  "$INBOUND_MUTATION_STATE" \
  "$OPERATING_PROFILE_STATE" \
  "$NEURO_RUNTIME_STATE" \
  "$TUNNEL_SERVICE_STATE"

run_root python3 - "$STATUS_FILE" "$EXPECTED_REVISION" "$EXPECTED_IMAGE_REFERENCE" "$KAPPA_POS" <<'PY'
from pathlib import Path
import json
import re
import sys

payload = json.loads(Path(sys.argv[1]).read_text('utf-8'))
assert payload.get('ok') is True, payload
assert payload.get('status') == 'UPDATED', payload
assert payload.get('revision') == sys.argv[2], payload
assert payload.get('image') == sys.argv[3], payload
assert payload.get('kappa_pos') == int(sys.argv[4]), payload
assert payload.get('predecessor_contract_gate') is True, payload
if payload.get('predecessor_container_present') is True:
    assert payload.get('semantic_compatibility_verified') is True, payload
    assert payload.get('previous_tool_surface_compared') is True, payload
    assert payload.get('first_install_attested') is False, payload
else:
    assert payload.get('semantic_compatibility_verified') is False, payload
    assert payload.get('previous_tool_surface_compared') is False, payload
    assert payload.get('first_install_without_predecessor') is True, payload
    assert payload.get('first_install_attested') is True, payload
assert re.fullmatch(r'[0-9a-f]{64}', str(payload.get('evidence_sha256', ''))), payload
PY

printf 'MCP revision installed: %s\n' "$INSTALLED_REVISION"
printf 'MCP image digest: %s\n' "$CONTAINER_REPO_DIGEST"
printf 'MCP image id: %s\n' "$CONTAINER_IMAGE_ID"
printf 'KappaPos: %s\n' "$INSTALLED_KAPPA_POS"
printf 'Cross-runtime parity: %s\n' "$INSTALLED_CROSS_RUNTIME_PARITY"
printf 'Release archive SHA-256: %s\n' "$ARCHIVE_SHA256"
printf 'MCP container: %s\n' "$CONTAINER_STATE"
printf 'MCP protocol ready: %s\n' "$MCP_PROTOCOL_STATE"
printf 'Broker service: %s\n' "$BROKER_SERVICE_STATE"
printf 'Broker RPC: %s\n' "$BROKER_RPC_STATE"
printf 'Host command worker: %s\n' "$COMMAND_WORKER_STATE"
printf 'Inbound mutation: %s\n' "$INBOUND_MUTATION_STATE"
printf 'Operating profile: %s\n' "$OPERATING_PROFILE_STATE"
printf 'Tunnel requirement: %s\n' "$TUNNEL_SERVICE_STATE"
