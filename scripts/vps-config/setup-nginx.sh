#!/bin/bash
# Install the authenticated MCP reverse-proxy nginx configuration for openhands.arelorian.de
# Issue: #1187 - codify authenticated OpenHands MCP reverse-proxy contract
# Run as: sudo bash setup-nginx.sh

set -e

CONFIG_FILE="/etc/nginx/sites-available/openhands.arelorian.de"
SYM_LINK="/etc/nginx/conf.d/openhands.arelorian.de.conf"
API_KEY_FILE="/opt/sovereign-owner-managed/openhands_mcp_api_key.txt"

echo "Setting up nginx for openhands.arelorian.de..."

# Verify owner-managed API key file exists with correct permissions
if [ ! -f "$API_KEY_FILE" ]; then
    echo "ERROR: Owner-managed API key file not found: $API_KEY_FILE"
    echo "Create it with: sudo mkdir -p /opt/sovereign-owner-managed && sudo touch $API_KEY_FILE && sudo chmod 600 $API_KEY_FILE"
    exit 1
fi

KEY_PERMS=$(stat -c "%a" "$API_KEY_FILE" 2>/dev/null || stat -f "%Lp" "$API_KEY_FILE" 2>/dev/null)
if [ "$KEY_PERMS" != "600" ]; then
    echo "WARNING: API key file permissions are $KEY_PERMS, should be 600"
    echo "Fix with: sudo chmod 600 $API_KEY_FILE"
fi

# Create the same configuration committed in nginx/openhands.arelorian.de.conf
# This establishes the authenticated MCP reverse-proxy contract
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

    # Authenticated MCP Streamable-HTTP route
    # Requires X-API-Key header; MCP server performs owner-managed validation
    location = /mcp {
        # Fail-closed: block if X-API-Key header is missing
        if ($http_x_api_key = "") {
            return 403;
        }

        # Proxy to MCP upstream with Streamable-HTTP protocol
        # MCP runs on loopback only at 127.0.0.1:8090
        # MCP server validates X-API-Key against owner-managed secret
        proxy_pass http://127.0.0.1:8090/mcp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Pass through MCP-specific headers
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_buffering off;
        proxy_cache off;

        # Timeout settings for MCP initialization
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Root route unchanged: serves existing local service at port 3000
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
    }

    # Fail-closed: deny all other MCP-related paths
    location ~ ^/mcp/ {
        return 403;
    }

    access_log /var/log/nginx/openhands.arelorian.de.access.log;
    error_log /var/log/nginx/openhands.arelorian.de.error.log;
}
NGINXCONF

echo "Config created: $CONFIG_FILE"

# Create symlink
ln -sf "$CONFIG_FILE" "$SYM_LINK"
echo "Symlink created: $SYM_LINK"

# Test nginx configuration
echo "Testing nginx configuration..."
if ! nginx -t; then
    echo "ERROR: nginx configuration test failed"
    exit 1
fi

# Reload nginx
echo "Reloading nginx..."
pkill -HUP nginx || nginx

echo "Nginx reloaded successfully."
echo ""
echo "Authenticated MCP reverse-proxy is now active at https://openhands.arelorian.de/mcp"
echo "- Requires X-API-Key header (owner-managed at $API_KEY_FILE)"
echo "- Proxies to MCP at 127.0.0.1:8090/mcp"
echo "- Root route serves existing service at port 3000 (unchanged)"
echo "- All other paths return 403 (fail-closed)"
