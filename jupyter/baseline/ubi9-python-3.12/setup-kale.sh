#!/bin/bash
# Sourced by start-notebook.sh. Nounset and errexit stay off: nounset exits this
# shell on an unset expansion, and errexit exits it when configure_kale_from_elyra.py
# returns 1 after an intentional DEX skip (see setup-elyra.sh). xtrace is restored
# so sourcing this file does not change the caller's trace setting.

__kale_had_xtrace=0
if [ -o xtrace ]; then
  __kale_had_xtrace=1
fi
set -x

# Runtime configuration for Kubeflow Kale JupyterLab extension
# This script configures Kale to connect to KFP by reading Elyra runtime config
# Note: The extension is disabled by default at build time (see Dockerfile)

# Prefer the default "Pipeline" runtime configuration created by the operator,
# otherwise fall back to the first available runtime config.
# The glob runs in a subshell so enabling nullglob cannot change the caller.
_KALE_RUNTIME_DIR="/opt/app-root/runtimes/..data"
ELYRA_RUNTIME_CONFIG="${_KALE_RUNTIME_DIR}/Pipeline.json"
if [ ! -f "$ELYRA_RUNTIME_CONFIG" ]; then
  ELYRA_RUNTIME_CONFIG="$(
    shopt -s nullglob
    configs=("${_KALE_RUNTIME_DIR}"/*.json)
    if [ "${#configs[@]}" -gt 0 ]; then
      printf '%s' "${configs[0]}"
    fi
  )"
fi
unset _KALE_RUNTIME_DIR

if [ -f "$ELYRA_RUNTIME_CONFIG" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  export ELYRA_RUNTIME_CONFIG
  # Non-zero is expected for an intentional DEX skip; keep going so Jupyter still starts.
  python3 "${SCRIPT_DIR}/configure_kale_from_elyra.py" || true
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

if [ "$__kale_had_xtrace" -eq 1 ]; then
  set -o xtrace
else
  set +o xtrace
fi
unset __kale_had_xtrace
