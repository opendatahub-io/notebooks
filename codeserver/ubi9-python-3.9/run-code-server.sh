#!/usr/bin/env bash

# Load bash libraries
SCRIPT_DIR=$(dirname -- "$0")
source ${SCRIPT_DIR}/utils/*.sh

# Start nginx and fastcgiwrap
run-nginx.sh &
spawn-fcgi -s /var/run/fcgiwrap.socket -M 766 /usr/sbin/fcgiwrap 

# Add .bashrc for custom promt if not present
if [ ! -f "/opt/app-root/src/.bashrc" ]; then
  echo 'PS1="\[\033[34;1m\][\$(pwd)]\[\033[0m\]\n\[\033[1;0m\]$ \[\033[0m\]"' > /opt/app-root/src/.bashrc
fi

# Initilize access logs for culling
echo '[{"id":"code-server","name":"code-server","last_activity":"'$(date -Iseconds)'","execution_state":"running","connections":1}]' > /var/log/nginx/codeserver.access.log

# Directory for settings file
user_dir="/opt/app-root/src/.local/share/code-server/User/"
settings_filepath="${user_dir}settings.json"

json_settings='{
  "python.defaultInterpreterPath": "/opt/app-root/bin/python3"
}'

# Check if User directory exists
if [ ! -d "$user_dir" ]; then
  echo "Debug: User directory not found, creating '$user_dir'..."
  mkdir -p "$user_dir"
  echo "$json_settings" > "$settings_filepath"
  echo "Debug: '$settings_filepath' file created."
else
  echo "Debug: User directory already exists."
  # Add settings.json if not present
  if [ ! -f "$settings_filepath" ]; then
    echo "Debug: '$settings_filepath' file not found, creating..."
    echo "$json_settings" > "$settings_filepath"
    echo "Debug: '$settings_filepath' file created."
  else
    echo "Debug: '$settings_filepath' file already exists."
  fi
fi

# Start server
start_process /usr/bin/code-server \
  --bind-addr 0.0.0.0:8787 \
  --disable-telemetry \
  --auth none \
  --disable-update-check \
  /opt/app-root/src & code_server_pid=$!

# Function to check if code-server is ready
check_code_server_ready() {
  if code-server --list-extensions > /dev/null 2>&1; then
    echo "code-server is ready."
    # Check if code-server folder exists
    if [ ! -f "/opt/app-root/src/.local/share/code-server" ]; then

        # Check internet connection - this check is for disconnected environments
        if curl -Is http://www.google.com | head -n 1 | grep -q "200 OK"; then
            # Internet connection is available
            echo "Internet connection available. Installing specific extensions."

            # Install specific extensions
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-python.python-2024.2.1.vsix
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-toolsai.jupyter-2023.9.100.vsix
        else
            # No internet connection
            echo "No internet connection. Installing all extensions."

            # Install all extensions
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-python.python-2024.2.1.vsix
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-python.debugpy-2024.2.0@linux-x64.vsix
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-toolsai.jupyter-2023.9.100.vsix
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-toolsai.jupyter-keymap-1.1.2.vsix
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-toolsai.jupyter-renderers-1.0.17.vsix
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-toolsai.vscode-jupyter-cell-tags-0.1.8.vsix
            code-server --install-extension ${SCRIPT_DIR}/utils/ms-toolsai.vscode-jupyter-slideshow-0.1.5.vsix
        fi
    fi
    return 0
  else
    echo "code-server is not ready yet."
    return 1
  fi
}

# Poll code-server until it is ready
until check_code_server_ready; do
  echo "Waiting for code-server to be ready..."
  sleep 5
done

# wait for code-server to finish or exit script
wait $code_server_pid
echo "code-server process has exited."
