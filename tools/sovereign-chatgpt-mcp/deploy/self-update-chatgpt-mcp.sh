#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SOURCE_DIR="${SOVEREIGN_MCP_SOURCE_DIR:-/opt/sovereign-operator-source}"
REQUEST_FILE="${SOVEREIGN_MCP_SELF_UPDATE_REQUEST:-/run/sovereign-chatgpt-broker/self-update.request.json}"
STATE_DIR="${SOVEREIGN_MCP_SELF_UPDATE_STATE_DIR:-/var/lib/sovereign-chatgpt-self-update}"
STATUS_FILE="$STATE_DIR/status.json"
INSTALLER="$SOURCE_DIR/tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
BROKER_ENV="/opt/sovereign-chatgpt-tools/broker.env"
SELF_UPDATE_TUNNEL_MODE="${SOVEREIGN_MCP_SELF_UPDATE_TUNNEL_MODE:-disabled}"

mkdir -p "$STATE_DIR"
chmod 0750 "$STATE_DIR"

write_status() {
  local status="$1"
  local revision="${2:-}"
  local detail="${3:-}"
  python3 - "$STATUS_FILE" "$status" "$revision" "$detail" <<'PY'
from pathlib import Path
import json
import os
import sys
import time

path = Path(sys.argv[1])
payload = {
    "ok": sys.argv[2] == "UPDATED",
    "status": sys.argv[2],
    "revision": sys.argv[3],
    "detail": sys.argv[4][:2000],
    "updated_at": int(time.time()),
}
temporary = path.with_suffix(".tmp")
temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", "utf-8")
os.chmod(temporary, 0o640)
temporary.replace(path)
PY
}

CURRENT_STAGE="initializing"

broker_rpc_ready() {
  python3 - <<'PY'
import json
import socket

payload = json.dumps(
    {"request_id": "broker-readiness-canary", "action": "broker_health", "arguments": {}},
    separators=(",", ":"),
).encode("utf-8") + b"\n"
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(2)
    client.connect("/run/sovereign-chatgpt-broker/operator.sock")
    client.sendall(payload)
    response = json.loads(client.recv(65536).split(b"\n", 1)[0].decode("utf-8"))
result = response.get("result") or {}
if result.get("status") != "BROKER_READY":
    raise SystemExit(1)
PY
}

wait_for_broker_ready() {
  for attempt in $(seq 1 30); do
    if [[ -S /run/sovereign-chatgpt-broker/operator.sock ]] && broker_rpc_ready >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

recover_control_plane() {
  set +e
  systemctl restart sovereign-chatgpt-command-worker.service
  systemctl restart sovereign-chatgpt-broker.service
  wait_for_broker_ready || true
  if [[ -f /opt/sovereign-chatgpt-tools/docker-compose.yml ]]; then
    BROKER_GID="$(getent group sovereign-mcp | cut -d: -f3)"
    if [[ "$BROKER_GID" =~ ^[0-9]+$ ]]; then
      BROKER_GID="$BROKER_GID" docker compose \
        --project-directory /opt/sovereign-chatgpt-tools \
        --file /opt/sovereign-chatgpt-tools/docker-compose.yml \
        up -d --no-build --force-recreate sovereign-chatgpt-mcp
    fi
  fi
  if [[ "$SELF_UPDATE_TUNNEL_MODE" == "required" ]]; then
    systemctl restart sovereign-openai-tunnel.service
  fi
  set -e
}

on_error() {
  local exit_code="$?"
  trap - ERR
  recover_control_plane
  write_status FAILED "${EXPECTED_REVISION:-}" "stage=${CURRENT_STAGE}; self-update command failed; recovery attempted"
  exit "$exit_code"
}
trap on_error ERR

[[ -f "$REQUEST_FILE" ]] || { write_status FAILED "" "request file missing"; exit 1; }
[[ -d "$SOURCE_DIR/.git" ]] || { write_status FAILED "" "source repository missing"; exit 1; }
[[ -f "$BROKER_ENV" ]] || { write_status FAILED "" "broker environment missing"; exit 1; }
[[ "$SELF_UPDATE_TUNNEL_MODE" =~ ^(disabled|required)$ ]] || {
  write_status FAILED "" "SOVEREIGN_MCP_SELF_UPDATE_TUNNEL_MODE must be disabled or required"
  exit 1
}

EXPECTED_REVISION="$(python3 - "$REQUEST_FILE" <<'PY'
import json
import re
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text("utf-8"))
revision = str(payload.get("expected_revision") or "").strip().lower()
if not re.fullmatch(r"[0-9a-f]{40}", revision):
    raise SystemExit("invalid expected revision")
