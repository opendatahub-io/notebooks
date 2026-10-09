#!/bin/bash
set -x

# Don't leak errexit and nounset:
#  when a runtime uses a supported DEX authentication type, configure_kale_from_elyra.py
#  returns status 1 after intentionally skipping Kale configuration. If setup-elyra.sh
#  were to enable errexit, the later sourced setup-kale.sh would exit the parent startup
#  shell at that command. With the next line commented out, setup-kale.sh continues and Jupyter starts.
# set -Eeuxo pipefail

# Set the elyra config on the right path
# RHOAIENG-15626: Always copy our custom config to ensure it's up to date (install -D creates directory if needed)
install -D -m 0644 /opt/app-root/bin/utils/jupyter_elyra_config.py /opt/app-root/src/.jupyter/jupyter_elyra_config.py
chmod 2770 /opt/app-root/src/.jupyter/ 2>/dev/null || true  # Fix directory perms if created

# create the elyra runtime directory if not present
if [ ! -d "$(jupyter --data-dir)/metadata/runtimes/" ]; then
  mkdir -p "$(jupyter --data-dir)/metadata/runtimes/"
fi
# Set elyra runtime config from volume mount
if [ "$(ls -A /opt/app-root/runtimes/)" ]; then
  cp -r /opt/app-root/runtimes/..data/*.json "$(jupyter --data-dir)/metadata/runtimes/"
fi

# Set elyra runtime images json from volume mount
if [ "$(ls -A /opt/app-root/pipeline-runtimes/)" ]; then
  cp -r /opt/app-root/pipeline-runtimes/..data/*.json /opt/app-root/share/jupyter/metadata/runtime-images/
fi

# Environment vars set for accessing ssl_sa_certs and sa_token

# https://redhat-internal.slack.com/archives/C08KP11G5KL/p1781270556595619?thread_ts=1781200460.945909&cid=C08KP11G5KL
# export PIPELINES_SSL_SA_CERTS="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
export KF_PIPELINES_SA_TOKEN_ENV="/var/run/secrets/kubernetes.io/serviceaccount/token"
export KF_PIPELINES_SA_TOKEN_PATH="/var/run/secrets/kubernetes.io/serviceaccount/token"
# https://github.com/elyra-ai/elyra/pull/3328
export ELYRA_INSTALL_PACKAGES="false"
# https://issues.redhat.com/browse/RHOAIENG-6780
export ELYRA_GENERIC_NODES_ENABLE_SCRIPT_OUTPUT_TO_S3="false"
