#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SOURCE_DIR="${1:-}"
ROOT="/opt/sovereign-legacy-mcp"
TARGET="$ROOT/sovereign-toolchain"
COMMON_SOURCE="$(dirname "$SOURCE_DIR")/sovereign-legacy-mcp-common"
COMMON_TARGET="$ROOT/sovereign-legacy-mcp-common"
UNIT_SOURCE="$SOURCE_DIR/deploy/sovereign-toolchain.service"
UNIT_TARGET="/etc/systemd/system/sovereign-toolchain.service"
ENV_TARGET="/etc/sovereign-toolchain/runtime.env"
SERVICE="sovereign-toolchain.service"
KEY_SOURCE="/opt/secure/sovereign-github-app/private-key.pem"
BACKUP_ROOT="/var/lib/sovereign-toolchain-installer"

fail() {
  local reason="$1"
  printf 'SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=%s reason_sha256=%s\n' \
    "${STAGE:-unknown}" "$(printf '%s' "$reason" | sha256sum | awk '{print $1}')" >&2
  exit 1
}

STAGE=preflight
[[ -n "$SOURCE_DIR" && -d "$SOURCE_DIR" && ! -L "$SOURCE_DIR" ]] || fail "source directory invalid"
[[ -f "$SOURCE_DIR/pyproject.toml" && -f "$SOURCE_DIR/uv.lock" ]] || fail "locked toolchain source incomplete"
[[ -f "$UNIT_SOURCE" && ! -L "$UNIT_SOURCE" ]] || fail "unit source invalid"
[[ -d "$COMMON_SOURCE" && -f "$COMMON_SOURCE/github_app_auth.py" ]] || fail "common adapter source invalid"
[[ -f "$KEY_SOURCE" && ! -L "$KEY_SOURCE" ]] || fail "GitHub App private key source invalid"
KEY_UID="$(stat -c %u "$KEY_SOURCE")"
KEY_MODE="$(stat -c %a "$KEY_SOURCE")"
[[ "$KEY_UID" == "0" ]] || fail "GitHub App private key owner is invalid"
[[ "$KEY_MODE" == "600" || "$KEY_MODE" == "640" ]] || fail "GitHub App private key mode is invalid"
! grep -Eq '(^|[^A-Za-z0-9_])(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$UNIT_SOURCE" || fail "unit has persistent token source"

STAGE=stage
install -d -m 0700 -o root -g root "$ROOT" "$BACKUP_ROOT" /etc/sovereign-toolchain
TEMP="$(mktemp -d "$ROOT/.toolchain-stage.XXXXXX")"
cleanup_stage() { rm -rf "$TEMP"; }
trap cleanup_stage EXIT
install -d -m 0700 -o root -g root "$TEMP/sovereign-toolchain" "$TEMP/sovereign-legacy-mcp-common"
cp -a "$SOURCE_DIR/." "$TEMP/sovereign-toolchain/"
cp -a "$COMMON_SOURCE/." "$TEMP/sovereign-legacy-mcp-common/"
rm -rf "$TEMP/sovereign-toolchain/.venv"
(
  cd "$TEMP/sovereign-toolchain"
  uv sync --frozen --no-dev
)

STAGE=metadata
METADATA_READER="$SOURCE_DIR/deploy/read-broker-github-app-metadata.sh"
[[ -f "$METADATA_READER" && ! -L "$METADATA_READER" ]] || fail "broker metadata reader source invalid"
# Read only required literal App metadata. Never execute broker.env as shell code.
"$METADATA_READER" /opt/sovereign-chatgpt-tools/broker.env > "$TEMP/runtime.env"
SOVEREIGN_MCP_REPOSITORY="$(awk -F= '$1 == "SOVEREIGN_MCP_REPOSITORY" { print $2 }' "$TEMP/runtime.env")"
[[ -n "$SOVEREIGN_MCP_REPOSITORY" ]] || fail "missing repository metadata"
printf 'ALLOWED_REPOS=%s\nGITHUB_TIMEOUT_SECONDS=60\n' \
  "$SOVEREIGN_MCP_REPOSITORY" >> "$TEMP/runtime.env"
chmod 0600 "$TEMP/runtime.env"
! grep -Eq '^(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$TEMP/runtime.env" || fail "runtime environment has persistent GitHub token"

STAGE=activate
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
UNIT_BACKUP="$BACKUP_ROOT/sovereign-toolchain.service.$STAMP"
TARGET_BACKUP="$BACKUP_ROOT/sovereign-toolchain.$STAMP"
ENV_BACKUP="$BACKUP_ROOT/runtime.env.$STAMP"
[[ -f "$UNIT_TARGET" ]] && cp -a "$UNIT_TARGET" "$UNIT_BACKUP" || :
[[ -d "$TARGET" ]] && mv "$TARGET" "$TARGET_BACKUP" || :
[[ -f "$ENV_TARGET" ]] && cp -a "$ENV_TARGET" "$ENV_BACKUP" || :
mv "$TEMP/sovereign-toolchain" "$TARGET"
mv "$TEMP/sovereign-legacy-mcp-common" "$COMMON_TARGET"
install -m 0644 -o root -g root "$UNIT_SOURCE" "$UNIT_TARGET"
install -m 0600 -o root -g root "$TEMP/runtime.env" "$ENV_TARGET"
systemctl daemon-reload
rollback() {
  systemctl stop "$SERVICE" || true
  rm -rf "$TARGET" "$COMMON_TARGET"
  [[ -e "$TARGET_BACKUP" ]] && mv "$TARGET_BACKUP" "$TARGET" || true
  [[ -e "$UNIT_BACKUP" ]] && cp -a "$UNIT_BACKUP" "$UNIT_TARGET" || true
  [[ -e "$ENV_BACKUP" ]] && cp -a "$ENV_BACKUP" "$ENV_TARGET" || true
  systemctl daemon-reload
  systemctl start "$SERVICE" || true
}
if ! systemctl restart "$SERVICE"; then rollback; fail "service restart failed"; fi

STAGE=readback
for _ in $(seq 1 20); do
  if python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:8001/', timeout=3) as response:
    payload=json.loads(response.read().decode('utf-8'))
assert payload == {'ok': True, 'name': 'Sovereign Universal Toolchain', 'rest': '/api/v1/manifest', 'openapi': '/api/openapi.json', 'mcp': '/mcp'}
PY
  then break; fi
  sleep 1
done
if ! python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:8001/', timeout=3) as response:
    payload=json.loads(response.read().decode('utf-8'))
assert payload == {'ok': True, 'name': 'Sovereign Universal Toolchain', 'rest': '/api/v1/manifest', 'openapi': '/api/openapi.json', 'mcp': '/mcp'}
PY
then rollback; fail "health readback failed"; fi
PID="$(systemctl show --property MainPID --value "$SERVICE")"
[[ "$PID" =~ ^[1-9][0-9]*$ ]] || { rollback; fail "service process missing"; }
if tr '\0' '\n' < "/proc/$PID/environ" | grep -qE '^(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)='; then rollback; fail "persistent GitHub token inherited by service"; fi
printf 'SOVEREIGN_TOOLCHAIN_INSTALL_OK service=%s token_free=true\n' "$SERVICE"
