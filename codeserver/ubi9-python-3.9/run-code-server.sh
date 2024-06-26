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

# Define universal settings
universal_dir="/opt/app-root/src/.local/share/code-server/User/"
user_settings_filepath="${universal_dir}settings.json"
universal_json_settings='{
  "python.defaultInterpreterPath": "/opt/app-root/bin/python3",
  "telemetry.telemetryLevel": "off",
  "telemetry.enableTelemetry": false,
  "workbench.enableExperiments": false
}'

# Define python debuger settings
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
  "python.defaultInterpreterPath": "/opt/app-root/bin/python3"
}'

# Create necessary directories and files for python debuger and universal settings
create_dir_and_file "$universal_dir" "$user_settings_filepath" "$universal_json_settings"
create_dir_and_file "$vscode_dir" "$settings_filepath" "$json_settings"
create_dir_and_file "$vscode_dir" "$launch_filepath" "$json_launch_settings"

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
