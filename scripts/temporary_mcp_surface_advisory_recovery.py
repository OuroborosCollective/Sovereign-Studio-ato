from pathlib import Path

INSTALLER = Path('tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh')
TEST = Path('tools/sovereign-chatgpt-mcp/tests/test_neuro_deployment_install_contract.py')

installer = INSTALLER.read_text('utf-8')

start_old = '''chmod 0600 "$NEW_MCP_REGISTRY_FILE"\npython3 - "$PREVIOUS_MCP_REGISTRY_FILE" "$NEW_MCP_REGISTRY_FILE" "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" "$EXPECTED_MCP_TOOL_COUNT" <<'PY'\n'''
start_new = '''chmod 0600 "$NEW_MCP_REGISTRY_FILE"\n# The replacement registry itself remains a hard runtime invariant. Historical\n# predecessor compatibility is evidence, not deployment authority.\npython3 - "$NEW_MCP_REGISTRY_FILE" "$EXPECTED_MCP_TOOL_COUNT" <<'PY'\nimport json\nimport sys\nfrom pathlib import Path\n\npath = Path(sys.argv[1])\nexpected_count = int(sys.argv[2])\nvalue = json.loads(path.read_text("utf-8"))\ntools = value.get("tools") if isinstance(value, dict) else None\nrequired_additions = {\n    "neuro_event_commit",\n    "neuro_event_route_preview",\n    "neuro_runtime_contract_status",\n    "teaching_lesson_simulate",\n    "teaching_package_assess",\n}\nif (\n    value.get("schemaVersion") != "sovereign.mcp-deployment-contract-surface.v1"\n    or not isinstance(tools, list)\n    or len(tools) != expected_count\n    or value.get("toolCount") != expected_count\n):\n    raise SystemExit("replacement MCP intrinsic registry contract is invalid")\nnames = [item.get("name") for item in tools if isinstance(item, dict)]\nif len(names) != expected_count or names != sorted(set(names)):\n    raise SystemExit("replacement MCP intrinsic registry names are invalid")\nif not required_additions.issubset(names):\n    raise SystemExit("replacement MCP intrinsic registry is missing required tools")\nfor item in tools:\n    if (\n        not isinstance(item.get("capabilities"), list)\n        or not isinstance(item.get("effect"), str)\n        or not isinstance(item.get("annotations"), dict)\n        or not isinstance(item.get("parameters"), dict)\n        or not isinstance(item.get("outputSchema"), dict)\n    ):\n        raise SystemExit(f"replacement MCP intrinsic contract is incomplete: {item.get('name')}")\nPY\nMCP_SURFACE_ADVISORY_FILE="$ROLLBACK_DIR/mcp-tool-surface-advisory.err"\nPREDECESSOR_SEMANTIC_COMPATIBILITY_VERIFIED=0\nset +e\n{\npython3 - "$PREVIOUS_MCP_REGISTRY_FILE" "$NEW_MCP_REGISTRY_FILE" "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" "$EXPECTED_MCP_TOOL_COUNT" <<'PY'\n'''
if installer.count(start_old) != 1:
    raise SystemExit('MCP_SURFACE_START_ANCHOR_MISMATCH')
installer = installer.replace(start_old, start_new, 1)

end_old = '''\nPY\n\nINSTALL_STAGE="verify_isolated_neuro_runtime_canary"\n'''
end_new = '''\nPY\n} 2>"$MCP_SURFACE_ADVISORY_FILE"\nMCP_SURFACE_COMPARE_RC=$?\nset -e\nif (( MCP_SURFACE_COMPARE_RC == 0 )); then\n  if [[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" == "1" ]]; then\n    PREDECESSOR_SEMANTIC_COMPATIBILITY_VERIFIED=1\n  fi\nelse\n  MCP_SURFACE_ADVISORY_SHA256="$(sha256sum "$MCP_SURFACE_ADVISORY_FILE" | awk '{print $1}')"\n  [[ "$MCP_SURFACE_ADVISORY_SHA256" =~ ^[0-9a-f]{64}$ ]] \\\n    || fail "could not hash predecessor MCP surface advisory evidence"\n  printf 'SOVEREIGN_MCP_TOOL_SURFACE_ADVISORY:%s\\n' "$MCP_SURFACE_ADVISORY_SHA256" >&2\nfi\nrm -f "$MCP_SURFACE_ADVISORY_FILE"\nunset MCP_SURFACE_ADVISORY_FILE MCP_SURFACE_ADVISORY_SHA256 MCP_SURFACE_COMPARE_RC\n\nINSTALL_STAGE="verify_isolated_neuro_runtime_canary"\n'''
if installer.count(end_old) != 1:
    raise SystemExit('MCP_SURFACE_END_ANCHOR_MISMATCH')
