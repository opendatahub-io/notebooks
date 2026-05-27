#!/bin/bash
set -eu

NB_PREFIX="${NB_PREFIX:-}"
CODE_SERVER_DATA_DIR="/opt/app-root/src/.local/share/code-server"
mkdir -p "${CODE_SERVER_DATA_DIR}/User"

# Write VS Code settings
cat > "${CODE_SERVER_DATA_DIR}/User/settings.json" << 'SETTINGS'
{
  "python.defaultInterpreterPath": "/opt/app-root/bin/python3",
  "telemetry.telemetryLevel": "off",
  "extensions.autoCheckUpdates": false,
  "extensions.autoUpdate": false,
  "security.workspace.trust.enabled": false,
  "security.workspace.trust.startupPrompt": "never"
}
SETTINGS

# Generate nginx config that proxies 8888 -> code-server on 8787
# and handles the NB_PREFIX path rewriting
cat > /etc/nginx/nginx.conf << NGINX_EOF
worker_processes auto;
pid /run/nginx.pid;
error_log /var/log/nginx/error.log;

events {
    worker_connections 1024;
}

http {
    access_log /var/log/nginx/access.log;

    map \$http_upgrade \$connection_upgrade {
        default upgrade;
        '' close;
    }

    server {
        listen 8888;
        server_name _;

        location ${NB_PREFIX:-/}/ {
            proxy_pass http://127.0.0.1:8787/;
            proxy_set_header Host \$host;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection \$connection_upgrade;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_http_version 1.1;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
        }

        # Redirect /notebook/ns/name to /notebook/ns/name/ (trailing slash)
        location = ${NB_PREFIX:-} {
            return 302 \$scheme://\$host${NB_PREFIX:-/}/;
        }

        # Health check endpoint for readiness probe
        location ${NB_PREFIX:-/}/api {
            proxy_pass http://127.0.0.1:8787/healthz;
            proxy_set_header Host \$host;
        }
    }
}
NGINX_EOF

# Start nginx in background
nginx &

# IPv6 support for code-server
if [ -f /proc/net/if_inet6 ]; then
    BIND_ADDR="[::]:8787"
else
    BIND_ADDR="0.0.0.0:8787"
fi

# Start code-server
exec code-server \
    --bind-addr "${BIND_ADDR}" \
    --user-data-dir "${CODE_SERVER_DATA_DIR}" \
    --extensions-dir "${CODE_SERVER_DATA_DIR}/extensions" \
    --disable-telemetry \
    --auth none \
    --disable-update-check \
    --disable-getting-started-override \
    /opt/app-root/src
