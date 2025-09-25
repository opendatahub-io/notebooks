#!/usr/bin/env bash

# Load bash libraries
SCRIPT_DIR=$(dirname -- "$0")
source ${SCRIPT_DIR}/utils/*.sh

# Start nginx and httpd
run-nginx.sh &

# Start Apache httpd with error checking
echo "Starting Apache httpd..."
/usr/sbin/httpd -D FOREGROUND &
HTTPD_PID=$!
sleep 2

# Check if Apache started successfully
if ! kill -0 $HTTPD_PID 2>/dev/null; then
    echo "ERROR: Apache httpd failed to start"
    echo "Checking Apache configuration..."
    /usr/sbin/httpd -t
    exit 1
else
    echo "Apache httpd started successfully (PID: $HTTPD_PID)"
fi


# Add .bashrc for custom promt if not present
if [ ! -f "/opt/app-root/src/.bashrc" ]; then
  echo 'PS1="\[\033[34;1m\][\$(pwd)]\[\033[0m\]\n\[\033[1;0m\]$ \[\033[0m\]"' > /opt/app-root/src/.bashrc
fi

# Create lib folders if it does not exist
mkdir -p  /opt/app-root/src/Rpackages/4.5
for package in /opt/app-root/bin/Rpackages/4.5/*/;
do
  package_folder=$(basename "$package")
  if [ ! -d "/opt/app-root/src/Rpackages/4.5/$package_folder" ]; then
    cp -r /opt/app-root/bin/Rpackages/4.5/$package_folder /opt/app-root/src/Rpackages/4.5/
  fi
done
# rstudio terminal can't see environment variables set by the container runtime;
# so we set all env variables to the Renviron.site config file. For kubectl, we need the KUBERNETES_* env vars at least.
# Also, we store proxy-related env vars lowercased by key so RStudio projects work with proxy by default
env >> /usr/lib64/R/etc/Renviron.site
env | grep "^HTTP_PROXY=" | tr '[:upper:]' '[:lower:]' >> /usr/lib64/R/etc/Renviron.site
env | grep "^HTTPS_PROXY=" | tr '[:upper:]' '[:lower:]' >> /usr/lib64/R/etc/Renviron.site
env | grep "^NO_PROXY=" | tr '[:upper:]' '[:lower:]' >> /usr/lib64/R/etc/Renviron.site

export USER=$(whoami)

# Initilize access logs for culling
echo '[{"id":"rstudio","name":"rstudio","last_activity":"'$(date -Iseconds)'","execution_state":"running","connections":1}]' > /var/log/nginx/rstudio.access.log

# Create RStudio launch command
launch_command=$(python /opt/app-root/bin/setup_rstudio.py)

echo $launch_command

start_process $launch_command
