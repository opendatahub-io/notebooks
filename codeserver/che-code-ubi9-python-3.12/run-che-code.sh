#!/bin/bash
set -euo pipefail

# Source utility scripts
for f in /opt/app-root/bin/utils/*.sh; do source "$f"; done

# Start NGINX on port 8888 (proxies to che-code on 3100)
/opt/app-root/bin/run-nginx.sh &
NGINX_PID=$!
python3 /opt/app-root/bin/culler-server.py &
CULLER_PID=$!

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
  "security.workspace.trust.enabled": false,
  "security.workspace.trust.startupPrompt": "never"
}
SETTINGS_EOF
fi

# Set DevWorkspace env vars so che-api/che-github-authentication can initialize.
# Without these, K8sHelper.getDevWorkspaceNamespace() throws and the Device Code Flow
# command never gets registered. The K8s API calls fail gracefully (no in-cluster config).
export DEVWORKSPACE_ID="${DEVWORKSPACE_ID:-kubeflow}"
export DEVWORKSPACE_NAMESPACE="${DEVWORKSPACE_NAMESPACE:-default}"
export DEVWORKSPACE_NAME="${DEVWORKSPACE_NAME:-workbench}"
export DEVWORKSPACE_POD_NAME="${DEVWORKSPACE_POD_NAME:-${HOSTNAME}}"
export DEVWORKSPACE_FLATTENED_DEVFILE="${DEVWORKSPACE_FLATTENED_DEVFILE:-/dev/null}"
export PROJECTS_ROOT="${PROJECTS_ROOT:-${HOME}}"

# Set LD_LIBRARY_PATH for bundled native libs (libnode, libbrotli, libz, libssl, libcrypto)
CHECODE_DIR=/opt/app-root/checode
if [[ -d "${CHECODE_DIR}/ld_libs/core" ]]; then
    export LD_LIBRARY_PATH="${CHECODE_DIR}/ld_libs/core${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
if [[ -d "${CHECODE_DIR}/ld_libs/openssl" ]]; then
    export LD_LIBRARY_PATH="${CHECODE_DIR}/ld_libs/openssl${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

# Che Code has no connection token; keep its upstream reachable only through NGINX.
HOST="127.0.0.1"

# Launch che-code VS Code server
# --server-base-path handles NB_PREFIX routing natively (no NGINX rewrite needed)
# --without-connection-token disables auth (Kubeflow handles auth via OAuth proxy)
"${CHECODE_DIR}/node" "${CHECODE_DIR}/out/server-main.js" \
    --host "$HOST" \
    --port 3100 \
    --without-connection-token \
    --server-base-path "${NB_PREFIX:-/}" \
    --server-data-dir "${HOME}/.vscode-server" \
    --extensions-dir "${CHECODE_DIR}/extensions" \
    --default-folder "${HOME}" \
    --telemetry-level off &
CHECODE_PID=$!

cleanup() {
    status=$?
    trap - EXIT TERM INT
    kill -TERM "$NGINX_PID" "$CULLER_PID" "$CHECODE_PID" 2>/dev/null || true
    wait "$NGINX_PID" "$CULLER_PID" "$CHECODE_PID" 2>/dev/null || true
    exit "$status"
}

trap cleanup EXIT TERM INT
wait -n "$NGINX_PID" "$CULLER_PID" "$CHECODE_PID"
