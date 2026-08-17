#!/bin/bash
# Retire the legacy OpenHands reverse-proxy integration per issue #1196.
# Run as: sudo bash setup-nginx.sh
#
# The historical hostname remains as a deny-only 410 vhost so requests cannot
# fall through to an unrelated default TLS server. No Browserless, MCP, agent,
# websocket, credential, or other upstream is exposed by this contract.

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_CONFIG="$SCRIPT_DIR/nginx/openhands.arelorian.de.conf"
CONFIG_FILE="/etc/nginx/sites-available/openhands.arelorian.de"
SYM_LINK="/etc/nginx/conf.d/openhands.arelorian.de.conf"
LEGACY_ENABLED_LINK="/etc/nginx/sites-enabled/openhands.arelorian.de"
BACKUP_ROOT="/var/backups/sovereign-nginx/openhands-retirement"
BACKUP_DIR=""

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "ERROR: OpenHands retirement must run as root"
    exit 1
fi

if [ ! -f "$SOURCE_CONFIG" ] || [ -L "$SOURCE_CONFIG" ]; then
    echo "ERROR: Canonical retired vhost is missing or is a symlink"
    exit 1
fi

# The retirement source must never regain an upstream or credential surface.
if grep -Eq 'proxy_pass|127\.0\.0\.1:(3000|8090)|mcp_api_key|X-API-Key|location[[:space:]]*=[[:space:]]*/mcp' "$SOURCE_CONFIG"; then
    echo "ERROR: Canonical retired vhost contains a forbidden legacy integration surface"
    exit 1
fi
if ! grep -Fq 'return 410;' "$SOURCE_CONFIG"; then
    echo "ERROR: Canonical retired vhost is not fail-closed"
    exit 1
fi

mkdir -p "$BACKUP_ROOT"
chmod 0700 "$BACKUP_ROOT"
BACKUP_DIR="$(mktemp -d "$BACKUP_ROOT/retire.XXXXXXXX")"
chmod 0700 "$BACKUP_DIR"

backup_path() {
    local target="$1"
    local name="$2"
    if [ -e "$target" ] || [ -L "$target" ]; then
        cp -a -- "$target" "$BACKUP_DIR/$name"
    fi
}

restore_path() {
    local target="$1"
    local name="$2"
    rm -f -- "$target"
    if [ -e "$BACKUP_DIR/$name" ] || [ -L "$BACKUP_DIR/$name" ]; then
        cp -a -- "$BACKUP_DIR/$name" "$target"
    fi
}

rollback() {
    echo "Retirement validation failed; restoring previous nginx paths"
    restore_path "$CONFIG_FILE" "sites-available"
    restore_path "$SYM_LINK" "conf-d"
    restore_path "$LEGACY_ENABLED_LINK" "sites-enabled"
    nginx -t || true
    systemctl reload nginx || true
}

backup_path "$CONFIG_FILE" "sites-available"
backup_path "$SYM_LINK" "conf-d"
backup_path "$LEGACY_ENABLED_LINK" "sites-enabled"

# Remove a historical sites-enabled link and replace the active conf.d path with
# one canonical deny-only vhost. Browserless and MCP runtimes are untouched.
rm -f -- "$LEGACY_ENABLED_LINK" "$SYM_LINK"
install -o root -g root -m 0644 "$SOURCE_CONFIG" "$CONFIG_FILE"
ln -s "$CONFIG_FILE" "$SYM_LINK"

if ! nginx -t; then
    rollback
    exit 1
fi

if ! systemctl reload nginx; then
    rollback
    exit 1
fi

if ! systemctl is-active --quiet nginx; then
    rollback
    exit 1
fi

# Read back the installed file and reject any silent reintroduction of the old
# Browserless/MCP proxy or credential include before declaring retirement.
if grep -Eq 'proxy_pass|127\.0\.0\.1:(3000|8090)|mcp_api_key|X-API-Key|location[[:space:]]*=[[:space:]]*/mcp' "$CONFIG_FILE"; then
    rollback
    echo "ERROR: Installed vhost still contains a legacy OpenHands integration surface"
    exit 1
fi
if ! grep -Fq 'return 410;' "$CONFIG_FILE"; then
    rollback
    echo "ERROR: Installed vhost is not fail-closed"
    exit 1
fi

printf '%s\n' \
    "OPENHANDS_RUNTIME_RETIRED" \
    "vhost=openhands.arelorian.de" \
    "http_status=410" \
    "browserless_proxy_present=false" \
    "mcp_proxy_present=false" \
    "credential_include_present=false" \
    "nginx_config_valid=true" \
    "nginx_service_active=true" \
    "backup_dir=$BACKUP_DIR"
