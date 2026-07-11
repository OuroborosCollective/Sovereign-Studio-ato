#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="/opt/sovereign-chatgpt-tools"
BIN_DIR="$INSTALL_ROOT/bin"
BROKER_DIR="$INSTALL_ROOT/broker"
DOCKER_AUTH_DIR="$INSTALL_ROOT/docker-auth"
WORKSPACE_DIR="$INSTALL_ROOT/workspaces"
ENV_FILE="$INSTALL_ROOT/.env"
GHCR_ENV="$INSTALL_ROOT/.ghcr.env"
TUNNEL_ENV="$INSTALL_ROOT/tunnel.env"
BROKER_ENV="$INSTALL_ROOT/broker.env"
BROKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-broker.service"
TUNNEL_SERVICE="/etc/systemd/system/sovereign-openai-tunnel.service"
MCP_UID="10001"
MCP_GID="10001"

fail() {
  printf 'install blocked: %s\n' "$*" >&2
  exit 1
}

read_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root on the VPS"
for command in docker systemctl python3; do
  command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed"
[[ -S /var/run/docker.sock ]] || fail "docker socket is missing"

getent group sovereign-mcp >/dev/null 2>&1 || groupadd --system sovereign-mcp
install -d -m 0750 "$INSTALL_ROOT" "$BIN_DIR" "$BROKER_DIR"
install -d -m 0770 -o "$MCP_UID" -g "$MCP_GID" "$WORKSPACE_DIR"
chown -R "$MCP_UID:$MCP_GID" "$WORKSPACE_DIR"
chmod 0770 "$WORKSPACE_DIR"

for file in Dockerfile requirements.txt policy.py runtime.py database.py broker_client.py server.py docker-compose.yml; do
  install -m 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file"
done

install -m 0640 "$SOURCE_DIR/broker.py" "$BROKER_DIR/broker.py"
install -m 0640 "$SOURCE_DIR/operations.py" "$BROKER_DIR/operations.py"
install -m 0640 "$SOURCE_DIR/policy.py" "$BROKER_DIR/policy.py"
install -m 0750 "$SOURCE_DIR/deploy/deploy-sovereign-backend" "$BIN_DIR/deploy-sovereign-backend"
install -m 0750 "$SOURCE_DIR/deploy/rollback-sovereign-backend" "$BIN_DIR/rollback-sovereign-backend"
install -m 0750 "$SOURCE_DIR/deploy/bootstrap-database.sh" "$BIN_DIR/bootstrap-database"
install -m 0750 "$SOURCE_DIR/deploy/install-secure-tunnel.sh" "$BIN_DIR/install-secure-tunnel"
install -m 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-broker.service" "$BROKER_SERVICE"
install -m 0644 "$SOURCE_DIR/deploy/sovereign-openai-tunnel.service" "$TUNNEL_SERVICE"
chown -R root:sovereign-mcp "$BROKER_DIR" "$BIN_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$SOURCE_DIR/.env.example" "$INSTALL_ROOT/.env.example"
  install -m 0600 "$SOURCE_DIR/.ghcr.env.example" "$INSTALL_ROOT/.ghcr.env.example"
  install -m 0600 "$SOURCE_DIR/.tunnel.env.example" "$INSTALL_ROOT/tunnel.env.example"
  fail "create $ENV_FILE from $INSTALL_ROOT/.env.example and fill it only on the VPS"
fi
chmod 0600 "$ENV_FILE"
grep -Eq '^GITHUB_TOKEN=.+$' "$ENV_FILE" || fail "GITHUB_TOKEN is not configured in $ENV_FILE"

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
  grep -E '^(SOVEREIGN_MCP_ALLOWED_CONTAINERS|SOVEREIGN_MCP_WORKSPACE_ROOT|SOVEREIGN_MCP_ENABLE_DB_WRITES|SOVEREIGN_MCP_ENABLE_DEPLOY|SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS|SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS|SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST|SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT|SOVEREIGN_MCP_PREVIEW_POSTGRES_DB|SOVEREIGN_MCP_PREVIEW_POSTGRES_USER|SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD|SOVEREIGN_BACKEND_IMAGE_REPOSITORY|SOVEREIGN_BACKEND_ENV_FILE)=' "$ENV_FILE" || true
  printf 'SOVEREIGN_MCP_DEPLOY_SCRIPT=%s\n' "$BIN_DIR/deploy-sovereign-backend"
  printf 'SOVEREIGN_MCP_ROLLBACK_SCRIPT=%s\n' "$BIN_DIR/rollback-sovereign-backend"
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
docker compose up -d --build

docker inspect sovereign-chatgpt-mcp >/dev/null
docker exec sovereign-chatgpt-mcp python -c 'import server; assert server.mcp is not None'
docker exec sovereign-chatgpt-mcp python -c 'from pathlib import Path; root=Path("/opt/sovereign-chatgpt-tools/workspaces"); probe=root/".permission-probe"; probe.write_text("ok", encoding="utf-8"); probe.unlink()'

if [[ -f "$TUNNEL_ENV" ]] \
  && grep -Eq '^OPENAI_TUNNEL_ID=tunnel_.+' "$TUNNEL_ENV" \
  && grep -Eq '^CONTROL_PLANE_API_KEY=.+$' "$TUNNEL_ENV"; then
  "$BIN_DIR/install-secure-tunnel"
else
  printf 'Tunnel not installed: configure %s when the OpenAI tunnel_id and runtime key are available.\n' "$TUNNEL_ENV"
fi

printf '{"ok":true,"mcp":"http://127.0.0.1:8090/mcp","broker":"active","container":"sovereign-chatgpt-mcp","workspace_writable":true}\n'
