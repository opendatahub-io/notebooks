#!/bin/bash
# Sourced by start-notebook.sh — do not use `set -u` here (nounset leaks into the
# parent shell and breaks optional NOTEBOOK_* env vars). Match datascience: set -x only.
set -x

# Runtime configuration for Kubeflow Kale JupyterLab extension
# This script configures Kale to connect to KFP by reading Elyra runtime config

# Read Elyra config and copy the relevant information to Kale config
# Extract KFP configuration from Elyra runtime configs if available
if [ "$(ls -A /opt/app-root/runtimes/ 2>/dev/null)" ]; then
  # Use the default "Pipeline" runtime configuration created by the operator
  ELYRA_RUNTIME_CONFIG="/opt/app-root/runtimes/..data/Pipeline.json"

  # Fallback to first available runtime config if default doesn't exist
  if [ ! -f "$ELYRA_RUNTIME_CONFIG" ]; then
    shopt -s nullglob
    RUNTIME_CONFIGS=(/opt/app-root/runtimes/..data/*.json)
    if [ ${#RUNTIME_CONFIGS[@]} -gt 0 ]; then
      ELYRA_RUNTIME_CONFIG="${RUNTIME_CONFIGS[0]}"
    else
      ELYRA_RUNTIME_CONFIG=""
    fi
    shopt -u nullglob
  fi

  if [ -n "$ELYRA_RUNTIME_CONFIG" ] && [ -f "$ELYRA_RUNTIME_CONFIG" ]; then
    # Configure Kale KFP server connection by mapping Elyra config to Kale config
    # Note: The Python script sets KF_PIPELINES_TOKEN directly in the environment
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    export ELYRA_RUNTIME_CONFIG
    python3 "${SCRIPT_DIR}/configure_kale_from_elyra.py"
  fi
fi

# Set environment variables for KFP authentication
export KF_PIPELINES_SA_TOKEN_PATH="/var/run/secrets/kubernetes.io/serviceaccount/token"
export KF_PIPELINES_SSL_SA_CERTS="${KF_PIPELINES_SSL_SA_CERTS:-/var/run/secrets/kubernetes.io/serviceaccount/ca.crt}"

# Configure Kale security context settings
# Disable security context enforcement (leave RUN_AS_USER and RUN_AS_GROUP undefined)
export KALE_SECURITY_CONTEXT_ENABLED=false

# Set default image
export KALE_DEFAULT_BASE_IMAGE=ubi9/python-312

# Set the default pipeline output directory to _kale/ (instead of the default .kale/
# since users can't see hidden files on notebooks)
# Written as a JupyterLab user-settings file so Kale picks it up on startup.
KALE_SETTINGS_DIR="${HOME}/.jupyter/lab/user-settings/jupyterlab-kubeflow-kale"
mkdir -p "${KALE_SETTINGS_DIR}"
if [ ! -f "${KALE_SETTINGS_DIR}/kale-settings.jupyterlab-settings" ]; then
    echo '{"outputPath": "_kale"}' > "${KALE_SETTINGS_DIR}/kale-settings.jupyterlab-settings"
fi
