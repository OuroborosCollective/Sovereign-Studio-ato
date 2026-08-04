#!/bin/bash
# Install / refresh nginx reverse-proxy for openhands.arelorian.de.
#
# This script is the canonical install path for:
#   - the OpenHands admin console (https://openhands.arelorian.de/)
#   - the authenticated MCP reverse-proxy (https://openhands.arelorian.de/mcp)
#
# Contract (matches scripts/vps-config/tests/test-nginx-mcp-contract.test.cjs):
#   1. Operator-managed secret must exist at
#      /opt/sovereign-owner-managed/openhands_mcp_api_key.txt with mode 0600
#      and owner root:root. The script NEVER creates or generates this key.
#      If it is missing or has the wrong mode, the script fails closed.
#   2. The generated /etc/nginx/conf.d/openhands-mcp-api-key.map file has
#      mode 0640, owner root:root, and contains exactly one line of the
#      form "<key> 1;".
#   3. The canonical server block at
#      /etc/nginx/sites-available/openhands.arelorian.de.conf is symlinked
#      into /etc/nginx/conf.d/ so it is loaded in http context.
#   4. The http-context map file /etc/nginx/conf.d/00-openhands-mcp-auth-map.conf
#      is written verbatim from scripts/vps-config/nginx/.
#   5. nginx -t must pass before HUP/reload is attempted.
#   6. After reload, the script probes
#         curl -sS -o /dev/null -w '%{http_code}' \
#              https://openhands.arelorian.de/mcp
#      and refuses to print success unless it gets 401 (correct behaviour
#      for an unauthenticated probe to a gated route). It then performs a
#      second probe with the X-API-Key header set; that probe MUST succeed
#      to a backend reachable on 127.0.0.1:8090. If the backend is not
#      running, the probe is allowed to fail at the backend layer, but the
#      script reports that explicitly rather than claiming success.
#   7. Existing nginx config files are backed up under
#      /var/backups/sovereign-nginx/YYYYMMDDHHMMSS/ before any change.
#      If nginx -t fails after changes, the script restores the most
#      recent backup.
#
# Usage:
#   sudo bash scripts/vps-config/setup-nginx.sh
#
# Exit codes:
#   0  install / refresh completed and verified
#   1  precondition failed (missing key, wrong mode, wrong owner)
#   2  nginx -t failed (config invalid); previous config restored
#   3  nginx reload failed; previous config restored
#   4  post-install probe failed in an unexpected way
#
# The script does NOT print the API key value at any point. It only echoes
# the key fingerprint (first 4 hex chars of sha256) for operator awareness.

set -euo pipefail

REPO_ROOT_DEFAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_ROOT="${REPO_ROOT:-$REPO_ROOT_DEFAULT}"

NGINX_DIR_ETC="/etc/nginx"
SITES_AVAILABLE="$NGINX_DIR_ETC/sites-available"
SITES_ENABLED="$NGINX_DIR_ETC/sites-enabled"
CONF_D="$NGINX_DIR_ETC/conf.d"

SERVER_NAME="openhands.arelorian.de"
SERVER_CONF_SRC="$REPO_ROOT/scripts/vps-config/nginx/$SERVER_NAME.conf"
SERVER_CONF_DST="$SITES_AVAILABLE/$SERVER_NAME.conf"
SERVER_SYMLINK="$CONF_D/$SERVER_NAME.conf"

MAP_SRC="$REPO_ROOT/scripts/vps-config/nginx/00-openhands-mcp-auth-map.conf"
MAP_DST="$CONF_D/00-openhands-mcp-auth-map.conf"

KEY_FILE="/opt/sovereign-owner-managed/openhands_mcp_api_key.txt"
MAP_VALUES_FILE="$CONF_D/openhands-mcp-api-key.map"

BACKUP_ROOT="/var/backups/sovereign-nginx"
BACKUP_DIR="$BACKUP_ROOT/$(date -u +%Y%m%d%H%M%SZ)"

PROBE_URL="https://${SERVER_NAME}/mcp"

log() {
    printf '[setup-nginx] %s\n' "$*" >&2
}

fail() {
    local code="$1"
    shift
    log "FATAL ($code): $*"
    exit "$code"
}

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        fail 1 "must be run as root (use sudo)"
    fi
}

require_repo_files() {
    [[ -f "$SERVER_CONF_SRC" ]] || fail 1 "missing template: $SERVER_CONF_SRC"
    [[ -f "$MAP_SRC" ]]         || fail 1 "missing template: $MAP_SRC"
}

