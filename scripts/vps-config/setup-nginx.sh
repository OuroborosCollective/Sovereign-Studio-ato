#!/usr/bin/env bash
# Install the canonical openhands.arelorian.de nginx contract for issue #1187.
# Run only as root on the VPS from the checked-out repository tree.

set -Eeuo pipefail

CONFIG_FILE="/etc/nginx/sites-available/openhands.arelorian.de"
SYM_LINK="/etc/nginx/conf.d/openhands.arelorian.de.conf"
KEY_FILE="/opt/sovereign-owner-managed/openhands_mcp_api_key.txt"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_CONFIG="$SCRIPT_DIR/nginx/openhands.arelorian.de.conf"
BACKUP_DIR="/var/backups/sovereign-nginx"
BACKUP_FILE=""
PREVIOUS_LINK_TARGET=""
HAD_CONFIG=0

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

if [ "$(id -u)" -ne 0 ]; then
    fail "run this installer as root"
fi

[ -f "$SOURCE_CONFIG" ] || fail "canonical nginx config is missing: $SOURCE_CONFIG"
[ -f "$KEY_FILE" ] || fail "owner-managed MCP key file is missing: $KEY_FILE"
[ ! -L "$KEY_FILE" ] || fail "owner-managed MCP key file must not be a symlink"

KEY_PERMS="$(stat -c "%a" "$KEY_FILE")"
KEY_OWNER="$(stat -c "%u:%g" "$KEY_FILE")"
[ "$KEY_PERMS" = "600" ] || fail "owner-managed MCP key file must have mode 0600"
[ "$KEY_OWNER" = "0:0" ] || fail "owner-managed MCP key file must be owned by root:root"

if [ -L "$SYM_LINK" ]; then
    PREVIOUS_LINK_TARGET="$(readlink "$SYM_LINK")"
fi

rollback() {
    echo "Rolling back nginx configuration..." >&2
    if [ "$HAD_CONFIG" -eq 1 ]; then
        install -m 0644 "$BACKUP_FILE" "$CONFIG_FILE"
    else
        rm -f "$CONFIG_FILE"
    fi

    if [ -n "$PREVIOUS_LINK_TARGET" ]; then
        ln -sfn "$PREVIOUS_LINK_TARGET" "$SYM_LINK"
    else
        rm -f "$SYM_LINK"
    fi

    nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
}

install -d -m 0755 "$(dirname "$CONFIG_FILE")" "$BACKUP_DIR"
if [ -f "$CONFIG_FILE" ]; then
    HAD_CONFIG=1
    BACKUP_FILE="$BACKUP_DIR/openhands.arelorian.de.$(date -u +%Y%m%dT%H%M%SZ).conf"
    install -m 0600 "$CONFIG_FILE" "$BACKUP_FILE"
fi

install -m 0644 "$SOURCE_CONFIG" "$CONFIG_FILE"
ln -sfn "$CONFIG_FILE" "$SYM_LINK"

if ! nginx -t; then
    rollback
    fail "nginx configuration validation failed; previous configuration was restored"
fi

if ! systemctl reload nginx; then
    rollback
    fail "nginx reload failed; previous configuration was restored"
fi

if ! systemctl is-active --quiet nginx; then
    rollback
    fail "nginx is not active after reload; previous configuration was restored"
fi

echo "Nginx contract installed for openhands.arelorian.de"
echo "  /       → existing root service"
echo "  /mcp    → authenticated loopback MCP upstream"
echo "  /mcp/*  → 404"
if [ -n "$BACKUP_FILE" ]; then
    echo "  backup  → $BACKUP_FILE"
fi
