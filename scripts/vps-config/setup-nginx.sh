#!/bin/bash
# Install the deliberate fail-closed nginx configuration for openhands.arelorian.de
# Run as: sudo bash setup-nginx.sh

set -e

CONFIG_FILE="/etc/nginx/sites-available/openhands.arelorian.de"
SYM_LINK="/etc/nginx/conf.d/openhands.arelorian.de.conf"

echo "Setting up nginx for openhands.arelorian.de..."

# Create the same fail-closed server blocks committed in nginx/openhands.arelorian.de.conf.
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

    # Fail-closed: return 403 for all requests.
    # MCP route at /mcp requires a separate authenticated TLS reverse-proxy contract.
    # This response header makes the deliberate fail-closed state observable to clients.
    add_header X-Sovereign-Fail-Closed "issue#1196-proxy-drift" always;

    location / {
        return 403;
    }

    location /sockets {
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

# Test nginx
nginx -t

# Reload nginx
pkill -HUP nginx || nginx

echo "Nginx reloaded. openhands.arelorian.de is deliberately fail-closed with HTTP 403 until an authenticated upstream is approved."
