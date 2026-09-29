#!/usr/bin/env bash
# Universal entrypoint: one image digest for workbench and pipeline runtime.
#
# Workbench (default): OpenShift AI / notebook controller starts the container
# with no command override → JupyterLab via start-notebook.sh.
#
# Pipeline runtime (production): Elyra/KFP sets command to [sh, -c] which
# *replaces* this ENTRYPOINT in Kubernetes. The bootstrapper is then invoked
# from /opt/app-root/bin/utils/ (or downloaded). See Elyra
# generic_component_definition_template.jinja2 (command: [sh, -c]).
#
# Local / PoC helpers (this script *is* the entrypoint):
#   entrypoint.sh              → JupyterLab
#   entrypoint.sh runtime …    → python utils/bootstrapper.py …
#   WORKBENCH_MODE=runtime     → same as "runtime" first arg
#
# Env that matters for runtime mode (set in Containerfile):
#   ELYRA_INSTALL_PACKAGES=false  — skip reinstalling pre-baked Elyra deps
#
set -Eeuo pipefail

mode="${WORKBENCH_MODE:-}"
if [[ "${1:-}" == "runtime" ]]; then
  mode="runtime"
  shift
elif [[ "${1:-}" == "workbench" ]]; then
  mode="workbench"
  shift
fi

if [[ "${mode}" == "runtime" ]]; then
  exec python /opt/app-root/bin/utils/bootstrapper.py "$@"
fi

exec /opt/app-root/bin/start-notebook.sh "$@"
