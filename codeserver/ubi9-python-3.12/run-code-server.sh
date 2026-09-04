#!/usr/bin/env bash

# Load bash libraries
# [IMPROVEMENT] Changed from `source ${SCRIPT_DIR}/utils/*.sh` (single glob) to a for-loop.
# The glob expansion is more robust: handles missing files and avoids issues with spaces in paths.
SCRIPT_DIR=$(dirname -- "$0")
for f in "${SCRIPT_DIR}"/utils/*.sh; do
  # shellcheck source=/dev/null
  [[ -f "$f" ]] && source "$f"
done

# Start nginx and httpd
run-nginx.sh &
/usr/sbin/httpd -D FOREGROUND &

# Add .bashrc for custom prompt and BYO Copilot hint if not present
if [ ! -f "/opt/app-root/src/.bashrc" ]; then
  cat > /opt/app-root/src/.bashrc <<'EOF'
PS1="\[\033[34;1m\][\$(pwd)]\[\033[0m\]\n\[\033[1;0m\]$ \[\033[0m\]"
# Shown when opening a terminal until install-byo-copilot.sh has been run.
if [ ! -f "${HOME}/.local/share/code-server/byo-copilot/gallery.env" ]; then
  echo ""
  echo "  GitHub Copilot is not included in this workbench image."
  echo "  To enable it with your own subscription, run:  install-byo-copilot.sh"
  echo "  Then restart the workbench and sign in to GitHub."
  echo "  See README.md in this folder for details."
  echo ""
fi
EOF
fi

# Initialize access logs for culling
echo '[{"id":"code-server","name":"code-server","last_activity":"'$(date -Iseconds)'","execution_state":"running","connections":1}]' > /var/log/nginx/codeserver.access.log

# Function to create directories and files if they do not exist
create_dir_and_file() {
  local dir=$1
  local filepath=$2
  local content=$3

  if [ ! -d "$dir" ]; then
    echo "Debug: Directory not found, creating '$dir'..."
    mkdir -p "$dir"
    echo "$content" > "$filepath"
    echo "Debug: '$filepath' file created."
  else
    echo "Debug: Directory already exists."
    if [ ! -f "$filepath" ]; then
      echo "Debug: '$filepath' file not found, creating..."
      echo "$content" > "$filepath"
      echo "Debug: '$filepath' file created."
    else
      echo "Debug: '$filepath' file already exists."
    fi
  fi
}

CODE_SERVER_DATA_DIR="/opt/app-root/src/.local/share/code-server"

# Define universal settings
universal_dir="${CODE_SERVER_DATA_DIR}/User/"
user_settings_filepath="${universal_dir}settings.json"
universal_json_settings='// vscode settings are written in json-with-comments
/* https://code.visualstudio.com/docs/languages/json#_json-with-comments */
{
  "python.defaultInterpreterPath": "/opt/app-root/bin/python3",
  "telemetry.telemetryLevel": "off",
  "telemetry.enableTelemetry": false,
  "workbench.enableExperiments": false,
  "extensions.autoCheckUpdates": false,
  "extensions.autoUpdate": false,

  // Open workspace README on startup (includes optional BYO Copilot instructions).
  "workbench.startupEditor": "readme",
  "workbench.editorAssociations": {
    "README.md": "vscode.markdown.preview.editor"
  },

  // AI features off by default; users opt in via install-byo-copilot.sh (BYO license).
  // https://code.visualstudio.com/docs/copilot/faq#_how-can-i-remove-copilot-from-vs-code
  "chat.disableAIFeatures": true,
  "github-authentication.preferDeviceCodeFlow": true,

  // RHOAIENG-14518: Disable the "Do you trust the authors [...]" startup prompt
  "security.workspace.trust.enabled": false,
  "security.workspace.trust.startupPrompt": "never"
}'

# Define python debugger settings
vscode_dir="/opt/app-root/src/.vscode/"
settings_filepath="${vscode_dir}settings.json"
launch_filepath="${vscode_dir}launch.json"
json_launch_settings='{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python Debugger: Current File",
      "type": "debugpy",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "python": "/opt/app-root/bin/python3"
    }
  ]
}'
json_settings='{
  "python.defaultInterpreterPath": "/opt/app-root/bin/python3",
  "workbench.editorAssociations": {
    "README.md": "vscode.markdown.preview.editor"
  }
}'