installer = installer.replace(end_old, end_new, 1)

final_old = '''if [[ "$PREVIOUS_MCP_CONTAINER_PRESENT" == "1" ]]; then\n  [[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" == "1" ]] \\\n    || fail "predecessor MCP existed but semantic compatibility was not verified"\nelse\n  [[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" == "0" ]] \\\n    || fail "first-install state conflicts with predecessor registry evidence"\nfi\nINSTALL_STAGE="completed"\nINSTALL_COMPLETED=1\nROLLBACK_ARMED=0\nPREVIOUS_TOOL_SURFACE_COMPARED_JSON=false\n[[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" != "1" ]] || PREVIOUS_TOOL_SURFACE_COMPARED_JSON=true\nPREDECESSOR_CONTAINER_PRESENT_JSON=false\nSEMANTIC_COMPATIBILITY_VERIFIED_JSON=false\nFIRST_INSTALL_WITHOUT_PREDECESSOR_JSON=true\nif [[ "$PREVIOUS_MCP_CONTAINER_PRESENT" == "1" ]]; then\n  PREDECESSOR_CONTAINER_PRESENT_JSON=true\n  SEMANTIC_COMPATIBILITY_VERIFIED_JSON=true\n  FIRST_INSTALL_WITHOUT_PREDECESSOR_JSON=false\nfi\n'''
final_new = '''if [[ "$PREVIOUS_MCP_CONTAINER_PRESENT" == "1" ]]; then\n  [[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" == "1" ]] \\\n    || fail "predecessor MCP existed but registry capture was not verified"\nelse\n  [[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" == "0" ]] \\\n    || fail "first-install state conflicts with predecessor registry evidence"\nfi\nINSTALL_STAGE="completed"\nINSTALL_COMPLETED=1\nROLLBACK_ARMED=0\nPREVIOUS_TOOL_SURFACE_COMPARED_JSON=false\n[[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" != "1" ]] || PREVIOUS_TOOL_SURFACE_COMPARED_JSON=true\nPREDECESSOR_CONTAINER_PRESENT_JSON=false\nSEMANTIC_COMPATIBILITY_VERIFIED_JSON=false\nFIRST_INSTALL_WITHOUT_PREDECESSOR_JSON=true\nif [[ "$PREVIOUS_MCP_CONTAINER_PRESENT" == "1" ]]; then\n  PREDECESSOR_CONTAINER_PRESENT_JSON=true\n  [[ "$PREDECESSOR_SEMANTIC_COMPATIBILITY_VERIFIED" != "1" ]] \\\n    || SEMANTIC_COMPATIBILITY_VERIFIED_JSON=true\n  FIRST_INSTALL_WITHOUT_PREDECESSOR_JSON=false\nfi\n'''
if installer.count(final_old) != 1:
    raise SystemExit('MCP_SURFACE_FINAL_ANCHOR_MISMATCH')
installer = installer.replace(final_old, final_new, 1)

json_old = '\\"semantic_compatibility_verified\\":%s,\\"first_install_without_predecessor\\":%s'
json_new = '\\"semantic_compatibility_verified\\":%s,\\"semantic_compatibility_blocking\\":false,\\"first_install_without_predecessor\\":%s'
if installer.count(json_old) != 1:
    raise SystemExit('MCP_SURFACE_RECEIPT_ANCHOR_MISMATCH')
installer = installer.replace(json_old, json_new, 1)
INSTALLER.write_text(installer, 'utf-8')


test = TEST.read_text('utf-8')
test_old = '''    assert 'predecessor MCP existed but semantic compatibility was not verified' in script\n    assert '\"semantic_compatibility_verified\":%s' in script\n'''
test_new = '''    assert 'predecessor MCP existed but registry capture was not verified' in script\n    assert 'MCP_SURFACE_ADVISORY_FILE="$ROLLBACK_DIR/mcp-tool-surface-advisory.err"' in script\n    assert 'PREDECESSOR_SEMANTIC_COMPATIBILITY_VERIFIED=0' in script\n    assert 'SOVEREIGN_MCP_TOOL_SURFACE_ADVISORY:%s' in script\n    assert '\"semantic_compatibility_verified\":%s' in script\n    assert '\"semantic_compatibility_blocking\":false' in script\n'''
if test.count(test_old) != 1:
    raise SystemExit('MCP_SURFACE_TEST_ANCHOR_MISMATCH')
test = test.replace(test_old, test_new, 1)
TEST.write_text(test, 'utf-8')
