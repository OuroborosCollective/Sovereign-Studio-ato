#!/bin/bash
# Setup nginx for OpenHands admin console
# Run as: sudo bash setup-nginx.sh

set -e

CONFIG_FILE="/etc/nginx/sites-available/openhands.arelorian.de"
SYM_LINK="/etc/nginx/conf.d/openhands.arelorian.de.conf"

echo "Setting up nginx for openhands.arelorian.de..."

# Create config
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
        proxy_request_buffering off;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /sockets {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
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

echo "Nginx reloaded. OpenHands admin should be available at https://openhands.arelorian.de"
