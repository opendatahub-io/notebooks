#!/usr/bin/env bash
# Dual-mode entrypoint: one image digest for workbench and pipeline runtime.
#
# Workbench mode: NOTEBOOK_ARGS is set by the notebook/workbench controller → JupyterLab
# Runtime mode:   Elyra/AI Pipelines overrides the command (typically bootstrapper.py),
#                 or the first arg is "runtime" (custom-workbenches convention).
#
# Pattern from opendatahub-io/notebooks#4110 and distributed-workloads ADR #0013;
# "runtime" shortcut matches custom-workbenches/src/bin/entrypoint.sh.
set -euo pipefail

START_NOTEBOOK=/opt/app-root/bin/start-notebook.sh
BOOTSTRAPPER=/opt/app-root/bin/utils/bootstrapper.py

if [[ "${1:-}" == "runtime" ]]; then
    shift
    exec python "${BOOTSTRAPPER}" "$@"
fi

if [ -n "${NOTEBOOK_ARGS:-}" ]; then
    exec "${START_NOTEBOOK}"
fi

if [ "$#" -eq 0 ]; then
    exec "${START_NOTEBOOK}"
fi

exec "$@"
