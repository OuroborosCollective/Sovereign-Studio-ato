#!/usr/bin/env bash
set -Eeuo pipefail

HOST_ROOT="/opt/sovereign-agent-workspaces"
BACKEND_ROOT="/var/lib/sovereign-agent/workspaces"
AGENT_ZERO_ROOT="/a0/sovereign-workspaces"
BACKEND_CONTAINER="sovereign-backend"
AGENT_ZERO_CONTAINER="agent-zero-xrev-agent-zero-1"
WORKSPACE_ID="agent-testfile-${GITHUB_RUN_ID:-manual}"
HOST_WORKSPACE="$HOST_ROOT/$WORKSPACE_ID"
BACKEND_REPO="$BACKEND_ROOT/$WORKSPACE_ID/repo"
AGENT_ZERO_REPO="$AGENT_ZERO_ROOT/$WORKSPACE_ID/repo"
TASK_RECEIPT="$(mktemp)"
cleanup() {
  rm -f -- "$TASK_RECEIPT"
  case "$HOST_WORKSPACE" in
    "$HOST_ROOT"/agent-testfile-*) rm -rf -- "$HOST_WORKSPACE" ;;
  esac
}
trap cleanup EXIT

fail() {
  printf 'AGENT_ZERO_TESTFILE_SMOKE_BLOCKED:%s\n' "$1" >&2
  exit 1
}

[[ "$(id -u)" -eq 0 ]] || fail "root_required"
docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || fail "backend_container_missing"
docker inspect "$AGENT_ZERO_CONTAINER" >/dev/null 2>&1 || fail "agent_zero_container_missing"

install -d -m 0770 -o 10001 -g 10001 "$HOST_WORKSPACE"
docker exec --user 10001:10001 "$BACKEND_CONTAINER" sh -eu -c "
  mkdir -p '$BACKEND_REPO'
  cd '$BACKEND_REPO'
  git init -q -b main
  git config user.email 'sovereign-testfile-smoke@invalid.example'
  git config user.name 'Sovereign Testfile Smoke'
  git commit -q --allow-empty -m baseline
"

docker exec --user 10001:10001 -i "$BACKEND_CONTAINER" python - "$WORKSPACE_ID" >"$TASK_RECEIPT" <<'PY'
from __future__ import annotations

import json
import sys
import time

from agent_runtime.agent_zero_a2a import (
    AgentZeroA2AClient,
    AgentZeroA2AError,
    AgentZeroA2ASubmitOutcomeUnknown,
)

workspace_id = sys.argv[1]
mission = (
    "Erstelle im Root des bereitgestellten Git-Worktrees genau eine leere reguläre Datei "
    "mit dem Namen testfile. Verändere keine andere Datei. Erzeuge keinen Commit und keinen Pull Request. "
    "Sobald testfile gespeichert ist, melde knapp: Auftrag abgeschlossen."
)
try:
    client = AgentZeroA2AClient.from_env()
    task = client.submit_repository_task(workspace_id=workspace_id, mission=mission)
except AgentZeroA2ASubmitOutcomeUnknown as exc:
    print(json.dumps({
        "ok": False,
        "status": "SUBMIT_OUTCOME_UNKNOWN",
        "failureFamily": exc.family,
        "taskId": None,
        "secretValuesReturned": False,
    }, sort_keys=True))
    raise SystemExit(2)
except AgentZeroA2AError as exc:
    print(json.dumps({
        "ok": False,
        "status": "SUBMIT_FAILED",
        "failureFamily": exc.family,
        "taskId": None,
        "secretValuesReturned": False,
    }, sort_keys=True))
    raise SystemExit(2)

task_id = task.task_id
state = task.state
deadline = time.monotonic() + 300
while state not in {"completed", "failed", "canceled", "rejected"} and time.monotonic() < deadline:
    time.sleep(2)
    try:
        task = client.get_task(task_id)
    except AgentZeroA2AError as exc:
        print(json.dumps({
            "ok": False,
            "status": "POLL_FAILED",
            "failureFamily": exc.family,
            "taskId": task_id,
            "secretValuesReturned": False,
        }, sort_keys=True))
        raise SystemExit(3)
    state = task.state

print(json.dumps({
    "ok": state == "completed",
    "status": "TASK_COMPLETED" if state == "completed" else "TASK_TERMINAL_NOT_COMPLETED",
    "taskId": task_id,
    "taskState": state,
    "secretValuesReturned": False,
}, sort_keys=True))
raise SystemExit(0 if state == "completed" else 4)
PY

python3 - "$TASK_RECEIPT" <<'PY'
from pathlib import Path
import json
import sys

payload = json.loads(Path(sys.argv[1]).read_text("utf-8"))
assert payload.get("ok") is True, payload
assert payload.get("status") == "TASK_COMPLETED", payload
assert payload.get("taskState") == "completed", payload
assert payload.get("secretValuesReturned") is False, payload
PY

test -f "$HOST_WORKSPACE/repo/testfile" || fail "host_testfile_missing"
test ! -L "$HOST_WORKSPACE/repo/testfile" || fail "host_testfile_symlink"
test "$(stat -c '%s' "$HOST_WORKSPACE/repo/testfile")" = "0" || fail "host_testfile_not_empty"

docker exec --user 10001:10001 "$BACKEND_CONTAINER" test -f "$BACKEND_REPO/testfile"   || fail "backend_testfile_missing"
docker exec --user 10001:10001 "$BACKEND_CONTAINER" test ! -L "$BACKEND_REPO/testfile"   || fail "backend_testfile_symlink"
test "$(docker exec --user 10001:10001 "$BACKEND_CONTAINER" stat -c '%s' "$BACKEND_REPO/testfile")" = "0"   || fail "backend_testfile_not_empty"

docker exec "$AGENT_ZERO_CONTAINER" test -f "$AGENT_ZERO_REPO/testfile"   || fail "agent_zero_testfile_missing"
docker exec "$AGENT_ZERO_CONTAINER" test ! -L "$AGENT_ZERO_REPO/testfile"   || fail "agent_zero_testfile_symlink"
test "$(docker exec "$AGENT_ZERO_CONTAINER" stat -c '%s' "$AGENT_ZERO_REPO/testfile")" = "0"   || fail "agent_zero_testfile_not_empty"

STATUS="$(docker exec --user 10001:10001 "$BACKEND_CONTAINER" git -C "$BACKEND_REPO" status --porcelain=v1 --untracked-files=all)"
test "$STATUS" = "?? testfile" || fail "unexpected_workspace_diff"

TASK_ID="$(python3 - "$TASK_RECEIPT" <<'PY'
from pathlib import Path
import json
import sys
print(json.loads(Path(sys.argv[1]).read_text("utf-8"))["taskId"])
PY
)"

printf '{"ok":true,"status":"AGENT_ZERO_TESTFILE_SMOKE_VERIFIED","taskId":"%s","taskState":"completed","workspaceId":"%s","changedFile":"testfile","fileSizeBytes":0,"hostReadbackVerified":true,"backendReadbackVerified":true,"agentZeroReadbackVerified":true,"gitStatusVerified":true,"cleanupScheduled":true,"secretValuesReturned":false}\n' "$TASK_ID" "$WORKSPACE_ID"