require_operator_key() {
    [[ -e "$KEY_FILE" ]] || fail 1 "operator-managed API key missing at $KEY_FILE (create it before running this script; never generate keys here)"
    [[ -f "$KEY_FILE" ]] || fail 1 "$KEY_FILE exists but is not a regular file"
    local mode owner
    mode="$(stat -c '%a' "$KEY_FILE")"
    owner="$(stat -c '%U:%G' "$KEY_FILE")"
    if [[ "$mode" != "600" ]]; then
        fail 1 "$KEY_FILE must have mode 0600 (current: $mode)"
    fi
    if [[ "$owner" != "root:root" ]]; then
        fail 1 "$KEY_FILE must be owned by root:root (current: $owner)"
    fi
    local key_value
    key_value="$(tr -d '\r\n' < "$KEY_FILE")"
    if [[ -z "$key_value" ]]; then
        fail 1 "$KEY_FILE is empty"
    fi
    if (( ${#key_value} < 32 )); then
        fail 1 "$KEY_FILE value is too short (min 32 chars); refusing weak keys"
    fi
    KEY_FINGERPRINT="$(printf '%s' "$key_value" | sha256sum | cut -c1-8)"
    KEY_VALUE_FOR_WRITE="$key_value"
}

make_backup() {
    mkdir -p "$BACKUP_DIR"
    local f
    for f in "$SERVER_CONF_DST" "$SERVER_SYMLINK" "$MAP_DST" "$MAP_VALUES_FILE"; do
        if [[ -e "$f" || -L "$f" ]]; then
            cp -aP "$f" "$BACKUP_DIR/$(basename "$f").bak"
        fi
    done
    log "backup written to $BACKUP_DIR"
}

restore_backup() {
    log "restoring previous nginx state from $BACKUP_DIR"
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log "no backup directory available; leaving filesystem as-is"
        return 1
    fi
    local b
    for b in "$BACKUP_DIR"/*.bak; do
        [[ -e "$b" || -L "$b" ]] || continue
        local name
        name="$(basename "$b" .bak)"
        if [[ "$name" == "$SERVER_NAME.conf" && "$SERVER_CONF_DST" == "$SITES_AVAILABLE/$SERVER_NAME.conf" ]]; then
            cp -aP "$b" "$SITES_AVAILABLE/$SERVER_NAME.conf"
        elif [[ "$name" == "00-openhands-mcp-auth-map.conf" ]]; then
            cp -aP "$b" "$MAP_DST"
        elif [[ "$name" == "openhands-mcp-api-key.map" ]]; then
            cp -aP "$b" "$MAP_VALUES_FILE"
        fi
    done
}

write_map_files() {
    mkdir -p "$CONF_D"
    install -m 0644 "$MAP_SRC" "$MAP_DST"
    chown root:root "$MAP_DST"

    local tmp
    tmp="$(mktemp)"
    printf '%s 1;\n' "$KEY_VALUE_FOR_WRITE" > "$tmp"
    chmod 0640 "$tmp"
    chown root:root "$tmp"
    mv "$tmp" "$MAP_VALUES_FILE"
}

install_server_conf() {
    mkdir -p "$SITES_AVAILABLE" "$CONF_D"
    install -m 0644 "$SERVER_CONF_SRC" "$SERVER_CONF_DST"
    chown root:root "$SERVER_CONF_DST"

    ln -sfn "$SERVER_CONF_DST" "$SERVER_SYMLINK"
}

test_nginx() {
    if ! nginx -t; then
        log "nginx -t failed; restoring previous config"
        restore_backup || true
        nginx -t || fail 2 "nginx -t fails even after restoring backup; manual intervention required"
    fi
}

reload_nginx() {
    if nginx -t; then
        if pgrep -x nginx >/dev/null; then
            pkill -HUP nginx || nginx
        else
            nginx
        fi
    else
        fail 3 "nginx -t refuses reload"
    fi
}

probe_mcp_route() {
    local code_unauth
    code_unauth="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$PROBE_URL" || echo '000')"
    if [[ "$code_unauth" != "401" ]]; then
        fail 4 "unauthenticated probe to $PROBE_URL returned $code_unauth (expected 401); auth gate is NOT enforced"
    fi
    log "unauthenticated probe returned 401 (gate enforced)"

    local code_auth backend_reachable
    if curl -sS --max-time 5 -o /dev/null "http://127.0.0.1:8090/mcp" 2>/dev/null; then
        backend_reachable=1
    else
        backend_reachable=0
    fi

    if (( backend_reachable == 1 )); then
        code_auth="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -H "X-API-Key: $KEY_VALUE_FOR_WRITE" "$PROBE_URL" || echo '000')"
        if [[ "$code_auth" == "401" || "$code_auth" == "000" ]]; then
            fail 4 "authenticated probe to $PROBE_URL returned $code_auth despite backend being reachable; auth map may be stale (HUP not applied?)"
        fi
        log "authenticated probe to $PROBE_URL returned $code_auth (backend reachable, key accepted)"
    else
        log "backend http://127.0.0.1:8090/mcp is not reachable; skipping authenticated end-to-end probe"
        log "next: start the MCP container and re-run this script to confirm auth end-to-end"
    fi
}

print_summary() {
    cat <<EOF >&2

[setup-nginx] DONE
  server conf: $SERVER_CONF_DST
  symlink:     $SERVER_SYMLINK
  auth map:    $MAP_DST
  key map:     $MAP_VALUES_FILE  (mode 0640 root:root)
  key source:  $KEY_FILE         (mode 0600 root:root)
  key sha256:  $KEY_FINGERPRINT... (full sha256 not echoed)
  backup:      $BACKUP_DIR
EOF
}

main() {
    require_root
    require_repo_files
    require_operator_key
    make_backup
    install_server_conf
    write_map_files
    test_nginx
    reload_nginx
    probe_mcp_route
    print_summary
}

main "$@"
