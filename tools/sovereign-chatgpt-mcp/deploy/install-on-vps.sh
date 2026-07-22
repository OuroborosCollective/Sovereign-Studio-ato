#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="/opt/sovereign-chatgpt-tools"
BIN_DIR="$INSTALL_ROOT/bin"
BROKER_DIR="$INSTALL_ROOT/broker"
COMPOSE_TEMPLATE_ROOT="$INSTALL_ROOT/templates"
LITELLM_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/sovereign-litellm"
LITELLM_TEMPLATE_SOURCE="$SOURCE_DIR/templates/sovereign-litellm"
PGBACKWEB_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/pgbackweb-wq5r"
PGBACKWEB_TEMPLATE_SOURCE="$SOURCE_DIR/templates/pgbackweb-wq5r"
PATCHMON_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/patchmon-sovereign"
PATCHMON_TEMPLATE_SOURCE="$SOURCE_DIR/templates/patchmon-sovereign"
CODE_SERVER_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/code-server-46bq"
CODE_SERVER_TEMPLATE_SOURCE="$SOURCE_DIR/templates/code-server-46bq"
MILVUS_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/milvus-sovereign"
MILVUS_TEMPLATE_SOURCE="$SOURCE_DIR/templates/milvus-sovereign"
FREELLMAPI_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/sovereign-freellmapi"
FREELLMAPI_TEMPLATE_SOURCE="$SOURCE_DIR/templates/sovereign-freellmapi"
DOCKER_AUTH_DIR="$INSTALL_ROOT/docker-auth"
WORKSPACE_DIR="$INSTALL_ROOT/workspaces"
COMMAND_QUEUE_DIR="$INSTALL_ROOT/command-queue"
ANDROID_SDK_DIR="/opt/android-sdk"
OWNER_INPUT_HOST_ROOT="/opt/sovereign-owner-managed"
BACKEND_WORKSPACE_HOST_ROOT="/opt/sovereign-agent-workspaces"
BACKEND_WORKSPACE_UID="10001"
BACKEND_WORKSPACE_GID="10001"
LITELLM_BASE_URL=http://litellm:4000
LITELLM_MASTER_KEY_FILE=/opt/sovereign-owner-managed/litellm_master_key.txt
ENV_FILE="$INSTALL_ROOT/.env"
MANAGED_ENV="$INSTALL_ROOT/runtime.env"
BACKEND_MANAGED_ENV="$INSTALL_ROOT/backend-runtime.env"
GHCR_ENV="$INSTALL_ROOT/.ghcr.env"
TUNNEL_ENV="$INSTALL_ROOT/tunnel.env"
BROKER_ENV="$INSTALL_ROOT/broker.env"
BROKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-broker.service"
COMMAND_WORKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-command-worker.service"
SELF_UPDATE_SERVICE="/etc/systemd/system/sovereign-chatgpt-mcp-self-update.service"
SELF_UPDATE_BIN="$BIN_DIR/self-update-chatgpt-mcp"
TUNNEL_SERVICE="/etc/systemd/system/sovereign-openai-tunnel.service"
MCP_UID="10001"
MCP_GID="10001"
MCP_HOST_PORT="8090"
MCP_IMAGE_REPOSITORY="${SOVEREIGN_MCP_IMAGE_REPOSITORY:-ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp}"
EXPECTED_REVISION="${SOVEREIGN_MCP_EXPECTED_REVISION:-}"
EXPECTED_CROSS_RUNTIME_PARITY="true"
REQUIRE_TUNNEL="${SOVEREIGN_MCP_REQUIRE_TUNNEL:-0}"
TUNNEL_MODE="${SOVEREIGN_MCP_TUNNEL_MODE:-auto}"
INSTALL_STAGE="initializing"
INSTALL_FAILURE_REASON=""
INSTALL_COMPLETED=0
ROLLBACK_ARMED=0
ROLLBACK_DIR=""
ROLLBACK_MANIFEST=""
PREVIOUS_MCP_IMAGE_DIGEST=""

fail() {
  INSTALL_FAILURE_REASON="$*"
  exit 1
}

read_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

read_mcp_value() {
  local key="$1"
  if [[ -f "$MANAGED_ENV" ]] && grep -q "^${key}=" "$MANAGED_ENV"; then
    read_value "$MANAGED_ENV" "$key"
  else
    read_value "$ENV_FILE" "$key"
  fi
}

read_backend_value() {
  local key="$1"
  if [[ -f "$BACKEND_MANAGED_ENV" ]] && grep -q "^${key}=" "$BACKEND_MANAGED_ENV"; then
    read_value "$BACKEND_MANAGED_ENV" "$key"
  else
    read_value "$BACKEND_ENV_PATH" "$key"
  fi
}

ensure_managed_env() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    install -m 0600 /dev/null "$file"
  else
    ensure_private_file_mode "$file"
  fi
}

ensure_private_file_mode() {
  local file="$1"
  python3 - "$file" <<'PY'
import errno
import os
import stat
import sys

path = sys.argv[1]
try:
    os.chmod(path, 0o600)
except OSError as exc:
    if exc.errno not in {errno.EPERM, errno.EACCES, errno.EROFS}:
        raise
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077:
        raise SystemExit(f"protected file has unsafe mode: {mode:o}")
PY
}

set_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import errno
import os
import stat
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
payload = "\n".join(out) + "\n"
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(payload, "utf-8")
os.chmod(temporary, 0o600)
try:
    temporary.replace(path)
except OSError as exc:
    if exc.errno not in {errno.EPERM, errno.EBUSY, errno.EXDEV}:
        temporary.unlink(missing_ok=True)
        raise
    try:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(path, 0o600)
        except OSError as chmod_exc:
            if chmod_exc.errno not in {errno.EPERM, errno.EACCES, errno.EROFS}:
                raise
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                raise PermissionError(f"protected file has unsafe mode: {mode:o}") from chmod_exc
    finally:
        temporary.unlink(missing_ok=True)
PY
}

valid_mcp_image_digest() {
  local value="$1"
  [[ "$value" == "$MCP_IMAGE_REPOSITORY"@sha256:* ]] \
    && [[ "${value#*@}" =~ ^sha256:[0-9a-f]{64}$ ]]
}

