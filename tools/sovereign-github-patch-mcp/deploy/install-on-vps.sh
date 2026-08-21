#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SOURCE_DIR="${1:?canonical sovereign-mcp source directory is required}"
TARGET_ROOT="${SOVEREIGN_LEGACY_MCP_ROOT:-/opt/sovereign-legacy-mcp}"
SERVICE="sovereign-mcp.service"
UNIT_SOURCE="$SOURCE_DIR/deploy/$SERVICE"
UNIT_TARGET="/etc/systemd/system/$SERVICE"
RUNTIME_ENV="/etc/sovereign-github-patch-mcp/runtime.env"
BROKER_ENV="/opt/sovereign-chatgpt-tools/broker.env"
KEY_SOURCE="/opt/secure/sovereign-github-app/private-key.pem"
STAGE="$(mktemp -d /opt/.sovereign-legacy-mcp-stage.XXXXXX)"
BACKUP="$(mktemp -d /root/.sovereign-mcp-rollback.XXXXXX)"
INSTALLED=0

fail() { printf 'SOVEREIGN_MCP_INSTALL_FAILURE stage=%s reason=%s\n' "${INSTALL_STAGE:-unknown}" "$1" >&2; exit 1; }
restore_previous() {
  code=$?
  if [[ "$INSTALLED" == 1 ]]; then
    if [[ -f "$BACKUP/unit" ]]; then
      cp -a "$BACKUP/unit" "$UNIT_TARGET" || true
    fi
    if [[ -d "$BACKUP/runtime-root" ]]; then
      rm -rf "$TARGET_ROOT" || true
      mv "$BACKUP/runtime-root" "$TARGET_ROOT" || true
    fi
    systemctl daemon-reload || true
    systemctl restart "$SERVICE" || true
  fi
  rm -rf "$STAGE" "$BACKUP" || true
  exit "$code"
}
trap restore_previous EXIT

INSTALL_STAGE=validate_source
[[ -d "$SOURCE_DIR" && ! -L "$SOURCE_DIR" ]] || fail "source directory is invalid"
[[ -f "$SOURCE_DIR/server.py" && ! -L "$SOURCE_DIR/server.py" ]] || fail "server source is invalid"
[[ -f "$UNIT_SOURCE" && ! -L "$UNIT_SOURCE" ]] || fail "unit source is invalid"
[[ -f "$BROKER_ENV" && ! -L "$BROKER_ENV" ]] || fail "broker environment is invalid"
[[ -f "$KEY_SOURCE" && ! -L "$KEY_SOURCE" ]] || fail "GitHub App private key is unavailable"
KEY_UID="$(stat -c '%u' "$KEY_SOURCE")"
KEY_MODE="$(stat -c '%a' "$KEY_SOURCE")"
[[ "$KEY_UID" == "0" ]] || fail "GitHub App private key owner is invalid"
[[ "$KEY_MODE" =~ ^0?6[04]0$ ]] || fail "GitHub App private key mode is invalid"
! grep -qE '^\s*(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$SOURCE_DIR/.env.example" || fail "token legacy variable remains in environment template"
! grep -qE '^\s*(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$UNIT_SOURCE" || fail "persistent token directive remains in unit source"

grep -q '^SOVEREIGN_MCP_GITHUB_APP_ID=[1-9][0-9]*$' "$BROKER_ENV" || fail "GitHub App id missing"
grep -q '^SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID=[1-9][0-9]*$' "$BROKER_ENV" || fail "GitHub App installation id missing"
grep -q '^SOVEREIGN_MCP_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato$' "$BROKER_ENV" || fail "repository scope mismatch"

