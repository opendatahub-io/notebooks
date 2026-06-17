#!/bin/bash
set -Eeuxo pipefail

# Runtime configuration for Kubeflow Kale JupyterLab extension
# This script configures Kale to connect to KFP by reading Elyra runtime config
# Note: The extension is disabled by default at build time (see Dockerfile)

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
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    export ELYRA_RUNTIME_CONFIG
    python3 "${SCRIPT_DIR}/configure_kale_from_elyra.py"

    # Source environment variable exports from Python script
    KALE_ENV_EXPORTS="${KALE_ENV_EXPORTS:-/tmp/kale-env-exports.sh}"
    if [[ -f "${KALE_ENV_EXPORTS}" ]]; then
      # shellcheck source=/dev/null
      source "${KALE_ENV_EXPORTS}"
      rm -f "${KALE_ENV_EXPORTS}"
    fi
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
