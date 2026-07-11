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
BROKER_ENV="$INSTALL_ROOT/broker.env"
SERVICE_FILE="/etc/systemd/system/sovereign-chatgpt-broker.service"

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
command -v docker >/dev/null 2>&1 || fail "docker is not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed"
command -v systemctl >/dev/null 2>&1 || fail "systemd is not available"
[[ -S /var/run/docker.sock ]] || fail "docker socket is missing"

getent group sovereign-mcp >/dev/null 2>&1 || groupadd --system sovereign-mcp
install -d -m 0750 "$INSTALL_ROOT" "$BIN_DIR" "$BROKER_DIR" "$WORKSPACE_DIR"

# MCP container build context.
for file in Dockerfile requirements.txt policy.py runtime.py database.py broker_client.py server.py docker-compose.yml; do
  install -m 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file"
done

# Root host broker receives only fixed Docker actions, never arbitrary shell.
install -m 0640 "$SOURCE_DIR/broker.py" "$BROKER_DIR/broker.py"
install -m 0640 "$SOURCE_DIR/operations.py" "$BROKER_DIR/operations.py"
install -m 0640 "$SOURCE_DIR/policy.py" "$BROKER_DIR/policy.py"
install -m 0750 "$SOURCE_DIR/deploy/deploy-sovereign-backend" "$BIN_DIR/deploy-sovereign-backend"
install -m 0750 "$SOURCE_DIR/deploy/rollback-sovereign-backend" "$BIN_DIR/rollback-sovereign-backend"
install -m 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-broker.service" "$SERVICE_FILE"
chown -R root:sovereign-mcp "$BROKER_DIR" "$BIN_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$SOURCE_DIR/.env.example" "$INSTALL_ROOT/.env.example"
  install -m 0600 "$SOURCE_DIR/.ghcr.env.example" "$INSTALL_ROOT/.ghcr.env.example"
  fail "create $ENV_FILE from $INSTALL_ROOT/.env.example and fill it only on the VPS"
fi
chmod 0600 "$ENV_FILE"
grep -Eq '^GITHUB_TOKEN=.+$' "$ENV_FILE" || fail "GITHUB_TOKEN is not configured in $ENV_FILE"

# Optional private GHCR login. The token is converted into Docker's host-only config
# and is never copied into broker.env or the MCP container environment.
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

# The root broker does not receive GitHub or database credentials.
{
  grep -E '^(SOVEREIGN_MCP_ALLOWED_CONTAINERS|SOVEREIGN_MCP_ENABLE_DEPLOY|SOVEREIGN_BACKEND_IMAGE_REPOSITORY|SOVEREIGN_BACKEND_ENV_FILE)=' "$ENV_FILE" || true
  printf 'SOVEREIGN_MCP_DEPLOY_SCRIPT=%s\n' "$BIN_DIR/deploy-sovereign-backend"
  printf 'SOVEREIGN_MCP_ROLLBACK_SCRIPT=%s\n' "$BIN_DIR/rollback-sovereign-backend"
  if [[ -n "$DOCKER_CONFIG_VALUE" ]]; then
    printf 'DOCKER_CONFIG=%s\n' "$DOCKER_CONFIG_VALUE"
  fi
} > "$BROKER_ENV"
chmod 0600 "$BROKER_ENV"
chown root:root "$BROKER_ENV"

systemctl daemon-reload
systemctl enable --now sovereign-chatgpt-broker.service
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
printf 'Sovereign ChatGPT MCP installed on loopback: http://127.0.0.1:8090/mcp\n'
printf 'Docker access is isolated behind /run/sovereign-chatgpt-broker/operator.sock.\n'
printf 'Connect through an authenticated TLS proxy or OpenAI Secure MCP Tunnel; never expose port 8090 directly.\n'
