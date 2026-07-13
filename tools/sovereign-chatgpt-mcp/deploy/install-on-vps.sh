#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="/opt/sovereign-chatgpt-tools"
BIN_DIR="$INSTALL_ROOT/bin"
BROKER_DIR="$INSTALL_ROOT/broker"
DOCKER_AUTH_DIR="$INSTALL_ROOT/docker-auth"
WORKSPACE_DIR="$INSTALL_ROOT/workspaces"
COMMAND_QUEUE_DIR="$INSTALL_ROOT/command-queue"
ANDROID_SDK_DIR="/opt/android-sdk"
ENV_FILE="$INSTALL_ROOT/.env"
GHCR_ENV="$INSTALL_ROOT/.ghcr.env"
TUNNEL_ENV="$INSTALL_ROOT/tunnel.env"
BROKER_ENV="$INSTALL_ROOT/broker.env"
BROKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-broker.service"
COMMAND_WORKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-command-worker.service"
SELF_UPDATE_SERVICE="/etc/systemd/system/sovereign-chatgpt-mcp-self-update.service"
TUNNEL_SERVICE="/etc/systemd/system/sovereign-openai-tunnel.service"
MCP_UID="10001"
MCP_GID="10001"
MCP_HOST_PORT="8090"
MCP_IMAGE_REPOSITORY="${SOVEREIGN_MCP_IMAGE_REPOSITORY:-ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp}"
EXPECTED_REVISION="${SOVEREIGN_MCP_EXPECTED_REVISION:-}"
INSTALL_STAGE="initializing"
INSTALL_FAILURE_REASON=""
INSTALL_COMPLETED=0
ROLLBACK_ARMED=0
ROLLBACK_DIR=""
ROLLBACK_MANIFEST=""

fail() {
  INSTALL_FAILURE_REASON="$*"
  exit 1
}

read_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

set_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text("utf-8").splitlines() if path.exists() else []
out = []
replaced = False
for line in lines:
    if line.startswith(key + "="):
        out.append(f"{key}={value}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"{key}={value}")
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text("\n".join(out) + "\n", "utf-8")
os.chmod(temporary, 0o600)
temporary.replace(path)
PY
}

backup_control_plane_file() {
  local target="$1"
  local key
  [[ -n "$ROLLBACK_DIR" && -n "$ROLLBACK_MANIFEST" ]] || fail "rollback storage is not initialized"
  if grep -Fqx "$target" "$ROLLBACK_MANIFEST.paths" 2>/dev/null; then
    return 0
  fi
  printf '%s\n' "$target" >> "$ROLLBACK_MANIFEST.paths"
  key="$(printf '%s' "$target" | sha256sum | awk '{print $1}')"
  if [[ -e "$target" || -L "$target" ]]; then
    cp -a "$target" "$ROLLBACK_DIR/$key"
    printf '%s\t%s\n' "$target" "$key" >> "$ROLLBACK_MANIFEST"
  else
    printf '%s\t%s\n' "$target" "__MISSING__" >> "$ROLLBACK_MANIFEST"
  fi
}

restore_control_plane_files() {
  [[ "$ROLLBACK_ARMED" == "1" && -f "$ROLLBACK_MANIFEST" ]] || return 0
  while IFS=$'\t' read -r target key; do
    [[ -n "$target" && -n "$key" ]] || continue
    if [[ "$key" == "__MISSING__" ]]; then
      rm -f "$target"
      continue
    fi
    mkdir -p "$(dirname "$target")"
    rm -f "$target"
    cp -a "$ROLLBACK_DIR/$key" "$target"
  done < "$ROLLBACK_MANIFEST"
}

