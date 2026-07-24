#!/usr/bin/env bash
set -euo pipefail

# Dual-mode entrypoint following the distributed-workloads universal image pattern
# (opendatahub-io/distributed-workloads, ADR #0013)
#
# Workbench mode: NOTEBOOK_ARGS is set by the workbench controller → start JupyterLab
# Runtime mode:   Elyra/AI Pipelines step overrides the command to run bootstrapper.py

if [ -n "${NOTEBOOK_ARGS:-}" ]; then
    exec sh -lc 'exec start-notebook.sh'
fi

exec "${@:-start-notebook.sh}"
