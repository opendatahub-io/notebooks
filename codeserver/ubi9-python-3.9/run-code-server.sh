#!/usr/bin/env bash

# Load bash libraries
SCRIPT_DIR=$(dirname -- "$0")
source ${SCRIPT_DIR}/utils/*.sh

# Start nginx and supervisord
run-nginx.sh &
/usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf &

# Add .bashrc for custom promt if not present
if [ ! -f "/opt/app-root/src/.bashrc" ]; then
  echo 'PS1="\[\033[34;1m\][\$(pwd)]\[\033[0m\]\n\[\033[1;0m\]$ \[\033[0m\]"' > /opt/app-root/src/.bashrc
fi

# Initilize access logs for culling
echo '[{"id":"code-server","name":"code-server","last_activity":"'$(date -Iseconds)'","execution_state":"running","connections":1}]' > /var/log/nginx/codeserver.access.log

# Add "/opt/app-root/src/.vscode/" directory to set default interpreter also for Run & Debug
user_dir="/opt/app-root/src/.vscode/"
settings_filepath="${user_dir}settings.json"
launch_filepath="${user_dir}launch.json"

json_launch_settings='{
    // Use IntelliSense to learn about possible attributes.
    // Hover to view descriptions of existing attributes.
    // For more information, visit: https://go.microsoft.com/fwlink/?linkid=830387
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
  "python.defaultInterpreterPath": "/opt/app-root/bin/python3"
  }'

# Check if User directory exists
if [ ! -d "$user_dir" ]; then
  echo "Debug: User directory not found, creating '$user_dir'..."
  mkdir -p "$user_dir"
  echo "$json_launch_settings" > "$launch_filepath"
  echo "Debug: '$launch_filepath' file created."
  echo "$json_settings" > "$settings_filepath"
  echo "Debug: '$settings_filepath' file created."
else
  echo "Debug: User directory already exists."
  # Add settings.json and launch.json if not present
  if [ ! -f "$launch_filepath" ]; then
    echo "Debug: '$launch_filepath' file not found, creating..."
    echo "$json_launch_settings" > "$launch_filepath"
    echo "Debug: '$launch_filepath' file created."
  elif [ ! -f "$settings_filepath" ]; then
    echo "Debug: '$settings_filepath' file not found, creating..."
    echo "$json_settings" > "$settings_filepath"
    echo "Debug: '$settings_filepath' file created."
  else
    echo "Debug: '$launch_filepath' file already exists."
    echo "Debug: '$settings_filepath' file already exists."

  fi
fi

# Ensure the extensions directory exists
extensions_dir="/opt/app-root/src/.local/share/code-server/extensions"
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
logs_dir="/opt/app-root/src/.local/share/code-server/coder-logs"
if [ ! -d "$logs_dir" ]; then
  echo "Debug: Log directory not found, creating '$logs_dir'..."
  mkdir -p "$logs_dir"
fi

# Start server
start_process /usr/bin/code-server \
  --bind-addr 0.0.0.0:8787 \
  --disable-telemetry \
  --auth none \
  --disable-update-check \
  /opt/app-root/src