resolve_running_mcp_image_digest() {
  local configured image_id
  configured="$(docker inspect sovereign-chatgpt-mcp --format '{{.Config.Image}}' 2>/dev/null || true)"
  if valid_mcp_image_digest "$configured"; then
    printf '%s\n' "$configured"
    return 0
  fi
  image_id="$(docker inspect sovereign-chatgpt-mcp --format '{{.Image}}' 2>/dev/null || true)"
  [[ -n "$image_id" ]] || return 1
  docker image inspect --format '{{json .RepoDigests}}' "$image_id" 2>/dev/null \
    | python3 -c 'import json,sys; repo=sys.argv[1]+"@"; values=json.load(sys.stdin); print(next((item for item in values if isinstance(item,str) and item.startswith(repo)), ""))' "$MCP_IMAGE_REPOSITORY"
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
  if [[ -f "$ENV_FILE" ]] && valid_mcp_image_digest "$PREVIOUS_MCP_IMAGE_DIGEST"; then
    ensure_managed_env "$MANAGED_ENV"
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$PREVIOUS_MCP_IMAGE_DIGEST"
    export SOVEREIGN_MCP_IMAGE="$PREVIOUS_MCP_IMAGE_DIGEST"
  fi
  systemctl daemon-reload >/dev/null 2>&1
  systemctl restart sovereign-chatgpt-command-worker.service >/dev/null 2>&1
  systemctl restart sovereign-chatgpt-broker.service >/dev/null 2>&1
  wait_for_broker_ready >/dev/null 2>&1 || true
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
  if [[ "$TUNNEL_MODE" != "disabled" ]]; then
    systemctl restart sovereign-openai-tunnel.service >/dev/null 2>&1
  fi
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

INSTALL_STAGE="preflight"
[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root on the VPS"
[[ "$EXPECTED_REVISION" =~ ^[0-9a-f]{40}$ ]] || fail "SOVEREIGN_MCP_EXPECTED_REVISION must be a full commit SHA"
[[ "$REQUIRE_TUNNEL" =~ ^[01]$ ]] || fail "SOVEREIGN_MCP_REQUIRE_TUNNEL must be 0 or 1"
[[ "$TUNNEL_MODE" =~ ^(auto|required|disabled)$ ]] || fail "SOVEREIGN_MCP_TUNNEL_MODE must be auto, required or disabled"
[[ "$MCP_IMAGE_REPOSITORY" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+$ ]] || fail "SOVEREIGN_MCP_IMAGE_REPOSITORY is invalid"
for command in docker systemctl python3 git ss openssl sha256sum; do
  command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed"
[[ -S /var/run/docker.sock ]] || fail "docker socket is missing"
[[ -f "$LITELLM_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "sovereign-litellm compose template is missing"
[[ -f "$LITELLM_TEMPLATE_SOURCE/config.yaml" ]] || fail "sovereign-litellm config template is missing"
[[ -f "$LITELLM_TEMPLATE_SOURCE/sovereign-entrypoint.py" ]] || fail "sovereign-litellm entrypoint template is missing"
[[ -f "$PGBACKWEB_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "pgbackweb compose template is missing"
[[ -f "$PATCHMON_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "patchmon compose template is missing"
[[ -f "$CODE_SERVER_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "code-server compose template is missing"
[[ -f "$MILVUS_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "milvus compose template is missing"
[[ -f "$FREELLMAPI_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "FreeLLM API compose template is missing"
[[ -f "$FREELLMAPI_TEMPLATE_SOURCE/sovereign-freellm-bootstrap.mjs" ]] || fail "FreeLLM API bootstrap template is missing"
[[ -f "$SOURCE_DIR/skills/sovereign-operational-governance/SKILL.md" ]] || fail "operational governance skill manifest is missing"
[[ -f "$SOURCE_DIR/skills/sovereign-operational-assurance/SKILL.md" ]] || fail "operational assurance skill manifest is missing"
bash -n "$SOURCE_DIR/deploy/self-update-chatgpt-mcp.sh" \
  || fail "source self-update wrapper has invalid bash syntax"

getent group sovereign-mcp >/dev/null 2>&1 || groupadd --system sovereign-mcp
install -d -m 0750 "$INSTALL_ROOT" "$BIN_DIR" "$BROKER_DIR" "$COMPOSE_TEMPLATE_ROOT" "$LITELLM_TEMPLATE_DIR" "$PGBACKWEB_TEMPLATE_DIR" "$PATCHMON_TEMPLATE_DIR" "$CODE_SERVER_TEMPLATE_DIR" "$MILVUS_TEMPLATE_DIR" "$FREELLMAPI_TEMPLATE_DIR"
for MANAGED_COMPOSE_ROOT in /opt/sovereign-litellm /opt/sovereign-backend /opt/gpt-tools /opt/code-server-46bq /opt/pgbackweb-wq5r /opt/patchmon-sovereign /opt/milvus-sovereign /opt/sovereign-freellmapi; do
  if [[ -e "$MANAGED_COMPOSE_ROOT" || -L "$MANAGED_COMPOSE_ROOT" ]]; then
    [[ -d "$MANAGED_COMPOSE_ROOT" && ! -L "$MANAGED_COMPOSE_ROOT" ]] \
      || fail "managed compose root is not a regular directory: $MANAGED_COMPOSE_ROOT"
  else
    install -d -m 0750 "$MANAGED_COMPOSE_ROOT"
  fi
done
unset MANAGED_COMPOSE_ROOT
install -d -m 0755 "$ANDROID_SDK_DIR"
install -d -m 0770 -o root -g sovereign-mcp "$COMMAND_QUEUE_DIR" "$COMMAND_QUEUE_DIR/inbox" "$COMMAND_QUEUE_DIR/processing" "$COMMAND_QUEUE_DIR/outbox"
install -d -m 0770 -o "$MCP_UID" -g "$MCP_GID" "$WORKSPACE_DIR"
chown -R "$MCP_UID:$MCP_GID" "$WORKSPACE_DIR"
chmod 0770 "$WORKSPACE_DIR"
if [[ -e "$OWNER_INPUT_HOST_ROOT" || -L "$OWNER_INPUT_HOST_ROOT" ]]; then
  [[ -d "$OWNER_INPUT_HOST_ROOT" && ! -L "$OWNER_INPUT_HOST_ROOT" ]] \
    || fail "owner input host root is not a regular directory"
else
  mkdir -p "$OWNER_INPUT_HOST_ROOT"
fi
chmod 0700 "$OWNER_INPUT_HOST_ROOT"
[[ -w "$OWNER_INPUT_HOST_ROOT" && -x "$OWNER_INPUT_HOST_ROOT" ]] \
  || fail "owner input host root is not writable and searchable"
if [[ -e "$BACKEND_WORKSPACE_HOST_ROOT" || -L "$BACKEND_WORKSPACE_HOST_ROOT" ]]; then
  [[ -d "$BACKEND_WORKSPACE_HOST_ROOT" && ! -L "$BACKEND_WORKSPACE_HOST_ROOT" ]] \
    || fail "backend workspace host root is not a regular directory"
else
  install -d -m 0770 -o "$BACKEND_WORKSPACE_UID" -g "$BACKEND_WORKSPACE_GID" "$BACKEND_WORKSPACE_HOST_ROOT"
fi
chown "$BACKEND_WORKSPACE_UID:$BACKEND_WORKSPACE_GID" "$BACKEND_WORKSPACE_HOST_ROOT"
chmod 0770 "$BACKEND_WORKSPACE_HOST_ROOT"
[[ -w "$BACKEND_WORKSPACE_HOST_ROOT" && -x "$BACKEND_WORKSPACE_HOST_ROOT" ]] \
  || fail "backend workspace host root is not writable and searchable"

INSTALL_STAGE="backup_existing_control_plane"
ROLLBACK_DIR="$(mktemp -d "$INSTALL_ROOT/.control-plane-backup.XXXXXX")"
chmod 0700 "$ROLLBACK_DIR"
ROLLBACK_MANIFEST="$ROLLBACK_DIR/manifest.tsv"
: > "$ROLLBACK_MANIFEST"
: > "$ROLLBACK_MANIFEST.paths"
backup_control_plane_file "$MANAGED_ENV"
backup_control_plane_file "$BACKEND_MANAGED_ENV"
backup_control_plane_file "$BROKER_ENV"
backup_control_plane_file "$BROKER_SERVICE"
backup_control_plane_file "$COMMAND_WORKER_SERVICE"
backup_control_plane_file "$SELF_UPDATE_SERVICE"
backup_control_plane_file "$TUNNEL_SERVICE"
PREVIOUS_MCP_IMAGE_DIGEST="$(read_mcp_value SOVEREIGN_MCP_IMAGE 2>/dev/null || true)"
if ! valid_mcp_image_digest "$PREVIOUS_MCP_IMAGE_DIGEST"; then
  PREVIOUS_MCP_IMAGE_DIGEST="$(resolve_running_mcp_image_digest || true)"
fi
ROLLBACK_ARMED=1

INSTALL_STAGE="copy_control_plane_files"
for file in Dockerfile requirements.txt policy.py runtime.py database.py command_contract.py command_queue.py broker_client.py owner_input_client.py a2a_runtime_client.py document_pipeline.py owner_input_widget.py self_heal.py android_hardening.py android_validation_router.py mcp_protocol_health.py sovereign_cognitive_widget.py server.py tool_extensions.py repository_skill_tools.py proven_learning_tools.py skill_supply_chain_tools.py deterministic_contract.py deterministic_architecture_tools.py enterprise_backend_tools.py freemium_product_architect_tools.py openai_project_access_tools.py operational_governance_tools.py operational_assurance_tools.py output_contracts.py toolchain_composition.py patchmon_operator.py launcher.py docker-compose.yml; do
  backup_control_plane_file "$INSTALL_ROOT/$file"
  install -m 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file"
done

for file in broker.py browserless_reader.py document_pipeline.py command_contract.py command_queue.py command_worker.py operations.py admin_mode.py github_admin.py self_update.py policy.py self_heal.py litellm_stack.py managed_compose.py patchmon_operator.py; do
  backup_control_plane_file "$BROKER_DIR/$file"
done
backup_control_plane_file "$LITELLM_TEMPLATE_DIR/docker-compose.yml"
backup_control_plane_file "$LITELLM_TEMPLATE_DIR/config.yaml"
backup_control_plane_file "$LITELLM_TEMPLATE_DIR/sovereign-entrypoint.py"
backup_control_plane_file "$PGBACKWEB_TEMPLATE_DIR/docker-compose.yml"
backup_control_plane_file "$PATCHMON_TEMPLATE_DIR/docker-compose.yml"
backup_control_plane_file "$CODE_SERVER_TEMPLATE_DIR/docker-compose.yml"
backup_control_plane_file "$MILVUS_TEMPLATE_DIR/docker-compose.yml"
backup_control_plane_file "$FREELLMAPI_TEMPLATE_DIR/docker-compose.yml"
backup_control_plane_file "$FREELLMAPI_TEMPLATE_DIR/sovereign-freellm-bootstrap.mjs"
for file in deploy-sovereign-backend rollback-sovereign-backend bootstrap-database install-secure-tunnel validate-tunnel-doctor-report; do
  backup_control_plane_file "$BIN_DIR/$file"
done

# The updater is the recovery and diagnostic entrypoint. After syntax validation,
# keep the newest bounded-status wrapper even when the wider control-plane install
# rolls back, otherwise the next attempt reintroduces generic failure evidence.
SELF_UPDATE_NEXT="$(mktemp "$BIN_DIR/.self-update-chatgpt-mcp.XXXXXX")"
install -m 0750 "$SOURCE_DIR/deploy/self-update-chatgpt-mcp.sh" "$SELF_UPDATE_NEXT"
chown root:sovereign-mcp "$SELF_UPDATE_NEXT"
mv -f "$SELF_UPDATE_NEXT" "$SELF_UPDATE_BIN"
unset SELF_UPDATE_NEXT

install -m 0640 "$SOURCE_DIR/broker.py" "$BROKER_DIR/broker.py"
install -m 0640 "$SOURCE_DIR/browserless_reader.py" "$BROKER_DIR/browserless_reader.py"
install -m 0640 "$SOURCE_DIR/document_pipeline.py" "$BROKER_DIR/document_pipeline.py"
install -m 0640 "$SOURCE_DIR/command_contract.py" "$BROKER_DIR/command_contract.py"
install -m 0640 "$SOURCE_DIR/command_queue.py" "$BROKER_DIR/command_queue.py"
install -m 0640 "$SOURCE_DIR/command_worker.py" "$BROKER_DIR/command_worker.py"
install -m 0640 "$SOURCE_DIR/operations.py" "$BROKER_DIR/operations.py"
install -m 0640 "$SOURCE_DIR/admin_mode.py" "$BROKER_DIR/admin_mode.py"
install -m 0640 "$SOURCE_DIR/github_admin.py" "$BROKER_DIR/github_admin.py"
install -m 0640 "$SOURCE_DIR/self_update.py" "$BROKER_DIR/self_update.py"
install -m 0640 "$SOURCE_DIR/policy.py" "$BROKER_DIR/policy.py"
install -m 0640 "$SOURCE_DIR/self_heal.py" "$BROKER_DIR/self_heal.py"
install -m 0640 "$SOURCE_DIR/litellm_stack.py" "$BROKER_DIR/litellm_stack.py"
install -m 0640 "$SOURCE_DIR/managed_compose.py" "$BROKER_DIR/managed_compose.py"
install -m 0640 "$SOURCE_DIR/patchmon_operator.py" "$BROKER_DIR/patchmon_operator.py"
install -m 0640 "$LITELLM_TEMPLATE_SOURCE/docker-compose.yml" "$LITELLM_TEMPLATE_DIR/docker-compose.yml"
install -m 0640 "$LITELLM_TEMPLATE_SOURCE/config.yaml" "$LITELLM_TEMPLATE_DIR/config.yaml"
install -m 0640 "$LITELLM_TEMPLATE_SOURCE/sovereign-entrypoint.py" "$LITELLM_TEMPLATE_DIR/sovereign-entrypoint.py"
install -m 0640 "$PGBACKWEB_TEMPLATE_SOURCE/docker-compose.yml" "$PGBACKWEB_TEMPLATE_DIR/docker-compose.yml"
install -m 0640 "$PATCHMON_TEMPLATE_SOURCE/docker-compose.yml" "$PATCHMON_TEMPLATE_DIR/docker-compose.yml"
install -m 0640 "$CODE_SERVER_TEMPLATE_SOURCE/docker-compose.yml" "$CODE_SERVER_TEMPLATE_DIR/docker-compose.yml"
install -m 0640 "$MILVUS_TEMPLATE_SOURCE/docker-compose.yml" "$MILVUS_TEMPLATE_DIR/docker-compose.yml"
install -m 0640 "$FREELLMAPI_TEMPLATE_SOURCE/docker-compose.yml" "$FREELLMAPI_TEMPLATE_DIR/docker-compose.yml"
install -m 0640 "$FREELLMAPI_TEMPLATE_SOURCE/sovereign-freellm-bootstrap.mjs" "$FREELLMAPI_TEMPLATE_DIR/sovereign-freellm-bootstrap.mjs"
install -m 0750 "$SOURCE_DIR/deploy/deploy-sovereign-backend" "$BIN_DIR/deploy-sovereign-backend"
install -m 0750 "$SOURCE_DIR/deploy/rollback-sovereign-backend" "$BIN_DIR/rollback-sovereign-backend"
install -m 0750 "$SOURCE_DIR/deploy/bootstrap-database.sh" "$BIN_DIR/bootstrap-database"
install -m 0750 "$SOURCE_DIR/deploy/install-secure-tunnel.sh" "$BIN_DIR/install-secure-tunnel"
install -m 0750 "$SOURCE_DIR/deploy/validate-tunnel-doctor-report.py" "$BIN_DIR/validate-tunnel-doctor-report"
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
chown -R root:sovereign-mcp "$BROKER_DIR" "$BIN_DIR" "$COMPOSE_TEMPLATE_ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$SOURCE_DIR/.env.example" "$INSTALL_ROOT/.env.example"
  install -m 0600 "$SOURCE_DIR/.ghcr.env.example" "$INSTALL_ROOT/.ghcr.env.example"
  install -m 0600 "$SOURCE_DIR/.tunnel.env.example" "$INSTALL_ROOT/tunnel.env.example"
  fail "create $ENV_FILE from $INSTALL_ROOT/.env.example and fill it only on the VPS"
fi
ensure_private_file_mode "$ENV_FILE"
ensure_managed_env "$MANAGED_ENV"
grep -Eq '^GITHUB_TOKEN=.+$' "$ENV_FILE" || fail "GITHUB_TOKEN is not configured in $ENV_FILE"

INSTALL_STAGE="configure_private_owner_mode"
PRIVATE_OWNER_MODE="$(read_mcp_value SOVEREIGN_MCP_PRIVATE_OWNER_MODE)"
if [[ -z "$PRIVATE_OWNER_MODE" ]]; then
  PRIVATE_OWNER_MODE="1"
fi
[[ "$PRIVATE_OWNER_MODE" =~ ^[01]$ ]] || fail "SOVEREIGN_MCP_PRIVATE_OWNER_MODE must be 0 or 1"
set_value "$MANAGED_ENV" SOVEREIGN_MCP_PRIVATE_OWNER_MODE "$PRIVATE_OWNER_MODE"
if [[ "$PRIVATE_OWNER_MODE" == "1" ]]; then
  for OWNER_CAPABILITY in \
    SOVEREIGN_MCP_ENABLE_DB_WRITES \
    SOVEREIGN_MCP_ENABLE_DEPLOY \
    SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS \
    SOVEREIGN_MCP_ENABLE_ADMIN_SQL \
    SOVEREIGN_MCP_ENABLE_MAIN_PUSH \
    SOVEREIGN_MCP_ENABLE_PR_MERGE \
    SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL \
    SOVEREIGN_MCP_ENABLE_SELF_UPDATE \
    SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE; do
    set_value "$MANAGED_ENV" "$OWNER_CAPABILITY" "1"
  done
fi
for GUARDED_CAPABILITY in \
  SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS \
  SOVEREIGN_MCP_ALLOW_MERGE_WITHOUT_CHECKS \
  SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE; do
  if [[ -z "$(read_mcp_value "$GUARDED_CAPABILITY")" ]]; then
    set_value "$MANAGED_ENV" "$GUARDED_CAPABILITY" "0"
  fi
done
unset PRIVATE_OWNER_MODE OWNER_CAPABILITY GUARDED_CAPABILITY

INSTALL_STAGE="ensure_recovery_image_digest"
CURRENT_MCP_IMAGE_DIGEST="$(read_mcp_value SOVEREIGN_MCP_IMAGE)"
if ! valid_mcp_image_digest "$CURRENT_MCP_IMAGE_DIGEST"; then
  CURRENT_MCP_IMAGE_DIGEST="$PREVIOUS_MCP_IMAGE_DIGEST"
fi
valid_mcp_image_digest "$CURRENT_MCP_IMAGE_DIGEST" \
  || fail "SOVEREIGN_MCP_IMAGE is missing and the running MCP container has no immutable GHCR digest"
set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$CURRENT_MCP_IMAGE_DIGEST"
export SOVEREIGN_MCP_IMAGE="$CURRENT_MCP_IMAGE_DIGEST"
unset CURRENT_MCP_IMAGE_DIGEST

INSTALL_STAGE="configure_owner_bridge"
BACKEND_ENV_PATH="$(read_mcp_value SOVEREIGN_BACKEND_ENV_FILE)"
if [[ -z "$BACKEND_ENV_PATH" ]]; then
  for candidate in /run/secrets/sovereign-backend.env /opt/sovereign-backend/.env; do
    if [[ -f "$candidate" ]]; then
      BACKEND_ENV_PATH="$candidate"
      break
    fi
  done
fi
[[ -n "$BACKEND_ENV_PATH" && -f "$BACKEND_ENV_PATH" ]] || fail "backend env file is missing for the owner approval bridge"
ensure_private_file_mode "$BACKEND_ENV_PATH"
ensure_managed_env "$BACKEND_MANAGED_ENV"
OWNER_REQUEST_KEY="$(read_mcp_value SOVEREIGN_OWNER_REQUEST_KEY)"
if [[ -z "$OWNER_REQUEST_KEY" ]]; then
  OWNER_REQUEST_KEY="$(read_backend_value SOVEREIGN_OWNER_REQUEST_KEY)"
fi
if [[ -z "$OWNER_REQUEST_KEY" ]]; then
  OWNER_REQUEST_KEY="$(openssl rand -hex 32)"
fi
set_value "$MANAGED_ENV" SOVEREIGN_OWNER_REQUEST_KEY "$OWNER_REQUEST_KEY"
set_value "$MANAGED_ENV" SOVEREIGN_BACKEND_INTERNAL_URL "http://sovereign-backend:8787"
set_value "$MANAGED_ENV" SOVEREIGN_BACKEND_ENV_FILE "$BACKEND_ENV_PATH"
set_value "$MANAGED_ENV" SOVEREIGN_BACKEND_MANAGED_ENV_FILE "$BACKEND_MANAGED_ENV"
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_REQUEST_KEY "$OWNER_REQUEST_KEY"
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_INPUT_ROOT "/opt/sovereign-owner-managed"
set_value "$BACKEND_MANAGED_ENV" LITELLM_BASE_URL "$LITELLM_BASE_URL"
set_value "$BACKEND_MANAGED_ENV" LITELLM_MASTER_KEY_FILE "$LITELLM_MASTER_KEY_FILE"
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE "/opt/sovereign-owner-managed/freellmapi_unified_key.txt"
OWNER_REFERENCE_ID="$(read_backend_value SOVEREIGN_OWNER_REFERENCE_ID)"
OWNER_ADMIN_ID="$(read_backend_value SOVEREIGN_OWNER_ADMIN_ID)"
OWNER_ADMIN_EMAIL="$(read_backend_value SOVEREIGN_OWNER_ADMIN_EMAIL)"
if [[ -z "$OWNER_REFERENCE_ID" ]]; then
  OWNER_REFERENCE_ID="26487"
fi
if [[ -z "$OWNER_ADMIN_ID" && -z "$OWNER_ADMIN_EMAIL" ]]; then
  OWNER_ADMIN_EMAIL="rastamanweeste@gmail.com"
fi
[[ "$OWNER_REFERENCE_ID" =~ ^[0-9]{1,20}$ ]] || fail "SOVEREIGN_OWNER_REFERENCE_ID is invalid"
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_REFERENCE_ID "$OWNER_REFERENCE_ID"
if [[ -n "$OWNER_ADMIN_ID" ]]; then
  [[ "$OWNER_ADMIN_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || fail "SOVEREIGN_OWNER_ADMIN_ID is invalid"
  set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_ADMIN_ID "$OWNER_ADMIN_ID"
elif [[ "$OWNER_ADMIN_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
  set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_ADMIN_EMAIL "$OWNER_ADMIN_EMAIL"
else
  fail "configure a valid SOVEREIGN_OWNER_ADMIN_ID or SOVEREIGN_OWNER_ADMIN_EMAIL for the owner approval surface"
fi
unset OWNER_REQUEST_KEY OWNER_REFERENCE_ID OWNER_ADMIN_ID OWNER_ADMIN_EMAIL

for REQUIRED_WORKFLOW in android.yml e2e-testing.yml sovereign-backend-image.yml sovereign-chatgpt-mcp.yml sovereign-agent-backend.yml release-verification.yml; do
  CURRENT_ALLOWED_WORKFLOWS="$(read_mcp_value SOVEREIGN_MCP_ALLOWED_WORKFLOWS)"
  if [[ -z "$CURRENT_ALLOWED_WORKFLOWS" ]]; then
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_WORKFLOWS "$REQUIRED_WORKFLOW"
  elif [[ ",$CURRENT_ALLOWED_WORKFLOWS," != *",$REQUIRED_WORKFLOW,"* ]]; then
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_WORKFLOWS "$REQUIRED_WORKFLOW,$CURRENT_ALLOWED_WORKFLOWS"
  fi
done
unset REQUIRED_WORKFLOW CURRENT_ALLOWED_WORKFLOWS

for REQUIRED_CONTAINER in sovereign-backend sovereign-chatgpt-mcp gpt-browserless gpt-tika gpt-gotenberg gpt-dozzle sovereign-litellm-litellm-1 sovereign-litellm-db-1 code-server-46bq-code-server-1 pgbackweb-wq5r-pgbackweb-1 pgbackweb-wq5r-db-1 patchmon-sovereign-server-1 patchmon-sovereign-database-1 patchmon-sovereign-redis-1 patchmon-sovereign-guacd-1 sovereign-freellmapi; do
  CURRENT_ALLOWED_CONTAINERS="$(read_mcp_value SOVEREIGN_MCP_ALLOWED_CONTAINERS)"
  if [[ -z "$CURRENT_ALLOWED_CONTAINERS" ]]; then
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_CONTAINERS "$REQUIRED_CONTAINER"
  elif [[ ",$CURRENT_ALLOWED_CONTAINERS," != *",$REQUIRED_CONTAINER,"* ]]; then
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_CONTAINERS "$REQUIRED_CONTAINER,$CURRENT_ALLOWED_CONTAINERS"
  fi
done
unset REQUIRED_CONTAINER CURRENT_ALLOWED_CONTAINERS

if [[ "$(read_mcp_value SOVEREIGN_MCP_BOOTSTRAP_DATABASE)" == "1" ]]; then
  command -v openssl >/dev/null 2>&1 || fail "openssl is required for database bootstrap"
  BACKEND_ENV_PATH="$(read_mcp_value SOVEREIGN_BACKEND_ENV_FILE)"
  MCP_BASE_ENV_FILE="$ENV_FILE" \
    MCP_ENV_FILE="$MANAGED_ENV" \
    SOVEREIGN_BACKEND_ENV_FILE="${BACKEND_ENV_PATH:-/opt/sovereign-backend/.env}" \
    "$BIN_DIR/bootstrap-database"
  set_value "$MANAGED_ENV" SOVEREIGN_MCP_BOOTSTRAP_DATABASE "0"
fi

[[ -n "$(read_mcp_value POSTGRES_PASSWORD)" ]] || fail "POSTGRES_PASSWORD is missing"
[[ -n "$(read_mcp_value SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD)" ]] || fail "preview database password is missing"

DOCKER_CONFIG_VALUE=""
if [[ -f "$GHCR_ENV" ]]; then
  ensure_private_file_mode "$GHCR_ENV"
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
MCP_IMAGE_CROSS_RUNTIME_PARITY="$(docker image inspect --format '{{index .Config.Labels "io.ouroboros.sovereign.cross-runtime-parity"}}' "$MCP_TAGGED_IMAGE")"
[[ "$MCP_IMAGE_CROSS_RUNTIME_PARITY" == "$EXPECTED_CROSS_RUNTIME_PARITY" ]] || fail "MCP image does not carry verified cross-runtime parity evidence"
set_value "$MANAGED_ENV" SOVEREIGN_CROSS_RUNTIME_PARITY_PROVEN "1"
MCP_IMAGE_DIGEST="$(docker image inspect --format '{{json .RepoDigests}}' "$MCP_TAGGED_IMAGE" \
  | python3 -c 'import json,sys; repo=sys.argv[1]+"@"; values=json.load(sys.stdin); print(next((item for item in values if isinstance(item,str) and item.startswith(repo)), ""))' "$MCP_IMAGE_REPOSITORY")"
[[ "$MCP_IMAGE_DIGEST" == "$MCP_IMAGE_REPOSITORY"@sha256:* ]] || fail "MCP image digest repository does not match"
[[ "${MCP_IMAGE_DIGEST#*@}" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "MCP image has no immutable repository digest"
set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$MCP_IMAGE_DIGEST"
export SOVEREIGN_MCP_IMAGE="$MCP_IMAGE_DIGEST"

INSTALL_STAGE="write_broker_environment"
{
  for environment_file in "$ENV_FILE" "$MANAGED_ENV"; do
    grep -E '^(GITHUB_TOKEN|SOVEREIGN_MCP_REPOSITORY|SOVEREIGN_MCP_GIT_AUTHOR_NAME|SOVEREIGN_MCP_GIT_AUTHOR_EMAIL|SOVEREIGN_MCP_ALLOWED_CONTAINERS|SOVEREIGN_MCP_ALLOWED_WORKFLOWS|SOVEREIGN_MCP_WORKSPACE_ROOT|SOVEREIGN_MCP_PRIVATE_OWNER_MODE|SOVEREIGN_MCP_ENABLE_DB_WRITES|SOVEREIGN_MCP_ENABLE_DEPLOY|SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS|SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS|SOVEREIGN_MCP_ENABLE_ADMIN_SQL|SOVEREIGN_MCP_ENABLE_MAIN_PUSH|SOVEREIGN_MCP_ENABLE_PR_MERGE|SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL|SOVEREIGN_MCP_ALLOW_MERGE_WITHOUT_CHECKS|SOVEREIGN_MCP_ENABLE_SELF_UPDATE|SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE|SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE|SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST|SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT|SOVEREIGN_MCP_PREVIEW_POSTGRES_DB|SOVEREIGN_MCP_PREVIEW_POSTGRES_USER|SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD|SOVEREIGN_BACKEND_IMAGE_REPOSITORY|SOVEREIGN_BACKEND_ENV_FILE|SOVEREIGN_BACKEND_MANAGED_ENV_FILE)=' "$environment_file" || true
  done
  printf 'SOVEREIGN_MCP_DEPLOY_SCRIPT=%s\n' "$BIN_DIR/deploy-sovereign-backend"
  printf 'SOVEREIGN_MCP_ROLLBACK_SCRIPT=%s\n' "$BIN_DIR/rollback-sovereign-backend"
  printf 'SOVEREIGN_MCP_SOURCE_DIR=/opt/sovereign-operator-source\n'
  printf 'SOVEREIGN_MCP_SELF_UPDATE_SERVICE=sovereign-chatgpt-mcp-self-update.service\n'
  printf 'SOVEREIGN_MCP_SELF_UPDATE_STATUS=/var/lib/sovereign-chatgpt-self-update/status.json\n'
  printf 'SOVEREIGN_MCP_COMMAND_QUEUE=%s\n' "$COMMAND_QUEUE_DIR"
  printf 'SOVEREIGN_COMPOSE_TEMPLATE_ROOT=%s\n' "$COMPOSE_TEMPLATE_ROOT"
  printf 'PATCHMON_MCP_ADMIN_TOKEN_FILE=/opt/patchmon-sovereign/mcp-admin.jwt\n'
  printf 'SOVEREIGN_LITELLM_TEMPLATE_ROOT=%s\n' "$LITELLM_TEMPLATE_DIR"
  printf 'SOVEREIGN_LITELLM_DEPLOY_ROOT=/opt/sovereign-litellm\n'
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
wait_for_broker_ready || {
  systemctl status sovereign-chatgpt-broker.service --no-pager >&2 || true
  fail "host broker socket exists but the broker RPC did not become ready"
}

# The image is built and dependency-resolved in GitHub Actions. The VPS only
# pulls and verifies the immutable revision before touching the running container.

INSTALL_STAGE="replace_mcp_container"
# Stop only the known tunnel and MCP container before claiming the host port.
# Unknown listeners are never killed: they block deployment with bounded evidence.
if [[ "$TUNNEL_MODE" != "disabled" ]] && systemctl is-active --quiet sovereign-openai-tunnel.service; then
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

INSTALL_STAGE="verify_broker_socket_visibility"
[[ -S /run/sovereign-chatgpt-broker/operator.sock ]] || fail "host broker socket disappeared after MCP recreation"
docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock || fail "broker socket is not visible inside the recreated MCP container"

INSTALL_STAGE="verify_inbound_mutation_boundary"
docker exec -i sovereign-chatgpt-mcp python - <<'PY'
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

INSTALL_STAGE="verify_runtime_import_contracts"
docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-operational-governance/SKILL.md || fail "operational governance skill manifest is missing from the MCP image"
docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-operational-assurance/SKILL.md || fail "operational assurance skill manifest is missing from the MCP image"
docker exec sovereign-chatgpt-mcp python -c 'import launcher; import server; import self_heal; import android_hardening; import android_validation_router; import a2a_runtime_client; import document_pipeline; import owner_input_widget; import tool_extensions; import repository_skill_tools; import proven_learning_tools; import skill_supply_chain_tools; import deterministic_contract; import deterministic_architecture_tools; import enterprise_backend_tools; import freemium_product_architect_tools; import openai_project_access_tools; import operational_governance_tools; import operational_assurance_tools; import output_contracts; import toolchain_composition; import patchmon_operator; assert launcher.mcp is server.mcp; output_contract_report=launcher.OUTPUT_CONTRACT_INSTALLATION; assert output_contract_report.get("ok") is True, output_contract_report; assert output_contract_report.get("missingOutputSchemaCount") == 0, output_contract_report; assert self_heal.REPAIR_ENGINE is not None; assert android_hardening.AndroidHardeningRuntime is not None; assert getattr(server.android, "_native_validation_router_installed", False) is True; assert callable(tool_extensions.repository_dispatch_workflow); assert callable(tool_extensions.repository_workflow_run_status); assert callable(repository_skill_tools.repository_knowledge_surface_scan); assert callable(repository_skill_tools.repository_product_logic_map); assert callable(repository_skill_tools.repository_change_impact_manifest); assert callable(repository_skill_tools.repository_architecture_snapshot); assert callable(repository_skill_tools.repository_architecture_drift_report); assert callable(repository_skill_tools.repository_architecture_runtime_drift_evidence); assert callable(repository_skill_tools.repository_mirror_diff_report); assert callable(repository_skill_tools.repository_endpoint_reference); assert callable(repository_skill_tools.repository_learning_records_normalize_preview); assert callable(repository_skill_tools.repository_release_hunt_manifest); assert callable(proven_learning_tools.proven_learning_pattern_plan); assert callable(proven_learning_tools.proven_learning_owner_approval_request); assert callable(proven_learning_tools.proven_learning_pattern_apply); assert callable(proven_learning_tools.repository_learning_logbook_update); assert callable(skill_supply_chain_tools.skill_supply_chain_inventory); assert callable(skill_supply_chain_tools.skill_archive_inspect); assert callable(skill_supply_chain_tools.goal_transition_preview); assert callable(skill_supply_chain_tools.template_generation_plan); assert deterministic_contract.KAPPA_SCALE == 1000000; inventory=deterministic_architecture_tools.deterministic_tool_inventory(); assert inventory.get("crossRuntimeParityProven") is True, inventory; assert callable(deterministic_architecture_tools.deterministic_tool_inventory); assert callable(deterministic_architecture_tools.deterministic_architecture_inventory); assert callable(deterministic_architecture_tools.deterministic_nondeterminism_scan); assert callable(deterministic_architecture_tools.deterministic_kappa_contract_audit); assert callable(deterministic_architecture_tools.deterministic_sql_contract_audit); assert callable(deterministic_architecture_tools.deterministic_transition_validate); assert callable(deterministic_architecture_tools.deterministic_replay_verify); assert callable(deterministic_architecture_tools.deterministic_transformation_plan); assert callable(enterprise_backend_tools.backend_engineering_tool_inventory); assert callable(enterprise_backend_tools.backend_architecture_assess); assert callable(enterprise_backend_tools.backend_stack_select); assert callable(enterprise_backend_tools.backend_delivery_plan); assert callable(enterprise_backend_tools.backend_api_security_plan); assert callable(enterprise_backend_tools.repository_revision_resolve); assert callable(freemium_product_architect_tools.freemium_product_tool_inventory); assert callable(freemium_product_architect_tools.freemium_market_opportunity_score); assert callable(freemium_product_architect_tools.freemium_offer_contract_build); assert callable(freemium_product_architect_tools.freemium_product_contract_validate); assert callable(freemium_product_architect_tools.freemium_product_bundle_manifest); assert callable(openai_project_access_tools.openai_project_access_plan); assert callable(openai_project_access_tools.openai_project_access_runtime_evidence); assert callable(operational_governance_tools.operational_skill_inventory); assert callable(operational_governance_tools.mcp_tool_contract_registry); assert callable(operational_governance_tools.tool_recommend_for_mission); assert callable(operational_governance_tools.mcp_registry_snapshot_verify); assert callable(operational_governance_tools.evidence_graph_build); assert callable(operational_governance_tools.schema_migration_reconcile); assert callable(operational_governance_tools.llm_route_reliability_assess); assert callable(operational_governance_tools.agent_run_liveness_assess); assert callable(operational_governance_tools.semantic_intent_boundary_audit); assert callable(operational_governance_tools.cost_credit_settlement_reconcile); assert callable(operational_governance_tools.backup_restore_evidence_verify); assert callable(operational_governance_tools.slo_error_budget_assess); assert callable(operational_governance_tools.configuration_drift_assess); assert callable(operational_governance_tools.runtime_runbook_generate); assert callable(operational_governance_tools.ownership_codeowners_guard); assert callable(operational_governance_tools.compliance_evidence_export); assert callable(operational_assurance_tools.operational_assurance_skill_inventory); assert callable(operational_assurance_tools.vps_capacity_resource_pressure_assess); assert callable(operational_assurance_tools.runtime_dependency_health_matrix); assert callable(operational_assurance_tools.outbox_queue_liveness_assess); assert callable(operational_assurance_tools.scheduled_maintenance_coordinate); assert callable(operational_assurance_tools.runtime_topology_change_audit); assert callable(operational_assurance_tools.postgres_query_index_performance_assess); assert callable(operational_assurance_tools.data_integrity_invariant_audit); assert callable(operational_assurance_tools.data_repair_plan_build); assert callable(operational_assurance_tools.vector_memory_consistency_assess); assert callable(operational_assurance_tools.memory_poisoning_provenance_guard); assert callable(operational_assurance_tools.learning_pattern_lifecycle_preview); assert callable(operational_assurance_tools.data_retention_privacy_audit); assert callable(operational_assurance_tools.multi_tenant_isolation_verify); assert callable(operational_assurance_tools.mcp_schema_compatibility_audit); assert callable(operational_assurance_tools.mcp_protocol_conformance_fuzz_plan); assert callable(operational_assurance_tools.tool_permission_minimize); assert callable(operational_assurance_tools.dynamic_execution_containment_audit); assert callable(operational_assurance_tools.skill_capability_coverage_map); assert callable(operational_assurance_tools.skill_lifecycle_deprecation_preview); assert callable(operational_assurance_tools.skill_regression_benchmark); assert callable(operational_assurance_tools.tool_idempotency_verify); assert callable(operational_assurance_tools.owner_approval_policy_evaluate); assert callable(operational_assurance_tools.secret_lifecycle_rotation_assess); assert callable(operational_assurance_tools.secret_literal_triage); assert callable(operational_assurance_tools.sbom_provenance_image_signing_verify); assert callable(operational_assurance_tools.dependency_vulnerability_remediation_plan); assert callable(operational_assurance_tools.authentication_chaos_negative_test_assess); assert output_contracts.ToolOutputEnvelope is not None; assert callable(toolchain_composition.mcp_toolchain_contract_inventory); assert callable(toolchain_composition.mcp_toolchain_compile); assert callable(toolchain_composition.mcp_toolchain_validate); assert callable(toolchain_composition.mcp_toolchain_next_step); assert callable(toolchain_composition.mcp_diagnostic_chain_plan); assert all(getattr(tool, "output_schema", None) for tool in launcher.mcp._tool_manager.list_tools()); assurance=operational_assurance_tools.operational_assurance_skill_inventory(); assert assurance.status == "OPERATIONAL_ASSURANCE_SKILLS_READY", assurance; registry=operational_governance_tools.mcp_tool_contract_registry(include_schemas=False); assert registry.status == "MCP_TOOL_REGISTRY_READY", registry; assert registry.toolCount >= 43, registry; assert callable(server.repository_sync_workspace_to_pr_head); assert callable(server.postgres_schema_inventory); assert callable(server.managed_compose_stack_plan); assert callable(server.deploy_managed_compose_stack); assert callable(server.memory_gateway_collection_canary); assert callable(server.patchmon_tool_inventory); assert callable(server.patchmon_runtime_inventory); assert callable(server.patchmon_database_inventory); assert callable(server.patchmon_query); assert callable(server.patchmon_brain_snapshot); assert callable(server.patchmon_patch_action_plan); assert callable(server.patchmon_patch_action_apply); assert patchmon_operator.PatchmonOperatorRuntime is not None; assert callable(server.a2a_live_canary); assert callable(server.controller_run_external_event); assert callable(server.document_pipeline_live_canary); assert a2a_runtime_client.A2A_VERSION == "1.0"; assert document_pipeline.DocumentPipelineRuntime is not None; assert owner_input_widget.WIDGET_URI in {str(item.uri) for item in server.mcp._resource_manager.list_resources()}; status=server.broker.status(); assert status.get("status") == "BROKER_READY", status'

INSTALL_STAGE="verify_host_worker_canary"
docker exec sovereign-chatgpt-mcp python -c 'import server; worker=server.broker.call("host_worker_canary", {}, timeout=10); assert worker.get("status") == "HOST_WORKER_READY", worker; assert worker.get("execution_origin") == "host_worker", worker'

INSTALL_STAGE="verify_mcp_protocol_handshake"
docker exec sovereign-chatgpt-mcp python /app/mcp_protocol_health.py --url http://127.0.0.1:8090/mcp --timeout-seconds 5

INSTALL_STAGE="verify_android_native_boundary"
docker exec sovereign-chatgpt-mcp python -c 'import os; assert os.getenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions") == "github_actions"'

INSTALL_STAGE="verify_workspace_write_boundary"
docker exec sovereign-chatgpt-mcp python -c 'from pathlib import Path; root=Path("/opt/sovereign-chatgpt-tools/workspaces"); probe=root/".permission-probe"; probe.write_text("ok", encoding="utf-8"); probe.unlink()'

INSTALL_STAGE="verify_tunnel_configuration"
TUNNEL_CONFIGURED=0
if [[ "$TUNNEL_MODE" == "disabled" ]]; then
  printf 'Tunnel checks skipped for the tunnel-independent MCP profile.\n'
elif [[ -f "$TUNNEL_ENV" ]] \
  && grep -Eq '^OPENAI_TUNNEL_ID=tunnel_.+' "$TUNNEL_ENV" \
  && grep -Eq '^CONTROL_PLANE_API_KEY=.+$' "$TUNNEL_ENV"; then
  TUNNEL_CONFIGURED=1
elif [[ "$REQUIRE_TUNNEL" == "1" || "$TUNNEL_MODE" == "required" ]]; then
  fail "the selected MCP profile requires a valid tunnel.env with OPENAI_TUNNEL_ID and CONTROL_PLANE_API_KEY"
fi

INSTALL_STAGE="verify_tunnel"
if [[ "$TUNNEL_CONFIGURED" == "1" ]]; then
  "$BIN_DIR/install-secure-tunnel"
  systemctl is-active --quiet sovereign-openai-tunnel.service \
    || fail "tunnel installer returned without an active service"
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
  printf 'Tunnel not installed: configure %s before using the ChatGPT app connection.\n' "$TUNNEL_ENV"
fi
unset TUNNEL_CONFIGURED

INSTALL_STAGE="completed"
INSTALL_COMPLETED=1
ROLLBACK_ARMED=0
printf '{"ok":true,"mcp":"http://127.0.0.1:8090/mcp","mcp_protocol_ready":true,"broker":"active","broker_rpc_ready":true,"broker_socket_host_visible":true,"broker_socket_container_visible":true,"host_command_worker_active":true,"inbound_mutation_forbidden":true,"container":"sovereign-chatgpt-mcp","mcp_image":"%s","mcp_revision":"%s","tunnel_mode":"%s","workspace_writable":true,"policy_repair_engine":true,"private_admin_mode_available":true,"self_update_available":true,"android_hardening_available":true,"android_native_build_mode":"github_actions","android_native_validation_router":true,"deterministic_architecture_tools":true,"enterprise_backend_tools":true,"freemium_product_architect_tools":true,"operational_governance_tools":true,"operational_assurance_tools":true,"repository_revision_resolver":true,"kappa_scale":1000000,"cross_runtime_parity_proven":true,"pr_lifecycle_available":true,"workspace_pr_head_sync_available":true,"workflow_dispatch_available":true,"managed_compose_write_available":true,"patchmon_operator_available":true,"managed_compose_stacks":["sovereign-litellm","sovereign-backend","gpt-tools","code-server-46bq","pgbackweb-wq5r","patchmon-sovereign","milvus-sovereign","sovereign-freellmapi"]}\n' "$MCP_IMAGE_DIGEST" "$EXPECTED_REVISION" "$TUNNEL_MODE"