INSTALL_STAGE=stage_runtime
mkdir -p "$STAGE/runtime/sovereign-github-patch-mcp" "$STAGE/runtime/sovereign-legacy-mcp-common"
cp -a "$SOURCE_DIR/../sovereign-legacy-mcp-common/github_app_auth.py" "$STAGE/runtime/sovereign-legacy-mcp-common/github_app_auth.py"
cp -a "$SOURCE_DIR/server.py" "$STAGE/runtime/sovereign-github-patch-mcp/server.py"
cp -a "$SOURCE_DIR/pyproject.toml" "$STAGE/runtime/sovereign-github-patch-mcp/pyproject.toml"
cp -a "$SOURCE_DIR/uv.lock" "$STAGE/runtime/sovereign-github-patch-mcp/uv.lock"
uv sync --frozen --no-dev --project "$STAGE/runtime/sovereign-github-patch-mcp" || fail "locked Python runtime build failed"
install -d -m 0750 -o root -g root "$STAGE/etc/sovereign-github-patch-mcp"
awk -F= '/^(SOVEREIGN_MCP_GITHUB_APP_ID|SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID|SOVEREIGN_MCP_REPOSITORY)=/{print}' "$BROKER_ENV" > "$STAGE/etc/sovereign-github-patch-mcp/runtime.env"
printf '%s\n' 'ALLOWED_REPOS=OuroborosCollective/Sovereign-Studio-ato' 'HOST=0.0.0.0' 'PORT=8000' 'MCP_TRANSPORT_SECURITY_ENABLED=false' >> "$STAGE/etc/sovereign-github-patch-mcp/runtime.env"
chmod 0600 "$STAGE/etc/sovereign-github-patch-mcp/runtime.env"
! grep -qE '^\s*(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$STAGE/etc/sovereign-github-patch-mcp/runtime.env" || fail "staged runtime environment contains persistent token"
"$STAGE/runtime/sovereign-github-patch-mcp/.venv/bin/python" -m py_compile "$STAGE/runtime/sovereign-github-patch-mcp/server.py" "$STAGE/runtime/sovereign-legacy-mcp-common/github_app_auth.py" || fail "staged Python syntax invalid"

INSTALL_STAGE=backup_current
if [[ -d "$TARGET_ROOT" ]]; then mv "$TARGET_ROOT" "$BACKUP/runtime-root"; fi
if [[ -f "$UNIT_TARGET" ]]; then cp -a "$UNIT_TARGET" "$BACKUP/unit"; fi
mkdir -p "$TARGET_ROOT"
mv "$STAGE/runtime/sovereign-github-patch-mcp" "$TARGET_ROOT/sovereign-github-patch-mcp"
mv "$STAGE/runtime/sovereign-legacy-mcp-common" "$TARGET_ROOT/sovereign-legacy-mcp-common"
install -d -m 0750 -o root -g root /etc/sovereign-github-patch-mcp
mv "$STAGE/etc/sovereign-github-patch-mcp/runtime.env" "$RUNTIME_ENV"
install -m 0644 -o root -g root "$UNIT_SOURCE" "$UNIT_TARGET"
INSTALLED=1

INSTALL_STAGE=restart_service
systemctl daemon-reload
systemctl restart "$SERVICE"
for _ in $(seq 1 30); do
  if systemctl is-active --quiet "$SERVICE" && curl --fail --silent --max-time 3 http://127.0.0.1:8000/health | grep -q 'sovereign-github-patch-mcp'; then break; fi
  sleep 1
done
systemctl is-active --quiet "$SERVICE" || fail "service did not become active"
curl --fail --silent --max-time 3 http://127.0.0.1:8000/health | grep -q 'sovereign-github-patch-mcp' || fail "health endpoint failed"
MAIN_PID="$(systemctl show --property MainPID --value "$SERVICE")"
[[ "$MAIN_PID" =~ ^[1-9][0-9]*$ ]] || fail "service main PID unavailable"
! tr '\0' '\n' < "/proc/$MAIN_PID/environ" | grep -qE '^(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' || fail "persistent GitHub token inherited by service"
! grep -qE '^\s*(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$RUNTIME_ENV" || fail "runtime environment has persistent GitHub token"

INSTALL_STAGE=complete
printf 'SOVEREIGN_MCP_INSTALL_OK service=%s token_free=true\n' "$SERVICE"
INSTALLED=0
rm -rf "$STAGE" "$BACKUP"
trap - EXIT