print(revision)
PY
)"

TOKEN="$(sed -n 's/^GITHUB_TOKEN=//p' "$BROKER_ENV" | tail -n 1)"
ASKPASS_DIR="$(mktemp -d)"
trap 'rm -rf "$ASKPASS_DIR"' EXIT
cat > "$ASKPASS_DIR/askpass.sh" <<'SH'
#!/bin/sh
case "$1" in
  *Username*) echo x-access-token ;;
  *Password*) printf '%s' "$GITHUB_TOKEN" ;;
esac
SH
chmod 0700 "$ASKPASS_DIR/askpass.sh"

export GITHUB_TOKEN="$TOKEN"
export GIT_ASKPASS="$ASKPASS_DIR/askpass.sh"
export GIT_TERMINAL_PROMPT=0

CURRENT_STAGE="fetch_confirmed_revision"
write_status RUNNING "$EXPECTED_REVISION" "fetching confirmed main revision"
cd "$SOURCE_DIR"
git fetch origin main
ACTUAL_REVISION="$(git rev-parse origin/main)"
[[ "$ACTUAL_REVISION" == "$EXPECTED_REVISION" ]] || {
  write_status BLOCKED "$EXPECTED_REVISION" "origin/main does not match expected revision"
  exit 1
}

CURRENT_STAGE="checkout_confirmed_revision"
git checkout main
git reset --hard "$EXPECTED_REVISION"
[[ -x "$INSTALLER" ]] || chmod 0750 "$INSTALLER"

CURRENT_STAGE="install_control_plane"
write_status INSTALLING "$EXPECTED_REVISION" "installing private ChatGPT MCP and broker from the CI-built immutable image"
INSTALL_LOG="$(mktemp)"
if ! SOVEREIGN_MCP_EXPECTED_REVISION="$EXPECTED_REVISION" \
  SOVEREIGN_MCP_TUNNEL_MODE="$SELF_UPDATE_TUNNEL_MODE" \
  bash "$INSTALLER" >"$INSTALL_LOG" 2>&1; then
  INSTALL_DETAIL="$(grep -E '^install blocked: stage=' "$INSTALL_LOG" | tail -n 1 | tr -d '\r\n' | cut -c1-1200 || true)"
  recover_control_plane
  write_status FAILED "$EXPECTED_REVISION" "stage=${CURRENT_STAGE}; ${INSTALL_DETAIL:-installer failed without bounded stage evidence}; recovery attempted"
  rm -f "$INSTALL_LOG"
  exit 1
fi
rm -f "$INSTALL_LOG"

CURRENT_STAGE="verify_end_to_end_control_plane"
systemctl is-active --quiet sovereign-chatgpt-command-worker.service
systemctl is-active --quiet sovereign-chatgpt-broker.service
wait_for_broker_ready
docker inspect sovereign-chatgpt-mcp --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}' | grep -qx 'running healthy'
docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock
docker exec sovereign-chatgpt-mcp python -c 'import server; status=server.broker.status(); assert status.get("status") == "BROKER_READY", status'
docker exec sovereign-chatgpt-mcp python /app/mcp_protocol_health.py --url http://127.0.0.1:8090/mcp --timeout-seconds 5
if [[ "$SELF_UPDATE_TUNNEL_MODE" == "required" ]]; then
  CURRENT_STAGE="verify_required_tunnel"
  systemctl is-active --quiet sovereign-openai-tunnel.service
fi

CURRENT_STAGE="completed"
if [[ "$SELF_UPDATE_TUNNEL_MODE" == "required" ]]; then
  COMPLETION_DETAIL="private ChatGPT MCP, host command worker, broker RPC, protocol handshake and required tunnel verified"
else
  COMPLETION_DETAIL="private ChatGPT MCP, host command worker, broker RPC and protocol handshake verified; tunnel not required"
fi
write_status UPDATED "$EXPECTED_REVISION" "$COMPLETION_DETAIL"
rm -f "$REQUEST_FILE"
