#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PY="$ROOT/.venv-backend-tests/bin/python"
MCP_PY="$ROOT/.venv-mcp-tests/bin/python"
PROFILE="${1:-smoke}"

[[ -x "$BACKEND_PY" ]] || {
  echo "Missing backend virtualenv. Run: bash .devcontainer/bootstrap.sh" >&2
  exit 1
}
[[ -x "$MCP_PY" ]] || {
  echo "Missing MCP virtualenv. Run: bash .devcontainer/bootstrap.sh" >&2
  exit 1
}

backend_runtime_smoke() {
  "$BACKEND_PY" scripts/check-backend-python-runtime.py
  "$BACKEND_PY" -m pytest backend/tests/test_backend_python_runtime_contract.py -q
}

mcp_runtime_smoke() {
  "$MCP_PY" -m pytest \
    tools/sovereign-chatgpt-mcp/tests/test_operating_profile.py \
    tools/sovereign-chatgpt-mcp/tests/test_install_contract.py \
    -q
}

agent_runtime_suite() {
  "$BACKEND_PY" -m pytest \
    backend/tests/test_agent_runtime_no_openhands_required.py \
    backend/tests/test_agent_runtime_e2e.py \
    -v
  PATH="$ROOT/.venv-backend-tests/bin:$PATH" pnpm run test:agent-runtime:frontend
  "$MCP_PY" -m pytest \
    tools/sovereign-chatgpt-mcp/tests/test_runtime_production_flow.py \
    tools/sovereign-chatgpt-mcp/tests/test_registry_runtime_evidence.py \
    -q
}

case "$PROFILE" in
  smoke)
    backend_runtime_smoke
    mcp_runtime_smoke
    PATH="$ROOT/.venv-backend-tests/bin:$PATH" pnpm run type-check
    ;;
  agent)
    backend_runtime_smoke
    mcp_runtime_smoke
    agent_runtime_suite
    ;;
  browser)
    PATH="$ROOT/.venv-backend-tests/bin:$PATH" pnpm run test:e2e
    ;;
  full)
    backend_runtime_smoke
    mcp_runtime_smoke
    agent_runtime_suite
    PATH="$ROOT/.venv-backend-tests/bin:$PATH" pnpm run verify
    "$MCP_PY" -m pytest tools/sovereign-chatgpt-mcp/tests -q
    ;;
  *)
    echo "Unknown profile '$PROFILE'. Use: smoke | agent | browser | full" >&2
    exit 2
    ;;
esac

printf 'CODESPACE_TEST_PROFILE=PASS profile=%s\n' "$PROFILE"
