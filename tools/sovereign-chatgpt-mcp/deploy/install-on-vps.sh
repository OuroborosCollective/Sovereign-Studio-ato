#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="/opt/sovereign-chatgpt-tools"
BIN_DIR="$INSTALL_ROOT/bin"
WORKSPACE_DIR="$INSTALL_ROOT/workspaces"
ENV_FILE="$INSTALL_ROOT/.env"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  printf 'install blocked: run as root on the VPS\n' >&2
  exit 1
fi

command -v docker >/dev/null 2>&1 || {
  printf 'install blocked: docker is not installed\n' >&2
  exit 1
}
docker compose version >/dev/null 2>&1 || {
  printf 'install blocked: docker compose plugin is not installed\n' >&2
  exit 1
}

install -d -m 0750 "$INSTALL_ROOT" "$BIN_DIR" "$WORKSPACE_DIR"
install -m 0750 "$SOURCE_DIR/deploy/deploy-sovereign-backend" "$BIN_DIR/deploy-sovereign-backend"
install -m 0750 "$SOURCE_DIR/deploy/rollback-sovereign-backend" "$BIN_DIR/rollback-sovereign-backend"
install -m 0644 "$SOURCE_DIR/docker-compose.yml" "$INSTALL_ROOT/docker-compose.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$SOURCE_DIR/.env.example" "$ENV_FILE.example"
  printf 'install blocked: create %s from %s and fill only on the VPS\n' "$ENV_FILE" "$ENV_FILE.example" >&2
  exit 1
fi
chmod 0600 "$ENV_FILE"

if ! grep -Eq '^GITHUB_TOKEN=.+$' "$ENV_FILE"; then
  printf 'install blocked: GITHUB_TOKEN is not configured in %s\n' "$ENV_FILE" >&2
  exit 1
fi

DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
export DOCKER_GID
cd "$INSTALL_ROOT"
docker compose config >/dev/null
docker compose up -d --build

docker inspect sovereign-chatgpt-mcp >/dev/null
printf 'Sovereign ChatGPT MCP installed on loopback: http://127.0.0.1:8090/mcp\n'
printf 'Connect it through an authenticated TLS proxy or the OpenAI Secure MCP Tunnel; never expose port 8090 directly.\n'
