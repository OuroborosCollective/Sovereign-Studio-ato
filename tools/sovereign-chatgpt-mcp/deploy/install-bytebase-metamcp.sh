#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$SOURCE_DIR/../.." && pwd)"
BYTEBASE_ROOT="/opt/sovereign-bytebase"
METAMCP_ROOT="/opt/sovereign-metamcp"
MCP_ROOT="/opt/sovereign-chatgpt-tools"
MCP_TEMPLATE_ROOT="$MCP_ROOT/templates"
MCP_EXTENSION_ROOT="$MCP_ROOT/extensions"
EVIDENCE_ROOT="$MCP_ROOT/runtime-evidence"
BYTEBASE_ENV="$BYTEBASE_ROOT/.env"
METAMCP_ENV="$METAMCP_ROOT/.env"
BYTEBASE_SOURCE="${SOVEREIGN_BYTEBASE_IMAGE_SOURCE:-bytebase/bytebase:latest}"
METAMCP_SOURCE="${SOVEREIGN_METAMCP_IMAGE_SOURCE:-ghcr.io/metatool-ai/metamcp:latest}"
METAMCP_POSTGRES_SOURCE="${SOVEREIGN_METAMCP_POSTGRES_IMAGE_SOURCE:-postgres:16-alpine}"
FORCE_IMAGE_RERESOLVE="${SOVEREIGN_EXTERNAL_STACK_FORCE_IMAGE_RERESOLVE:-0}"
BROKER_SERVICE="sovereign-chatgpt-broker.service"
WORKER_SERVICE="sovereign-chatgpt-command-worker.service"

fail() {
  printf 'external stack install blocked: %s\n' "$*" >&2
  exit 1
}

require_root() {
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root on the Sovereign VPS"
}

require_tools() {
  local command
  for command in docker python3 openssl sha256sum git install systemctl; do
    command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
  done
  docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed"
}

require_control_plane_contract() {
  local broker worker
  broker="$(systemctl cat "$BROKER_SERVICE" 2>/dev/null || true)"
  worker="$(systemctl cat "$WORKER_SERVICE" 2>/dev/null || true)"
  [[ "$broker" == *"Environment=PYTHONPATH=$MCP_EXTENSION_ROOT"* ]] || fail "broker extension path is not installed from the reviewed MCP revision"
  [[ "$worker" == *"Environment=PYTHONPATH=$MCP_EXTENSION_ROOT"* ]] || fail "command worker extension path is not installed from the reviewed MCP revision"
  [[ "$worker" == *"$BYTEBASE_ROOT"* ]] || fail "command worker does not permit the Bytebase deploy root"
  [[ "$worker" == *"$METAMCP_ROOT"* ]] || fail "command worker does not permit the MetaMCP deploy root"
}

read_env_value() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

set_env_value() {
  local file="$1" key="$2" value="$3" temporary
  [[ "$key" =~ ^[A-Z0-9_]+$ ]] || fail "invalid environment key: $key"
  temporary="$(mktemp "${file}.XXXXXX")"
  if [[ -f "$file" ]]; then
    grep -v "^${key}=" "$file" > "$temporary" || true
  fi
  printf '%s=%s\n' "$key" "$value" >> "$temporary"
  chown root:root "$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$file"
}

resolve_immutable_image() {
  local source="$1" existing="$2" resolved
  if [[ "$FORCE_IMAGE_RERESOLVE" != "1" && "$existing" =~ @sha256:[0-9a-f]{64}$ ]]; then
    printf '%s' "$existing"
    return 0
  fi
  docker pull "$source" >/dev/null
  resolved="$(docker image inspect "$source" --format '{{json .RepoDigests}}' | python3 -c 'import json,sys; values=json.load(sys.stdin) or []; print(next((v for v in values if "@sha256:" in v), ""))')"
  [[ "$resolved" =~ @sha256:[0-9a-f]{64}$ ]] || fail "could not resolve immutable digest for $source"
  printf '%s' "$resolved"
}

