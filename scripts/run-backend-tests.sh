#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
VENV_DIR="${BACKEND_TEST_VENV:-$ROOT_DIR/.venv-backend-tests}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install --requirement "$ROOT_DIR/backend/requirements-test.txt"
"$VENV_DIR/bin/python" -m pip check
"$VENV_DIR/bin/python" "$ROOT_DIR/scripts/check-backend-python-runtime.py"

cd "$ROOT_DIR/backend"
exec "$VENV_DIR/bin/python" -m pytest "$@"
