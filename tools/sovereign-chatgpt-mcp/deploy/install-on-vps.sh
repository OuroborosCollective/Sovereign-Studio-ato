#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="/opt/sovereign-chatgpt-tools"
BIN_DIR="$INSTALL_ROOT/bin"
BROKER_DIR="$INSTALL_ROOT/broker"
DOCKER_AUTH_DIR="$INSTALL_ROOT/docker-auth"
WORKSPACE_DIR="$INSTALL_ROOT/workspaces"
ANDROID_SDK_DIR="/opt/android-sdk"
ENV_FILE="$INSTALL_ROOT/.env"
GHCR_ENV="$INSTALL_ROOT/.ghcr.env"
TUNNEL_ENV="$INSTALL_ROOT/tunnel.env"
BROKER_ENV="$INSTALL_ROOT/broker.env"
BROKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-broker.service"
SELF_UPDATE_SERVICE="/etc/systemd/system/sovereign-chatgpt-mcp-self-update.service"
TUNNEL_SERVICE="/etc/systemd/system/sovereign-openai-tunnel.service"
MCP_UID="10001"
MCP_GID="10001"
MCP_HOST_PORT="8090"

fail() {
  printf 'install blocked: %s\n' "$*" >&2
  exit 1
}

read_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

port_listener_evidence() {
  ss -H -ltnp 2>/dev/null | awk -v suffix=":$MCP_HOST_PORT" '$4 ~ suffix "$" {print}'
}