ensure_secret() {
  local file="$1" key="$2" current
  current="$(read_env_value "$file" "$key")"
  if [[ "$current" =~ ^[A-Fa-f0-9]{64}$ ]]; then
    return 0
  fi
  set_env_value "$file" "$key" "$(openssl rand -hex 32)"
}

http_ready() {
  local url="$1"
  URL="$url" python3 - <<'PY'
import os
import urllib.error
import urllib.request

request = urllib.request.Request(os.environ["URL"], method="GET")
try:
    with urllib.request.urlopen(request, timeout=4) as response:
        code = int(response.status)
except urllib.error.HTTPError as exc:
    code = int(exc.code)
except Exception:
    raise SystemExit(1)
if code < 200 or code >= 500:
    raise SystemExit(1)
PY
}

wait_http() {
  local url="$1" attempts="${2:-90}" attempt
  for attempt in $(seq 1 "$attempts"); do
    if http_ready "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

compose_up() {
  local root="$1" env_file="$2"
  docker compose --project-name "$(basename "$root")" --project-directory "$root" --file "$root/docker-compose.yml" --env-file "$env_file" config >/dev/null
  docker compose --project-name "$(basename "$root")" --project-directory "$root" --file "$root/docker-compose.yml" --env-file "$env_file" up -d --remove-orphans
}

install_control_plane_extension() {
  local bytebase_template="$MCP_TEMPLATE_ROOT/sovereign-bytebase"
  local metamcp_template="$MCP_TEMPLATE_ROOT/sovereign-metamcp"
  install -d -m 0755 -o root -g root "$MCP_TEMPLATE_ROOT" "$MCP_EXTENSION_ROOT" "$bytebase_template" "$metamcp_template"
  install -m 0644 "$SOURCE_DIR/templates/sovereign-bytebase/docker-compose.yml" "$bytebase_template/docker-compose.yml"
  install -m 0644 "$SOURCE_DIR/templates/sovereign-metamcp/docker-compose.yml" "$metamcp_template/docker-compose.yml"
  install -m 0644 "$SOURCE_DIR/deploy/extensions/sitecustomize.py" "$MCP_EXTENSION_ROOT/sitecustomize.py"
  install -m 0644 "$SOURCE_DIR/deploy/extensions/sovereign_external_control_plane.py" "$MCP_EXTENSION_ROOT/sovereign_external_control_plane.py"
}

verify_broker_registration() {
  PYTHONPATH="$MCP_EXTENSION_ROOT:$MCP_ROOT/broker" python3 - <<'PY'
import json
import socket
import uuid

socket_path = "/run/sovereign-chatgpt-broker/operator.sock"
receipts = {}
for stack_id in ("sovereign-bytebase", "sovereign-metamcp"):
    request = {
        "request_id": str(uuid.uuid4()),
        "action": "managed_compose_stack_plan",
        "arguments": {"stack_id": stack_id},
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        client.connect(socket_path)
        client.sendall(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
        with client.makefile("rb") as handle:
            raw = handle.readline(1_000_001)
    if len(raw) > 1_000_000:
        raise SystemExit("broker response exceeds limit")
    response = json.loads(raw)
    result = response.get("result") or {}
    if result.get("ok") is not True or result.get("stackId") != stack_id or result.get("templateRegistered") is not True:
        raise SystemExit(f"broker did not register {stack_id}: {result.get('status')}")
    bundle = str(result.get("templateBundleSha256") or "")
    if len(bundle) != 64:
        raise SystemExit(f"broker returned invalid template hash for {stack_id}")
    receipts[stack_id] = {
        "status": result.get("status"),
        "templateBundleSha256": bundle,
        "composeWriteEnabled": bool(result.get("composeWriteEnabled")),
    }
print(json.dumps(receipts, sort_keys=True, separators=(",", ":")))
PY
}

require_root
require_tools
[[ "$FORCE_IMAGE_RERESOLVE" =~ ^[01]$ ]] || fail "SOVEREIGN_EXTERNAL_STACK_FORCE_IMAGE_RERESOLVE must be 0 or 1"
[[ -f "$SOURCE_DIR/templates/sovereign-bytebase/docker-compose.yml" ]] || fail "Bytebase compose template is missing"
[[ -f "$SOURCE_DIR/templates/sovereign-metamcp/docker-compose.yml" ]] || fail "MetaMCP compose template is missing"
[[ -f "$SOURCE_DIR/deploy/extensions/sitecustomize.py" ]] || fail "MCP sitecustomize extension is missing"
[[ -f "$SOURCE_DIR/deploy/extensions/sovereign_external_control_plane.py" ]] || fail "MCP external stack extension is missing"
require_control_plane_contract
docker network inspect supabase_default >/dev/null 2>&1 || fail "required Sovereign network supabase_default is missing"

install -d -m 0750 -o root -g root "$BYTEBASE_ROOT" "$METAMCP_ROOT"
install -d -m 0700 -o root -g root "$EVIDENCE_ROOT"
install -m 0644 "$SOURCE_DIR/templates/sovereign-bytebase/docker-compose.yml" "$BYTEBASE_ROOT/docker-compose.yml"
install -m 0644 "$SOURCE_DIR/templates/sovereign-metamcp/docker-compose.yml" "$METAMCP_ROOT/docker-compose.yml"
install_control_plane_extension
[[ -f "$BYTEBASE_ENV" ]] || install -m 0600 /dev/null "$BYTEBASE_ENV"
[[ -f "$METAMCP_ENV" ]] || install -m 0600 /dev/null "$METAMCP_ENV"
chown root:root "$BYTEBASE_ENV" "$METAMCP_ENV"
chmod 0600 "$BYTEBASE_ENV" "$METAMCP_ENV"

BYTEBASE_IMAGE="$(resolve_immutable_image "$BYTEBASE_SOURCE" "$(read_env_value "$BYTEBASE_ENV" SOVEREIGN_BYTEBASE_IMAGE)")"
METAMCP_IMAGE="$(resolve_immutable_image "$METAMCP_SOURCE" "$(read_env_value "$METAMCP_ENV" SOVEREIGN_METAMCP_IMAGE)")"
METAMCP_POSTGRES_IMAGE="$(resolve_immutable_image "$METAMCP_POSTGRES_SOURCE" "$(read_env_value "$METAMCP_ENV" SOVEREIGN_METAMCP_POSTGRES_IMAGE)")"
set_env_value "$BYTEBASE_ENV" SOVEREIGN_BYTEBASE_IMAGE "$BYTEBASE_IMAGE"
set_env_value "$METAMCP_ENV" SOVEREIGN_METAMCP_IMAGE "$METAMCP_IMAGE"
set_env_value "$METAMCP_ENV" SOVEREIGN_METAMCP_POSTGRES_IMAGE "$METAMCP_POSTGRES_IMAGE"
set_env_value "$METAMCP_ENV" METAMCP_POSTGRES_USER "metamcp_user"
set_env_value "$METAMCP_ENV" METAMCP_POSTGRES_DB "metamcp_db"
set_env_value "$METAMCP_ENV" SOVEREIGN_METAMCP_APP_URL "http://127.0.0.1:32832"
ensure_secret "$METAMCP_ENV" METAMCP_POSTGRES_PASSWORD
ensure_secret "$METAMCP_ENV" METAMCP_BETTER_AUTH_SECRET

compose_up "$BYTEBASE_ROOT" "$BYTEBASE_ENV"
compose_up "$METAMCP_ROOT" "$METAMCP_ENV"

wait_http "http://127.0.0.1:32831/" 120 || fail "Bytebase did not become HTTP-ready"
wait_http "http://127.0.0.1:32832/" 120 || fail "MetaMCP did not become HTTP-ready"

for container in sovereign-bytebase sovereign-metamcp sovereign-metamcp-postgres; do
  state="$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || true)"
  [[ "$state" == "running" ]] || fail "$container is not running"
done

systemctl restart "$BROKER_SERVICE" "$WORKER_SERVICE"
[[ "$(systemctl is-active "$BROKER_SERVICE")" == "active" ]] || fail "broker did not return active after extension install"
[[ "$(systemctl is-active "$WORKER_SERVICE")" == "active" ]] || fail "command worker did not return active after extension install"
BROKER_PLAN_RECEIPT="$(verify_broker_registration)"

REVISION="$(git -C "$REPO_ROOT" rev-parse HEAD)"
[[ "$REVISION" =~ ^[0-9a-f]{40}$ ]] || fail "repository revision readback is invalid"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RECEIPT="$EVIDENCE_ROOT/bytebase-metamcp-${REVISION}-${TIMESTAMP}.json"
export REVISION BYTEBASE_SOURCE METAMCP_SOURCE METAMCP_POSTGRES_SOURCE BYTEBASE_IMAGE METAMCP_IMAGE METAMCP_POSTGRES_IMAGE RECEIPT BROKER_PLAN_RECEIPT
python3 - <<'PY'
import hashlib
import json
import os
import subprocess
from pathlib import Path

containers = {}
for name in ("sovereign-bytebase", "sovereign-metamcp", "sovereign-metamcp-postgres"):
    raw = subprocess.check_output([
        "docker", "inspect", "--format",
        "{{json .State}}|{{json .Config.Image}}|{{json .Image}}|{{json .NetworkSettings.Networks}}",
        name,
    ], text=True).strip()
    state_raw, image_ref_raw, image_id_raw, networks_raw = raw.split("|", 3)
    state = json.loads(state_raw)
    containers[name] = {
        "running": bool(state.get("Running")),
        "status": str(state.get("Status") or ""),
        "imageReference": json.loads(image_ref_raw),
        "imageId": json.loads(image_id_raw),
        "networks": sorted((json.loads(networks_raw) or {}).keys()),
    }

payload = {
    "schema": "sovereign.external-control-plane-install-receipt.v2",
    "repositoryRevision": os.environ["REVISION"],
    "images": {
        "bytebase": {"source": os.environ["BYTEBASE_SOURCE"], "resolved": os.environ["BYTEBASE_IMAGE"]},
        "metamcp": {"source": os.environ["METAMCP_SOURCE"], "resolved": os.environ["METAMCP_IMAGE"]},
        "metamcpPostgres": {"source": os.environ["METAMCP_POSTGRES_SOURCE"], "resolved": os.environ["METAMCP_POSTGRES_IMAGE"]},
    },
    "containers": containers,
    "managedCompose": json.loads(os.environ["BROKER_PLAN_RECEIPT"]),
    "endpoints": {
        "bytebaseLoopback": "http://127.0.0.1:32831",
        "bytebaseMcpPath": "/mcp",
        "metamcpLoopback": "http://127.0.0.1:32832",
        "metamcpStreamableHttpPattern": "/metamcp/<endpoint>/mcp",
    },
    "dockerSocketDelegatedToMetaMCP": False,
    "secretsIncluded": False,
}
canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
payload["receiptSha256"] = hashlib.sha256(canonical).hexdigest()
Path(os.environ["RECEIPT"]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({
    "status": "EXTERNAL_CONTROL_PLANE_RUNTIME_READBACK_VERIFIED",
    "repositoryRevision": payload["repositoryRevision"],
    "managedStackIds": sorted(payload["managedCompose"]),
    "receipt": os.environ["RECEIPT"],
    "receiptSha256": payload["receiptSha256"],
    "secretsIncluded": False,
}, separators=(",", ":")))
PY
