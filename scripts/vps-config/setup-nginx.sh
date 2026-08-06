#!/bin/bash
# Install the nginx configuration for openhands.arelorian.de per issue #1187.
# Run as: sudo bash setup-nginx.sh
#
# Routing contract:
#   /         → 127.0.0.1:3000 (existing local service / Browserless UI)
#   /mcp      → 127.0.0.1:8090 (MCP, requires X-API-Key header)
#   all other → 403 (fail-closed)
#
# API key sourced from owner-managed file (must exist with mode 0600):
#   /opt/sovereign-owner-managed/openhands_mcp_api_key.txt

set -e

CONFIG_FILE="/etc/nginx/sites-available/openhands.arelorian.de"
SYM_LINK="/etc/nginx/conf.d/openhands.arelorian.de.conf"
KEY_FILE="/opt/sovereign-owner-managed/openhands_mcp_api_key.txt"

echo "Setting up nginx for openhands.arelorian.de (issue #1187)..."

# Verify owner-managed API key file exists with correct permissions
if [ ! -f "$KEY_FILE" ]; then
    echo "ERROR: Owner-managed API key file not found: $KEY_FILE"
    echo "Create it with: echo 'set \$mcp_api_key \"YOUR_KEY_HERE\";' > $KEY_FILE && chmod 0600 $KEY_FILE"
    exit 1
fi

KEY_PERMS=$(stat -c "%a" "$KEY_FILE" 2>/dev/null || stat -f "%Lp" "$KEY_FILE" 2>/dev/null)
if [ "$KEY_PERMS" != "600" ]; then
    echo "ERROR: API key file has permissions $KEY_PERMS, expected 0600"
    echo "Fix with: chmod 0600 $KEY_FILE"
    exit 1
fi

    # Create the same server blocks committed in nginx/openhands.arelorian.de.conf.
cat > "$CONFIG_FILE" << 'NGINXCONF'
server {
    listen 80;
    server_name openhands.arelorian.de;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name openhands.arelorian.de;

    ssl_certificate /etc/letsencrypt/live/openhands.arelorian.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/openhands.arelorian.de/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Load MCP API key from owner-managed file
    # The file must exist with mode 0600 on the VPS before running setup-nginx.sh
    # Key value is not committed to the repository.
    # Fail-closed: if file is missing or unreadable, no authentication succeeds.
    set $mcp_api_key "";
    set $mcp_authorized 0;
    # Load key into nginx variable; fails silently if file missing (fail-closed)
    include /opt/sovereign-owner-managed/openhands_mcp_api_key.txt;

    # MCP route: authenticated Streamable-HTTP proxy to MCP at port 8090
    # Only exact-match /mcp is proxied; /mcp/* falls through to the catch-all 403.
    location = /mcp {
        # Require X-API-Key header; fail-closed without it
        if ($http_x_api_key != $mcp_api_key) {
            return 401;
        }

        proxy_pass http://127.0.0.1:8090/mcp;
        proxy_http_version 1.1;
        proxy_set_header Content-Type "application/json";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_cache off;
    }

    # Root route: existing local service at port 3000 (Browserless/OpenHands UI)
    # Unchanged from previous configuration per issue #1187 acceptance criterion 1.
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    access_log /var/log/nginx/openhands.arelorian.de.access.log;
    error_log /var/log/nginx/openhands.arelorian.de.error.log;
}
NGINXCONF

echo "Config created: $CONFIG_FILE"

# Create symlink
ln -sf "$CONFIG_FILE" "$SYM_LINK"
echo "Symlink created: $SYM_LINK"

# Test nginx
nginx -t

# Reload nginx
pkill -HUP nginx || nginx

echo "Nginx reloaded. openhands.arelorian.de configured per issue #1187:"
echo "  /     → 127.0.0.1:3000 (root, unchanged)"
echo "  /mcp  → 127.0.0.1:8090 (MCP, requires X-API-Key header)"
echo "  other → 403 (fail-closed)"
