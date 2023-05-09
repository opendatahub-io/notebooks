#!/bin/bash
set -x

# Set the elyra config on the right path
cp /opt/app-root/bin/utils/jupyter_elyra_config.py /opt/app-root/src/.jupyter/

# Set runtime config from volume mount
if [ "$(ls -A /opt/app-root/runtimes/)" ]; then
  cp -r /opt/app-root/runtimes/..data/*.json $(jupyter --data-dir)/metadata/runtimes/
fi

# Environment vars set for accessing ssl_sa_certs and sa_token
export KF_PIPELINES_SSL_SA_CERTS="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
export KF_PIPELINES_SA_TOKEN_ENV="/var/run/secrets/kubernetes.io/serviceaccount/token"