[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root on the VPS"
for command in docker systemctl python3 git ss; do
  command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed"
[[ -S /var/run/docker.sock ]] || fail "docker socket is missing"

getent group sovereign-mcp >/dev/null 2>&1 || groupadd --system sovereign-mcp
install -d -m 0750 "$INSTALL_ROOT" "$BIN_DIR" "$BROKER_DIR"
install -d -m 0755 "$ANDROID_SDK_DIR"
install -d -m 0770 -o "$MCP_UID" -g "$MCP_GID" "$WORKSPACE_DIR"
chown -R "$MCP_UID:$MCP_GID" "$WORKSPACE_DIR"
chmod 0770 "$WORKSPACE_DIR"

for file in Dockerfile requirements.txt policy.py runtime.py database.py broker_client.py self_heal.py android_hardening.py android_validation_router.py mcp_protocol_health.py server.py tool_extensions.py launcher.py docker-compose.yml; do
  install -m 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file"
done

install -m 0640 "$SOURCE_DIR/broker.py" "$BROKER_DIR/broker.py"
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

{
  grep -E '^(GITHUB_TOKEN|SOVEREIGN_MCP_REPOSITORY|SOVEREIGN_MCP_GIT_AUTHOR_NAME|SOVEREIGN_MCP_GIT_AUTHOR_EMAIL|SOVEREIGN_MCP_ALLOWED_CONTAINERS|SOVEREIGN_MCP_ALLOWED_WORKFLOWS|SOVEREIGN_MCP_WORKSPACE_ROOT|SOVEREIGN_MCP_ENABLE_DB_WRITES|SOVEREIGN_MCP_ENABLE_DEPLOY|SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS|SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS|SOVEREIGN_MCP_ENABLE_ADMIN_SQL|SOVEREIGN_MCP_ENABLE_MAIN_PUSH|SOVEREIGN_MCP_ENABLE_PR_MERGE|SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL|SOVEREIGN_MCP_ALLOW_MERGE_WITHOUT_CHECKS|SOVEREIGN_MCP_ENABLE_SELF_UPDATE|SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST|SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT|SOVEREIGN_MCP_PREVIEW_POSTGRES_DB|SOVEREIGN_MCP_PREVIEW_POSTGRES_USER|SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD|SOVEREIGN_BACKEND_IMAGE_REPOSITORY|SOVEREIGN_BACKEND_ENV_FILE)=' "$ENV_FILE" || true
  printf 'SOVEREIGN_MCP_DEPLOY_SCRIPT=%s\n' "$BIN_DIR/deploy-sovereign-backend"
  printf 'SOVEREIGN_MCP_ROLLBACK_SCRIPT=%s\n' "$BIN_DIR/rollback-sovereign-backend"
  printf 'SOVEREIGN_MCP_SOURCE_DIR=/opt/sovereign-operator-source\n'
  printf 'SOVEREIGN_MCP_SELF_UPDATE_SERVICE=sovereign-chatgpt-mcp-self-update.service\n'
  printf 'SOVEREIGN_MCP_SELF_UPDATE_STATUS=/var/lib/sovereign-chatgpt-self-update/status.json\n'
  printf 'SOVEREIGN_BACKEND_CONTAINER=sovereign-backend\n'
  [[ -z "$DOCKER_CONFIG_VALUE" ]] || printf 'DOCKER_CONFIG=%s\n' "$DOCKER_CONFIG_VALUE"
} > "$BROKER_ENV"
chmod 0600 "$BROKER_ENV"
chown root:root "$BROKER_ENV"

systemctl daemon-reload
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

BROKER_GID="$(getent group sovereign-mcp | cut -d: -f3)"
[[ "$BROKER_GID" =~ ^[0-9]+$ ]] || fail "could not resolve sovereign-mcp group id"
export BROKER_GID
cd "$INSTALL_ROOT"
docker compose config >/dev/null

# Build first. The running container is not touched when the new image cannot be built.
docker compose build

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
docker exec sovereign-chatgpt-mcp python -c 'import launcher; import server; import self_heal; import android_hardening; import android_validation_router; import tool_extensions; assert launcher.mcp is server.mcp; assert self_heal.REPAIR_ENGINE is not None; assert android_hardening.AndroidHardeningRuntime is not None; assert getattr(server.android, "_native_validation_router_installed", False) is True; assert callable(tool_extensions.repository_dispatch_workflow); assert callable(tool_extensions.repository_workflow_run_status); status=server.broker.status(); assert status.get("status") == "BROKER_READY", status'
docker exec sovereign-chatgpt-mcp python /app/mcp_protocol_health.py --url http://127.0.0.1:8090/mcp --timeout-seconds 5
docker exec sovereign-chatgpt-mcp python -c 'import os; assert os.getenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions") == "github_actions"'
docker exec sovereign-chatgpt-mcp python -c 'from pathlib import Path; root=Path("/opt/sovereign-chatgpt-tools/workspaces"); probe=root/".permission-probe"; probe.write_text("ok", encoding="utf-8"); probe.unlink()'

if [[ -f "$TUNNEL_ENV" ]] \
  && grep -Eq '^OPENAI_TUNNEL_ID=tunnel_.+' "$TUNNEL_ENV" \
  && grep -Eq '^CONTROL_PLANE_API_KEY=.+$' "$TUNNEL_ENV"; then
  "$BIN_DIR/install-secure-tunnel"
  sleep 11
  MALFORMED_MCP_REQUESTS="$(docker logs --since 20s sovereign-chatgpt-mcp 2>&1 \
    | grep -Ec 'POST /mcp HTTP/1\.1" 400 Bad Request' || true)"
  [[ "$MALFORMED_MCP_REQUESTS" =~ ^[0-9]+$ ]] || fail "could not count malformed MCP requests"
  if (( MALFORMED_MCP_REQUESTS >= 2 )); then
    docker logs --since 20s sovereign-chatgpt-mcp 2>&1 | tail -n 80 >&2 || true
    fail "repeated malformed MCP requests detected after tunnel start"
  fi
else
  printf 'Tunnel not installed: configure %s when the OpenAI tunnel_id and runtime key are available.\n' "$TUNNEL_ENV"
fi

printf '{"ok":true,"mcp":"http://127.0.0.1:8090/mcp","mcp_protocol_ready":true,"broker":"active","broker_rpc_ready":true,"broker_socket_host_visible":true,"broker_socket_container_visible":true,"container":"sovereign-chatgpt-mcp","workspace_writable":true,"policy_repair_engine":true,"private_admin_mode_available":true,"self_update_available":true,"android_hardening_available":true,"android_native_build_mode":"github_actions","android_native_validation_router":true,"pr_lifecycle_available":true,"workflow_dispatch_available":true}\n'