recover_previous_control_plane() {
  set +e
  restore_control_plane_files
  systemctl daemon-reload >/dev/null 2>&1
  systemctl restart sovereign-chatgpt-command-worker.service >/dev/null 2>&1
  systemctl restart sovereign-chatgpt-broker.service >/dev/null 2>&1
  if [[ -f "$INSTALL_ROOT/docker-compose.yml" && -f "$ENV_FILE" ]]; then
    local rollback_gid
    rollback_gid="$(getent group sovereign-mcp | cut -d: -f3)"
    if [[ "$rollback_gid" =~ ^[0-9]+$ ]]; then
      BROKER_GID="$rollback_gid" docker compose \
        --project-directory "$INSTALL_ROOT" \
        --file "$INSTALL_ROOT/docker-compose.yml" \
        up -d --no-build --force-recreate sovereign-chatgpt-mcp >/dev/null 2>&1
    fi
  fi
  systemctl restart sovereign-openai-tunnel.service >/dev/null 2>&1
  set -e
}

on_installer_exit() {
  local exit_code="$?"
  trap - EXIT
  if [[ "$exit_code" -eq 0 && "$INSTALL_COMPLETED" == "1" ]]; then
    [[ -z "$ROLLBACK_DIR" ]] || rm -rf "$ROLLBACK_DIR"
    exit 0
  fi
  [[ "$exit_code" -ne 0 ]] || exit_code=1
  recover_previous_control_plane
  printf 'install blocked: stage=%s exit=%s reason=%s rollback_attempted=%s\n' \
    "$INSTALL_STAGE" "$exit_code" "${INSTALL_FAILURE_REASON:-unexpected command failure}" "$ROLLBACK_ARMED" >&2
  [[ -z "$ROLLBACK_DIR" ]] || rm -rf "$ROLLBACK_DIR"
  exit "${exit_code:-1}"
}
trap on_installer_exit EXIT

port_listener_evidence() {
  ss -H -ltnp 2>/dev/null | awk -v suffix=":$MCP_HOST_PORT" '$4 ~ suffix "$" {print}'
}

