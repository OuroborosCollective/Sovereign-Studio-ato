#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="/opt/sovereign-chatgpt-tools"
BIN_DIR="$INSTALL_ROOT/bin"
BROKER_DIR="$INSTALL_ROOT/broker"
WORKSPACE_DIR="$INSTALL_ROOT/workspaces"
ENV_FILE="$INSTALL_ROOT/.env"
BROKER_ENV="$INSTALL_ROOT/broker.env"
SERVICE_FILE="/etc/systemd/system/sovereign-chatgpt-broker.service"

fail() {
  printf 'install blocked: %s\n' "$*" >&2
  exit 1
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
  fail "create $ENV_FILE from $INSTALL_ROOT/.env.example and fill it only on the VPS"
fi
chmod 0600 "$ENV_FILE"
grep -Eq '^GITHUB_TOKEN=.+$' "$ENV_FILE" || fail "GITHUB_TOKEN is not configured in $ENV_FILE"

# The root broker does not receive GitHub or database credentials.
{
  grep -E '^(SOVEREIGN_MCP_ALLOWED_CONTAINERS|SOVEREIGN_MCP_ENABLE_DEPLOY|SOVEREIGN_BACKEND_IMAGE_REPOSITORY|SOVEREIGN_BACKEND_ENV_FILE)=' "$ENV_FILE" || true
  printf 'SOVEREIGN_MCP_DEPLOY_SCRIPT=%s\n' "$BIN_DIR/deploy-sovereign-backend"
  printf 'SOVEREIGN_MCP_ROLLBACK_SCRIPT=%s\n' "$BIN_DIR/rollback-sovereign-backend"
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
