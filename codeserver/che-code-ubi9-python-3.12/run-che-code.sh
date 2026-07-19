#!/bin/bash
set -e

# Source utility scripts
for f in /opt/app-root/bin/utils/*.sh; do source "$f"; done

# Start NGINX on port 8888 (proxies to che-code on 3100)
/opt/app-root/bin/run-nginx.sh &

# Start culler server (port 8080) — Python replacement for httpd CGI
python3 /opt/app-root/bin/culler-server.py &

# Initialize culler log so first culler query doesn't fail
mkdir -p /var/log/nginx
echo "[{\"id\":\"che-code\",\"name\":\"che-code\",\"last_activity\":\"$(date -Iseconds)\",\"execution_state\":\"busy\",\"connections\":1}]" \
    > /var/log/nginx/checode.access.log

# Custom prompt
echo 'PS1="\[\e[34;1m\]\u:\w \$ \[\e[0m\]"' >> "${HOME}/.bashrc"

# VS Code user settings (only written on first start, not overwritten on restart)
VSCODE_DATA_DIR="${HOME}/.vscode-server"
VSCODE_USER_SETTINGS_DIR="${VSCODE_DATA_DIR}/data/User"
VSCODE_USER_SETTINGS="${VSCODE_USER_SETTINGS_DIR}/settings.json"
if [[ ! -f "${VSCODE_USER_SETTINGS}" ]]; then
    mkdir -p "${VSCODE_USER_SETTINGS_DIR}"
    cat > "${VSCODE_USER_SETTINGS}" << 'SETTINGS_EOF'
{
  "python.defaultInterpreterPath": "/opt/app-root/bin/python3",
  "telemetry.telemetryLevel": "off",
  "telemetry.enableTelemetry": false,
  "workbench.enableExperiments": false,
  "extensions.autoCheckUpdates": false,
  "extensions.autoUpdate": false,
  "chat.disableAIFeatures": true,
  "security.workspace.trust.enabled": false,
  "security.workspace.trust.startupPrompt": "never"
}
SETTINGS_EOF
fi

# Set LD_LIBRARY_PATH for bundled native libs (libnode, libbrotli, libz, libssl, libcrypto)
CHECODE_DIR=/opt/app-root/checode
if [[ -d "${CHECODE_DIR}/ld_libs/core" ]]; then
    export LD_LIBRARY_PATH="${CHECODE_DIR}/ld_libs/core${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
if [[ -d "${CHECODE_DIR}/ld_libs/openssl" ]]; then
    export LD_LIBRARY_PATH="${CHECODE_DIR}/ld_libs/openssl:$LD_LIBRARY_PATH"
fi

# Detect bind address
HOST="0.0.0.0"

# Launch che-code VS Code server
# --server-base-path handles NB_PREFIX routing natively (no NGINX rewrite needed)
# --without-connection-token disables auth (Kubeflow handles auth via OAuth proxy)
start_process "${CHECODE_DIR}/node" "${CHECODE_DIR}/out/server-main.js" \
    --host "$HOST" \
    --port 3100 \
    --without-connection-token \
    --server-base-path "${NB_PREFIX:-/}" \
    --server-data-dir "${HOME}/.vscode-server" \
    --extensions-dir "${CHECODE_DIR}/extensions" \
    --default-folder "${HOME}" \
    --telemetry-level off
