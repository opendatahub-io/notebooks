#!/usr/bin/env bash
# Universal entrypoint: one image digest for workbench and pipeline runtime.
#
# Workbench (default): OpenShift AI starts with no extra args → JupyterLab.
# Pipeline runtime:    first arg "runtime" → Elyra bootstrapper.
#
set -Eeuo pipefail

if [[ "${1:-}" == "runtime" ]]; then
  shift
  exec python /opt/app-root/bin/utils/bootstrapper.py "$@"
fi

exec /opt/app-root/bin/start-notebook.sh "$@"
