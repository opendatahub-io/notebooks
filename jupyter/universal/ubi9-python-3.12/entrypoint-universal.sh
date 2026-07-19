#!/usr/bin/env bash
set -euo pipefail

# Dual-mode entrypoint following the distributed-workloads universal image pattern
# (opendatahub-io/distributed-workloads, ADR #0013)
#
# Workbench mode: NOTEBOOK_ARGS is set by the workbench controller → start JupyterLab
# Runtime mode:   training controller overrides the command → this script is bypassed

if [ -n "${NOTEBOOK_ARGS:-}" ]; then
    exec sh -lc 'exec start-notebook.sh ${NOTEBOOK_ARGS}'
fi

exec "${@:-start-notebook.sh}"
