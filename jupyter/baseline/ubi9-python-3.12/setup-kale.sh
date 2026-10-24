#!/bin/bash
# Sourced by start-notebook.sh — do not use `set -u` here (nounset leaks into the
# parent shell and breaks optional NOTEBOOK_* env vars). Match datascience: set -x only.
__SETUP_KALE_SHELL_OPTS="$(set +o)"
set -Eeuxo pipefail

# Runtime configuration for Kubeflow Kale JupyterLab extension
# This script configures Kale to connect to KFP by reading Elyra runtime config
# Note: The extension is disabled by default at build time (see Dockerfile)

# Read Elyra config and copy the relevant information to Kale config
# Prefer the default "Pipeline" runtime configuration created by the operator,
# otherwise fall back to the first available runtime config.
ELYRA_RUNTIME_CONFIG="/opt/app-root/runtimes/..data/Pipeline.json"
if [ ! -f "$ELYRA_RUNTIME_CONFIG" ]; then
  shopt -s nullglob
  RUNTIME_CONFIGS=(/opt/app-root/runtimes/..data/*.json)
  shopt -u nullglob
  if [ ${#RUNTIME_CONFIGS[@]} -gt 0 ]; then
    ELYRA_RUNTIME_CONFIG="${RUNTIME_CONFIGS[0]}"
  fi
fi

if [ -f "$ELYRA_RUNTIME_CONFIG" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  export ELYRA_RUNTIME_CONFIG
  python3 "${SCRIPT_DIR}/configure_kale_from_elyra.py"
fi

# Set environment variables for KFP authentication
export KF_PIPELINES_SA_TOKEN_PATH="/var/run/secrets/kubernetes.io/serviceaccount/token"
export KF_PIPELINES_SSL_SA_CERTS="${KF_PIPELINES_SSL_SA_CERTS:-/var/run/secrets/kubernetes.io/serviceaccount/ca.crt}"

# Configure Kale security context settings
# Disable security context enforcement (leave RUN_AS_USER and RUN_AS_GROUP undefined)
export KALE_SECURITY_CONTEXT_ENABLED=false

# Set default image
export KALE_DEFAULT_BASE_IMAGE=ubi9/python-312

# Set the default pipeline output directory to _kale/ (instead of the default .kale/)
# Written as a JupyterLab user-settings file so the extension picks it up on startup.
KALE_SETTINGS_DIR="${HOME}/.jupyter/lab/user-settings/jupyterlab-kubeflow-kale"
mkdir -p "${KALE_SETTINGS_DIR}"
if [ ! -f "${KALE_SETTINGS_DIR}/kale-settings.jupyterlab-settings" ]; then
    echo '{"outputPath": "_kale"}' > "${KALE_SETTINGS_DIR}/kale-settings.jupyterlab-settings"
fi

eval "$__SETUP_KALE_SHELL_OPTS"
unset __SETUP_KALE_SHELL_OPTS
