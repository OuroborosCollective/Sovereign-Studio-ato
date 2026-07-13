#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SOURCE_DIR="${SOVEREIGN_MCP_SOURCE_DIR:-/opt/sovereign-operator-source}"
REQUEST_FILE="${SOVEREIGN_MCP_SELF_UPDATE_REQUEST:-/run/sovereign-chatgpt-broker/self-update.request.json}"
STATE_DIR="${SOVEREIGN_MCP_SELF_UPDATE_STATE_DIR:-/var/lib/sovereign-chatgpt-self-update}"
STATUS_FILE="$STATE_DIR/status.json"
INSTALLER="$SOURCE_DIR/tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
BROKER_ENV="/opt/sovereign-chatgpt-tools/broker.env"

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

recover_control_plane() {
  set +e
  systemctl restart sovereign-chatgpt-broker.service
  if [[ -f /opt/sovereign-chatgpt-tools/docker-compose.yml ]]; then
    BROKER_GID="$(getent group sovereign-mcp | cut -d: -f3)"
    if [[ "$BROKER_GID" =~ ^[0-9]+$ ]]; then
      BROKER_GID="$BROKER_GID" docker compose \
        --project-directory /opt/sovereign-chatgpt-tools \
        --file /opt/sovereign-chatgpt-tools/docker-compose.yml \
        up -d --no-build --force-recreate sovereign-chatgpt-mcp
    fi
  fi
  systemctl restart sovereign-openai-tunnel.service
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
write_status INSTALLING "$EXPECTED_REVISION" "installing private ChatGPT MCP and broker"
bash "$INSTALLER"

CURRENT_STAGE="verify_end_to_end_control_plane"
systemctl is-active --quiet sovereign-chatgpt-broker.service
[[ -S /run/sovereign-chatgpt-broker/operator.sock ]]
docker inspect sovereign-chatgpt-mcp --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}' | grep -qx 'running healthy'
docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock
docker exec sovereign-chatgpt-mcp python -c 'import server; status=server.broker.status(); assert status.get("status") == "BROKER_READY", status'
docker exec sovereign-chatgpt-mcp python /app/mcp_protocol_health.py --url http://127.0.0.1:8090/mcp --timeout-seconds 5
systemctl is-active --quiet sovereign-openai-tunnel.service

CURRENT_STAGE="completed"
write_status UPDATED "$EXPECTED_REVISION" "private ChatGPT MCP, broker RPC, protocol handshake and tunnel verified"
rm -f "$REQUEST_FILE"
