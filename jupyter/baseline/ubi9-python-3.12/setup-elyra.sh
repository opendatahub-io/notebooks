#!/bin/bash
set -x

# Set the elyra config on the right path
# RHOAIENG-15626: Always copy our custom config to ensure it's up to date (install -D creates directory if needed)
install -D -m 0644 /opt/app-root/bin/utils/jupyter_elyra_config.py /opt/app-root/src/.jupyter/jupyter_elyra_config.py
chmod 2770 /opt/app-root/src/.jupyter/ 2>/dev/null || true  # Fix directory perms if created

# create the elyra runtime directory if not present
if [ ! -d $(jupyter --data-dir)/metadata/runtimes/ ]; then
  mkdir -p $(jupyter --data-dir)/metadata/runtimes/
fi
# Set elyra runtime config from volume mount
if [ "$(ls -A /opt/app-root/runtimes/)" ]; then
  cp -r /opt/app-root/runtimes/..data/*.json $(jupyter --data-dir)/metadata/runtimes/
fi

# Set elyra runtime images json from volume mount
if [ "$(ls -A /opt/app-root/pipeline-runtimes/)" ]; then
  cp -r /opt/app-root/pipeline-runtimes/..data/*.json /opt/app-root/share/jupyter/metadata/runtime-images/
fi

# Environment vars set for accessing ssl_sa_certs and sa_token
# export PIPELINES_SSL_SA_CERTS="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
export KF_PIPELINES_SA_TOKEN_ENV="/var/run/secrets/kubernetes.io/serviceaccount/token"
export KF_PIPELINES_SA_TOKEN_PATH="/var/run/secrets/kubernetes.io/serviceaccount/token"