INSTALL_STAGE="preflight"
[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root on the VPS"
[[ "$EXPECTED_REVISION" =~ ^[0-9a-f]{40}$ ]] || fail "SOVEREIGN_MCP_EXPECTED_REVISION must be a full commit SHA"
[[ "$MCP_IMAGE_REPOSITORY" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+$ ]] || fail "SOVEREIGN_MCP_IMAGE_REPOSITORY is invalid"
for command in docker systemctl python3 git ss openssl sha256sum; do
  command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed"
[[ -S /var/run/docker.sock ]] || fail "docker socket is missing"

getent group sovereign-mcp >/dev/null 2>&1 || groupadd --system sovereign-mcp
install -d -m 0750 "$INSTALL_ROOT" "$BIN_DIR" "$BROKER_DIR"
install -d -m 0755 "$ANDROID_SDK_DIR"
install -d -m 0770 -o root -g sovereign-mcp "$COMMAND_QUEUE_DIR" "$COMMAND_QUEUE_DIR/inbox" "$COMMAND_QUEUE_DIR/processing" "$COMMAND_QUEUE_DIR/outbox"
install -d -m 0770 -o "$MCP_UID" -g "$MCP_GID" "$WORKSPACE_DIR"
chown -R "$MCP_UID:$MCP_GID" "$WORKSPACE_DIR"
chmod 0770 "$WORKSPACE_DIR"

INSTALL_STAGE="backup_existing_control_plane"
ROLLBACK_DIR="$(mktemp -d "$INSTALL_ROOT/.control-plane-backup.XXXXXX")"
chmod 0700 "$ROLLBACK_DIR"
ROLLBACK_MANIFEST="$ROLLBACK_DIR/manifest.tsv"
: > "$ROLLBACK_MANIFEST"
: > "$ROLLBACK_MANIFEST.paths"
backup_control_plane_file "$ENV_FILE"
backup_control_plane_file "$BROKER_ENV"
backup_control_plane_file "$BROKER_SERVICE"
backup_control_plane_file "$COMMAND_WORKER_SERVICE"
backup_control_plane_file "$SELF_UPDATE_SERVICE"
backup_control_plane_file "$TUNNEL_SERVICE"
ROLLBACK_ARMED=1

INSTALL_STAGE="copy_control_plane_files"
for file in Dockerfile requirements.txt policy.py runtime.py database.py command_contract.py command_queue.py broker_client.py owner_input_client.py self_heal.py android_hardening.py android_validation_router.py mcp_protocol_health.py server.py tool_extensions.py launcher.py docker-compose.yml; do
  backup_control_plane_file "$INSTALL_ROOT/$file"
  install -m 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file"
done

for file in broker.py command_contract.py command_queue.py command_worker.py operations.py admin_mode.py github_admin.py self_update.py policy.py self_heal.py; do
  backup_control_plane_file "$BROKER_DIR/$file"
done
for file in deploy-sovereign-backend rollback-sovereign-backend bootstrap-database install-secure-tunnel self-update-chatgpt-mcp; do
  backup_control_plane_file "$BIN_DIR/$file"
done

install -m 0640 "$SOURCE_DIR/broker.py" "$BROKER_DIR/broker.py"
install -m 0640 "$SOURCE_DIR/command_contract.py" "$BROKER_DIR/command_contract.py"
install -m 0640 "$SOURCE_DIR/command_queue.py" "$BROKER_DIR/command_queue.py"
install -m 0640 "$SOURCE_DIR/command_worker.py" "$BROKER_DIR/command_worker.py"
install -m 0640 "$SOURCE_DIR/operations.py" "$BROKER_DIR/operations.py"
install -m 0640 "$SOURCE_DIR/admin_mode.py" "$BROKER_DIR/admin_mode.py"
install -m 0640 "$SOURCE_DIR/github_admin.py" "$BROKER_DIR/github_admin.py"
install -m 0640 "$SOURCE_DIR/self_update.py" "$BROKER_DIR/self_update.py"
install -m 0640 "$SOURCE_DIR/policy.py" "$BROKER_DIR/policy.py"
install -m 0640 "$SOURCE_DIR/self_heal.py" "$BROKER_DIR/self_heal.py"
install -m 0750 "$SOURCE_DIR/deploy/deploy-sovereign-backend" "$BIN_DIR/deploy-sovereign-backend"
install -m 0750 "$SOURCE_DIR/deploy/rollback-sovereign-backend" "$BIN_DIR/rollback-sovereign-backend"
install -m 0750 "$SOURCE_DIR/deploy/bootstrap-database.sh" "$BIN_DIR/bootstrap-database"
install -m 0750 "$SOURCE_DIR/deploy/install-secure-tunnel.sh" "$BIN_DIR/install-secure-tunnel"
install -m 0750 "$SOURCE_DIR/deploy/self-update-chatgpt-mcp.sh" "$BIN_DIR/self-update-chatgpt-mcp"
install -m 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-broker.service" "$BROKER_SERVICE"
install -m 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-command-worker.service" "$COMMAND_WORKER_SERVICE"
install -m 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-mcp-self-update.service" "$SELF_UPDATE_SERVICE"
install -m 0644 "$SOURCE_DIR/deploy/sovereign-openai-tunnel.service" "$TUNNEL_SERVICE"
grep -q '^ExecStartPre=/usr/bin/python3 /opt/sovereign-chatgpt-tools/mcp_protocol_health.py ' "$TUNNEL_SERVICE" \
  || fail "installed tunnel unit does not use the shared MCP protocol checker"
grep -q '^Restart=on-failure$' "$TUNNEL_SERVICE" || fail "installed tunnel unit has an unsafe restart policy"
grep -q '^StartLimitBurst=3$' "$TUNNEL_SERVICE" || fail "installed tunnel unit has no bounded restart limit"
if grep -Eq 'c[u]rl[[:space:]]' "$TUNNEL_SERVICE"; then
  fail "installed tunnel unit still contains a curl-based MCP probe"
fi
chown -R root:sovereign-mcp "$BROKER_DIR" "$BIN_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$SOURCE_DIR/.env.example" "$INSTALL_ROOT/.env.example"
  install -m 0600 "$SOURCE_DIR/.ghcr.env.example" "$INSTALL_ROOT/.ghcr.env.example"
  install -m 0600 "$SOURCE_DIR/.tunnel.env.example" "$INSTALL_ROOT/tunnel.env.example"
  fail "create $ENV_FILE from $INSTALL_ROOT/.env.example and fill it only on the VPS"
fi
chmod 0600 "$ENV_FILE"
grep -Eq '^GITHUB_TOKEN=.+$' "$ENV_FILE" || fail "GITHUB_TOKEN is not configured in $ENV_FILE"

INSTALL_STAGE="configure_owner_bridge"
BACKEND_ENV_PATH="$(read_value "$ENV_FILE" SOVEREIGN_BACKEND_ENV_FILE)"
if [[ -z "$BACKEND_ENV_PATH" ]]; then
  for candidate in /run/secrets/sovereign-backend.env /opt/sovereign-backend/.env; do
    if [[ -f "$candidate" ]]; then
      BACKEND_ENV_PATH="$candidate"
      break
    fi
  done
fi
[[ -n "$BACKEND_ENV_PATH" && -f "$BACKEND_ENV_PATH" ]] || fail "backend env file is missing for the owner approval bridge"
backup_control_plane_file "$BACKEND_ENV_PATH"
chmod 0600 "$BACKEND_ENV_PATH"
OWNER_REQUEST_KEY="$(read_value "$ENV_FILE" SOVEREIGN_OWNER_REQUEST_KEY)"
if [[ -z "$OWNER_REQUEST_KEY" ]]; then
  OWNER_REQUEST_KEY="$(openssl rand -hex 32)"
fi
set_value "$ENV_FILE" SOVEREIGN_OWNER_REQUEST_KEY "$OWNER_REQUEST_KEY"
set_value "$ENV_FILE" SOVEREIGN_BACKEND_INTERNAL_URL "http://sovereign-backend:8787"
set_value "$ENV_FILE" SOVEREIGN_BACKEND_ENV_FILE "$BACKEND_ENV_PATH"
set_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_REQUEST_KEY "$OWNER_REQUEST_KEY"
set_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_INPUT_ROOT "/opt/secure/owner-managed"
OWNER_REFERENCE_ID="$(read_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_REFERENCE_ID)"
OWNER_ADMIN_ID="$(read_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_ADMIN_ID)"
OWNER_ADMIN_EMAIL="$(read_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_ADMIN_EMAIL)"
if [[ -z "$OWNER_REFERENCE_ID" ]]; then
  OWNER_REFERENCE_ID="26487"
fi
if [[ -z "$OWNER_ADMIN_ID" && -z "$OWNER_ADMIN_EMAIL" ]]; then
  OWNER_ADMIN_EMAIL="rastamanweeste@gmail.com"
fi
[[ "$OWNER_REFERENCE_ID" =~ ^[0-9]{1,20}$ ]] || fail "SOVEREIGN_OWNER_REFERENCE_ID is invalid"
set_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_REFERENCE_ID "$OWNER_REFERENCE_ID"
if [[ -n "$OWNER_ADMIN_ID" ]]; then
  [[ "$OWNER_ADMIN_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || fail "SOVEREIGN_OWNER_ADMIN_ID is invalid"
  set_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_ADMIN_ID "$OWNER_ADMIN_ID"
elif [[ "$OWNER_ADMIN_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
  set_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_ADMIN_EMAIL "$OWNER_ADMIN_EMAIL"
else
  fail "configure a valid SOVEREIGN_OWNER_ADMIN_ID or SOVEREIGN_OWNER_ADMIN_EMAIL for the owner approval surface"
fi
unset OWNER_REQUEST_KEY OWNER_REFERENCE_ID OWNER_ADMIN_ID OWNER_ADMIN_EMAIL

CURRENT_ALLOWED_WORKFLOWS="$(read_value "$ENV_FILE" SOVEREIGN_MCP_ALLOWED_WORKFLOWS)"
if [[ -z "$CURRENT_ALLOWED_WORKFLOWS" ]]; then
  printf '\nSOVEREIGN_MCP_ALLOWED_WORKFLOWS=android.yml,android-release.yml,sovereign-chatgpt-mcp.yml\n' >> "$ENV_FILE"
elif [[ ",$CURRENT_ALLOWED_WORKFLOWS," != *",android.yml,"* ]]; then
  sed -i "s|^SOVEREIGN_MCP_ALLOWED_WORKFLOWS=.*$|SOVEREIGN_MCP_ALLOWED_WORKFLOWS=android.yml,$CURRENT_ALLOWED_WORKFLOWS|" "$ENV_FILE"
fi

if [[ "$(read_value "$ENV_FILE" SOVEREIGN_MCP_BOOTSTRAP_DATABASE)" == "1" ]]; then
  command -v openssl >/dev/null 2>&1 || fail "openssl is required for database bootstrap"
  BACKEND_ENV_PATH="$(read_value "$ENV_FILE" SOVEREIGN_BACKEND_ENV_FILE)"
  MCP_ENV_FILE="$ENV_FILE" \
    SOVEREIGN_BACKEND_ENV_FILE="${BACKEND_ENV_PATH:-/opt/sovereign-backend/.env}" \
    "$BIN_DIR/bootstrap-database"
  sed -i 's/^SOVEREIGN_MCP_BOOTSTRAP_DATABASE=.*/SOVEREIGN_MCP_BOOTSTRAP_DATABASE=0/' "$ENV_FILE"
fi

grep -Eq '^POSTGRES_PASSWORD=.+$' "$ENV_FILE" || fail "POSTGRES_PASSWORD is missing"
grep -Eq '^SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD=.+$' "$ENV_FILE" || fail "preview database password is missing"

DOCKER_CONFIG_VALUE=""
if [[ -f "$GHCR_ENV" ]]; then
  chmod 0600 "$GHCR_ENV"
  GHCR_USERNAME="$(read_value "$GHCR_ENV" GHCR_USERNAME)"
  GHCR_TOKEN="$(read_value "$GHCR_ENV" GHCR_TOKEN)"
  if [[ -n "$GHCR_USERNAME" || -n "$GHCR_TOKEN" ]]; then
    [[ -n "$GHCR_USERNAME" && -n "$GHCR_TOKEN" ]] || fail "GHCR_USERNAME and GHCR_TOKEN must both be configured"
    install -d -m 0700 "$DOCKER_AUTH_DIR"
    printf '%s' "$GHCR_TOKEN" | docker --config "$DOCKER_AUTH_DIR" login ghcr.io --username "$GHCR_USERNAME" --password-stdin >/dev/null
    chmod 0600 "$DOCKER_AUTH_DIR/config.json"
    DOCKER_CONFIG_VALUE="$DOCKER_AUTH_DIR"
  fi
fi

INSTALL_STAGE="pull_immutable_image"
MCP_TAGGED_IMAGE="$MCP_IMAGE_REPOSITORY:$EXPECTED_REVISION"
if [[ -n "$DOCKER_CONFIG_VALUE" ]]; then
  docker --config "$DOCKER_CONFIG_VALUE" pull "$MCP_TAGGED_IMAGE"
else
  docker pull "$MCP_TAGGED_IMAGE"
fi
MCP_IMAGE_REVISION="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$MCP_TAGGED_IMAGE")"
[[ "$MCP_IMAGE_REVISION" == "$EXPECTED_REVISION" ]] || fail "MCP image revision label does not match expected revision"
MCP_IMAGE_DIGEST="$(docker image inspect --format '{{json .RepoDigests}}' "$MCP_TAGGED_IMAGE" \
  | python3 -c 'import json,sys; repo=sys.argv[1]+"@"; values=json.load(sys.stdin); print(next((item for item in values if isinstance(item,str) and item.startswith(repo)), ""))' "$MCP_IMAGE_REPOSITORY")"
[[ "$MCP_IMAGE_DIGEST" == "$MCP_IMAGE_REPOSITORY"@sha256:* ]] || fail "MCP image digest repository does not match"
[[ "${MCP_IMAGE_DIGEST#*@}" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "MCP image has no immutable repository digest"
if grep -q '^SOVEREIGN_MCP_IMAGE=' "$ENV_FILE"; then
  sed -i "s|^SOVEREIGN_MCP_IMAGE=.*$|SOVEREIGN_MCP_IMAGE=$MCP_IMAGE_DIGEST|" "$ENV_FILE"
else
  printf '\nSOVEREIGN_MCP_IMAGE=%s\n' "$MCP_IMAGE_DIGEST" >> "$ENV_FILE"
fi
export SOVEREIGN_MCP_IMAGE="$MCP_IMAGE_DIGEST"

INSTALL_STAGE="write_broker_environment"
{
  grep -E '^(GITHUB_TOKEN|SOVEREIGN_MCP_REPOSITORY|SOVEREIGN_MCP_GIT_AUTHOR_NAME|SOVEREIGN_MCP_GIT_AUTHOR_EMAIL|SOVEREIGN_MCP_ALLOWED_CONTAINERS|SOVEREIGN_MCP_ALLOWED_WORKFLOWS|SOVEREIGN_MCP_WORKSPACE_ROOT|SOVEREIGN_MCP_ENABLE_DB_WRITES|SOVEREIGN_MCP_ENABLE_DEPLOY|SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS|SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS|SOVEREIGN_MCP_ENABLE_ADMIN_SQL|SOVEREIGN_MCP_ENABLE_MAIN_PUSH|SOVEREIGN_MCP_ENABLE_PR_MERGE|SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL|SOVEREIGN_MCP_ALLOW_MERGE_WITHOUT_CHECKS|SOVEREIGN_MCP_ENABLE_SELF_UPDATE|SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST|SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT|SOVEREIGN_MCP_PREVIEW_POSTGRES_DB|SOVEREIGN_MCP_PREVIEW_POSTGRES_USER|SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD|SOVEREIGN_BACKEND_IMAGE_REPOSITORY|SOVEREIGN_BACKEND_ENV_FILE)=' "$ENV_FILE" || true
  printf 'SOVEREIGN_MCP_DEPLOY_SCRIPT=%s\n' "$BIN_DIR/deploy-sovereign-backend"
  printf 'SOVEREIGN_MCP_ROLLBACK_SCRIPT=%s\n' "$BIN_DIR/rollback-sovereign-backend"
  printf 'SOVEREIGN_MCP_SOURCE_DIR=/opt/sovereign-operator-source\n'
  printf 'SOVEREIGN_MCP_SELF_UPDATE_SERVICE=sovereign-chatgpt-mcp-self-update.service\n'
  printf 'SOVEREIGN_MCP_SELF_UPDATE_STATUS=/var/lib/sovereign-chatgpt-self-update/status.json\n'
  printf 'SOVEREIGN_MCP_COMMAND_QUEUE=%s\n' "$COMMAND_QUEUE_DIR"
  printf 'SOVEREIGN_BACKEND_CONTAINER=sovereign-backend\n'
  [[ -z "$DOCKER_CONFIG_VALUE" ]] || printf 'DOCKER_CONFIG=%s\n' "$DOCKER_CONFIG_VALUE"
} > "$BROKER_ENV"
chmod 0600 "$BROKER_ENV"
chown root:root "$BROKER_ENV"

INSTALL_STAGE="compose_preflight"
BROKER_GID="$(getent group sovereign-mcp | cut -d: -f3)"
[[ "$BROKER_GID" =~ ^[0-9]+$ ]] || fail "could not resolve sovereign-mcp group id"
export BROKER_GID
cd "$INSTALL_ROOT"
docker compose config >/dev/null

INSTALL_STAGE="start_host_control_plane"
systemctl daemon-reload
systemctl enable --now sovereign-chatgpt-command-worker.service
systemctl restart sovereign-chatgpt-command-worker.service
systemctl is-active --quiet sovereign-chatgpt-command-worker.service || fail "host command worker is not active"
systemctl enable --now sovereign-chatgpt-broker.service
systemctl restart sovereign-chatgpt-broker.service
for attempt in $(seq 1 20); do
  [[ -S /run/sovereign-chatgpt-broker/operator.sock ]] && break
  sleep 1
done
[[ -S /run/sovereign-chatgpt-broker/operator.sock ]] || {
  systemctl status sovereign-chatgpt-broker.service --no-pager >&2 || true
  fail "host broker socket was not created"
}

# The image is built and dependency-resolved in GitHub Actions. The VPS only
# pulls and verifies the immutable revision before touching the running container.

INSTALL_STAGE="replace_mcp_container"
# Stop only the known tunnel and MCP container before claiming the host port.
# Unknown listeners are never killed: they block deployment with bounded evidence.
if systemctl is-active --quiet sovereign-openai-tunnel.service; then
  systemctl stop sovereign-openai-tunnel.service
fi
if docker container inspect sovereign-chatgpt-mcp >/dev/null 2>&1; then
  docker rm -f sovereign-chatgpt-mcp >/dev/null
fi

PORT_EVIDENCE=""
for attempt in $(seq 1 10); do
  PORT_EVIDENCE="$(port_listener_evidence)"
  [[ -z "$PORT_EVIDENCE" ]] && break
  sleep 1
done
if [[ -n "$PORT_EVIDENCE" ]]; then
  printf '%s\n' "$PORT_EVIDENCE" >&2
  fail "host port $MCP_HOST_PORT remains occupied after controlled MCP shutdown; refusing to kill an unknown process"
fi

docker compose up -d --no-build --force-recreate --remove-orphans

INSTALL_STAGE="verify_mcp_container"
CONTAINER_STATE=""
for attempt in $(seq 1 30); do
  CONTAINER_STATE="$(docker inspect sovereign-chatgpt-mcp --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}' 2>/dev/null || true)"
  if [[ "$CONTAINER_STATE" == "running healthy" ]]; then
    break
  fi
  sleep 2
done
if [[ "$CONTAINER_STATE" != "running healthy" ]]; then
  docker logs --tail 200 sovereign-chatgpt-mcp >&2 || true
  fail "MCP container did not pass protocol health: ${CONTAINER_STATE:-missing}"
fi

[[ -S /run/sovereign-chatgpt-broker/operator.sock ]] || fail "host broker socket disappeared after MCP recreation"
docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock || fail "broker socket is not visible inside the recreated MCP container"
docker exec sovereign-chatgpt-mcp python - <<'PY'
import json
import socket
import uuid

request_id = uuid.uuid4().hex
payload = json.dumps(
    {"request_id": request_id, "action": "host_worker_canary", "arguments": {}},
    separators=(",", ":"),
).encode("utf-8") + b"\n"
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(5)
    client.connect("/run/sovereign-chatgpt-broker/operator.sock")
    client.sendall(payload)
    response = json.loads(client.recv(65536).split(b"\n", 1)[0].decode("utf-8"))
result = response["result"]
assert result.get("failure_family") == "INBOUND_MUTATION_FORBIDDEN", result
PY
docker exec sovereign-chatgpt-mcp python -c 'import launcher; import server; import self_heal; import android_hardening; import android_validation_router; import tool_extensions; assert launcher.mcp is server.mcp; assert self_heal.REPAIR_ENGINE is not None; assert android_hardening.AndroidHardeningRuntime is not None; assert getattr(server.android, "_native_validation_router_installed", False) is True; assert callable(tool_extensions.repository_dispatch_workflow); assert callable(tool_extensions.repository_workflow_run_status); status=server.broker.status(); assert status.get("status") == "BROKER_READY", status; worker=server.broker.call("host_worker_canary", {}, timeout=10); assert worker.get("status") == "HOST_WORKER_READY", worker; assert worker.get("execution_origin") == "host_worker", worker'
docker exec sovereign-chatgpt-mcp python /app/mcp_protocol_health.py --url http://127.0.0.1:8090/mcp --timeout-seconds 5
docker exec sovereign-chatgpt-mcp python -c 'import os; assert os.getenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions") == "github_actions"'
docker exec sovereign-chatgpt-mcp python -c 'from pathlib import Path; root=Path("/opt/sovereign-chatgpt-tools/workspaces"); probe=root/".permission-probe"; probe.write_text("ok", encoding="utf-8"); probe.unlink()'

INSTALL_STAGE="verify_tunnel"
if [[ -f "$TUNNEL_ENV" ]] \
  && grep -Eq '^OPENAI_TUNNEL_ID=tunnel_.+' "$TUNNEL_ENV" \
  && grep -Eq '^CONTROL_PLANE_API_KEY=.+$' "$TUNNEL_ENV"; then
  "$BIN_DIR/install-secure-tunnel"
  sleep 11
  MALFORMED_MCP_REQUESTS="$(docker logs --since 20s sovereign-chatgpt-mcp 2>&1 \
    | grep -Ec 'POST /mcp HTTP/1\.1" 400 Bad Request' || true)"
  SUCCESSFUL_MCP_REQUESTS="$(docker logs --since 20s sovereign-chatgpt-mcp 2>&1 \
    | grep -Ec 'POST /mcp HTTP/1\.1" (200 OK|202 Accepted)' || true)"
  [[ "$MALFORMED_MCP_REQUESTS" =~ ^[0-9]+$ ]] || fail "could not count malformed MCP requests"
  [[ "$SUCCESSFUL_MCP_REQUESTS" =~ ^[0-9]+$ ]] || fail "could not count successful MCP requests"
  if (( MALFORMED_MCP_REQUESTS >= 2 && SUCCESSFUL_MCP_REQUESTS == 0 )); then
    docker logs --since 20s sovereign-chatgpt-mcp 2>&1 | tail -n 80 >&2 || true
    fail "repeated malformed MCP requests detected after tunnel start"
  fi
else
  printf 'Tunnel not installed: configure %s when the OpenAI tunnel_id and runtime key are available.\n' "$TUNNEL_ENV"
fi

INSTALL_STAGE="completed"
INSTALL_COMPLETED=1
ROLLBACK_ARMED=0
printf '{"ok":true,"mcp":"http://127.0.0.1:8090/mcp","mcp_protocol_ready":true,"broker":"active","broker_rpc_ready":true,"broker_socket_host_visible":true,"broker_socket_container_visible":true,"host_command_worker_active":true,"inbound_mutation_forbidden":true,"container":"sovereign-chatgpt-mcp","mcp_image":"%s","mcp_revision":"%s","workspace_writable":true,"policy_repair_engine":true,"private_admin_mode_available":true,"self_update_available":true,"android_hardening_available":true,"android_native_build_mode":"github_actions","android_native_validation_router":true,"pr_lifecycle_available":true,"workflow_dispatch_available":true}\n' "$MCP_IMAGE_DIGEST" "$EXPECTED_REVISION"