# Create necessary directories and files for python debugger and universal settings
create_dir_and_file "$universal_dir" "$user_settings_filepath" "$universal_json_settings"
create_dir_and_file "$vscode_dir" "$settings_filepath" "$json_settings"
create_dir_and_file "$vscode_dir" "$launch_filepath" "$json_launch_settings"

workspace_readme="/opt/app-root/src/README.md"
workspace_readme_src="${SCRIPT_DIR}/workspace-readme.md"
if [ ! -f "$workspace_readme" ]; then
  if [ -f "$workspace_readme_src" ]; then
    cp "$workspace_readme_src" "$workspace_readme"
    echo "Debug: '$workspace_readme' seeded from '$workspace_readme_src'."
  else
    echo "Warning: workspace readme source not found at '$workspace_readme_src'."
  fi
else
  echo "Debug: '$workspace_readme' already exists."
fi

# Symlink BYO installer into workspace so `ls` shows it (binary lives in /opt/app-root/bin).
byo_link="/opt/app-root/src/install-byo-copilot.sh"
if [ ! -e "$byo_link" ] && [ -x "/opt/app-root/bin/install-byo-copilot.sh" ]; then
  ln -s /opt/app-root/bin/install-byo-copilot.sh "$byo_link"
fi

# Ensure the extensions directory exists
extensions_dir="${CODE_SERVER_DATA_DIR}/extensions"
mkdir -p "$extensions_dir"

# Copy installed extensions to the runtime extensions directory if they do not already exist
if [ -d "/opt/app-root/extensions-temp" ]; then
  for extension in /opt/app-root/extensions-temp/*/;
  do
    extension_folder=$(basename "$extension")
    if [ ! -d "$extensions_dir/$extension_folder" ]; then
      cp -r "$extension" "$extensions_dir"
      echo "Debug: Extension '$extension_folder' copied to runtime directory."
    else
      echo "Debug: Extension '$extension_folder' already exists in runtime directory, skipping."
    fi
  done
else
  echo "Debug: Temporary extensions directory not found."
fi

# Ensure log directory exists
logs_dir="${CODE_SERVER_DATA_DIR}/coder-logs"
if [ ! -d "$logs_dir" ]; then
  echo "Debug: Log directory not found, creating '$logs_dir'..."
  mkdir -p "$logs_dir"
fi

# IPv6 support (skip when IPv6 is disabled, e.g. via container sysctls in CI)
echo "Checking IPv6 support..."
if [ -f /proc/net/if_inet6 ] && [ "$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6 2>/dev/null)" != "1" ]; then
    BIND_ADDR="[::]:8787"  # IPv6/dual-stack
    echo "IPv6 detected: binding to all interfaces (IPv4 + IPv6)"
else
    BIND_ADDR="0.0.0.0:8787"  # IPv4 only
    echo "IPv6 not available: falling back to IPv4 only"
fi

# Start server with explicit --user-data-dir so code-server writes settings,
# extensions, and logs under /opt/app-root/src/ (writable by UID 1001).
BYO_COPILOT_GALLERY="${CODE_SERVER_DATA_DIR}/byo-copilot/gallery.env"
if [[ -f "${BYO_COPILOT_GALLERY}" ]]; then
  # shellcheck source=/dev/null
  source "${BYO_COPILOT_GALLERY}"
  echo "Debug: loaded BYO Copilot gallery config from ${BYO_COPILOT_GALLERY}"
else
  echo "NOTE: GitHub Copilot is not enabled. Users with their own subscription can run:"
  echo "      install-byo-copilot.sh   (see /opt/app-root/src/README.md)"
fi

start_process /usr/bin/code-server \
    --bind-addr "${BIND_ADDR}" \
    --user-data-dir "${CODE_SERVER_DATA_DIR}" \
    --extensions-dir "${CODE_SERVER_DATA_DIR}/extensions" \
    --disable-telemetry \
    --auth none \
    --disable-update-check \
    --disable-getting-started-override \
    /opt/app-root/src
