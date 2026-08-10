#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "CODESPACE_BOOTSTRAP=FAIL $*" >&2
  exit 1
}

command -v node >/dev/null 2>&1 || fail "node is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"
command -v java >/dev/null 2>&1 || fail "java is unavailable"
command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI is unavailable"
command -v corepack >/dev/null 2>&1 || fail "corepack is unavailable"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" == "22" ]] || fail "expected Node 22, got $(node --version)"

PYTHON_MM="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
[[ "$PYTHON_MM" == "3.11" ]] || fail "expected Python 3.11, got $(python --version 2>&1)"

JAVA_VERSION="$(java -version 2>&1 | head -n 1)"
[[ "$JAVA_VERSION" == *'"17.'* || "$JAVA_VERSION" == *'"17"'* ]] || fail "expected Java 17, got $JAVA_VERSION"

corepack enable
corepack prepare pnpm@9.12.2 --activate
[[ "$(pnpm --version)" == "9.12.2" ]] || fail "pnpm contract mismatch: $(pnpm --version)"

pnpm install --frozen-lockfile

BACKEND_VENV="$ROOT/.venv-backend-tests"
MCP_VENV="$ROOT/.venv-mcp-tests"

python -m venv "$BACKEND_VENV"
"$BACKEND_VENV/bin/python" -m pip install -r backend/requirements-test.txt
"$BACKEND_VENV/bin/python" scripts/check-backend-python-runtime.py

python -m venv "$MCP_VENV"
"$MCP_VENV/bin/python" -m pip install -r tools/sovereign-chatgpt-mcp/requirements.txt
"$MCP_VENV/bin/python" - <<'PY'
import importlib.metadata
import mcp
import pytest

assert importlib.metadata.version("pytest") == "8.4.1"
print("MCP_PYTHON_RUNTIME=PASS pytest=8.4.1")
PY

# Browser dependencies are installed once at Codespace creation so Playwright
# smoke/e2e tests can run without mutating production containers.
pnpm exec playwright install --with-deps chromium

printf '%s\n' \
  "CODESPACE_BOOTSTRAP=PASS" \
  "node=$(node --version)" \
  "pnpm=$(pnpm --version)" \
  "python=$(python --version 2>&1)" \
  "java=$JAVA_VERSION" \
  "backend_venv=$BACKEND_VENV" \
  "mcp_venv=$MCP_VENV"
