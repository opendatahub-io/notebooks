#!/usr/bin/env bash
#
# Apply or remove baseline ImageStreams on a RHOAI cluster.
#
# Baseline images ship in the ODH operator bundle but are excluded from RHOAI.
# This script applies the RHOAI additional overlay that references the published
# quay.io/opendatahub builds via ImageStreams.
#
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly OVERLAY_DIR="${REPO_ROOT}/manifests/rhoai/overlays/additional/baseline"

readonly -a BASELINE_RESOURCES=(
  imagestream/jupyter-baseline-notebook
  imagestream/code-server-baseline-notebook
  imagestream/runtime-baseline
  configmap/notebook-baseline-image-params
  configmap/notebook-baseline-image-commithash
)

APPLICATIONS_NS="${APPLICATIONS_NS:-redhat-ods-applications}"
DASHBOARD_DEPLOY="rhods-dashboard"
DRY_RUN=false
RESTART_DASHBOARD=true

usage() {
  cat <<'EOF'
Apply or remove baseline ImageStreams on a RHOAI cluster.

Baseline images are included in ODH by default; RHOAI users apply them via the
manifests/rhoai/overlays/additional/baseline overlay.

Usage:
  scripts/apply-baseline-imagestreams.sh <command> [options]

Commands:
  apply     Render baseline ImageStreams and apply to the applications namespace
  revert    Delete the baseline resources added by apply
  preview   Print rendered manifests (no cluster changes)

Options:
  --applications-ns NS    Override dashboard namespace (default: redhat-ods-applications)
  --dry-run               Client-side dry-run only (apply/revert)
  --no-restart-dashboard  Skip dashboard rollout after apply/revert
  -h, --help              Show this help
EOF
}

log() { printf '[apply-baseline-imagestreams] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

KUSTOMIZE=()

resolve_kustomize() {
  if [[ -n "${KUSTOMIZE_BIN:-}" ]]; then
    need_cmd "${KUSTOMIZE_BIN}"
    KUSTOMIZE=("${KUSTOMIZE_BIN}" build)
    return
  fi
  if command -v kustomize >/dev/null 2>&1; then
    KUSTOMIZE=(kustomize build)
    return
  fi
  if command -v oc >/dev/null 2>&1 && oc kustomize --help >/dev/null 2>&1; then
    log "Using 'oc kustomize' (standalone kustomize not found)"
    KUSTOMIZE=(oc kustomize)
    return
  fi
  if command -v kubectl >/dev/null 2>&1 && kubectl kustomize --help >/dev/null 2>&1; then
    log "Using 'kubectl kustomize' (standalone kustomize not found)"
    KUSTOMIZE=(kubectl kustomize)
    return
  fi
  die "Required command not found: kustomize (install via 'brew install kustomize', or use oc/kubectl with kustomize)"
}

kustomize_build() {
  # Overlay references manifests/odh/base/ files; allow parent-directory loads.
  if [[ "${KUSTOMIZE[0]}" == "kustomize" ]]; then
    kustomize build --load-restrictor LoadRestrictionsNone "$@"
  else
    "${KUSTOMIZE[@]}" "$@"
  fi
}

parse_args() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 1
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --applications-ns)
        APPLICATIONS_NS="${2:?}"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --no-restart-dashboard)
        RESTART_DASHBOARD=false
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      apply | revert | preview)
        COMMAND="$1"
        shift
        break
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done

  [[ -n "${COMMAND:-}" ]] || die "Missing command (apply, revert, preview)"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --applications-ns)
        APPLICATIONS_NS="${2:?}"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --no-restart-dashboard)
        RESTART_DASHBOARD=false
        shift
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done
}

check_build_prerequisites() {
  resolve_kustomize
  [[ -d "${OVERLAY_DIR}" ]] || die "Overlay directory not found: ${OVERLAY_DIR}"
}

check_cluster_prerequisites() {
  need_cmd oc
  oc whoami >/dev/null 2>&1 || die "Not logged in to OpenShift (oc whoami failed)"
}

cmd_preview() {
  check_build_prerequisites
  log "Previewing baseline ImageStreams from ${OVERLAY_DIR}"
  kustomize_build "${OVERLAY_DIR}"
}

cmd_apply() {
  check_build_prerequisites
  check_cluster_prerequisites
  local rendered
  rendered="$(mktemp)"

  kustomize_build "${OVERLAY_DIR}" > "${rendered}"

  log "Applying baseline ImageStreams to namespace ${APPLICATIONS_NS}"
  if [[ "${DRY_RUN}" == true ]]; then
    oc apply --dry-run=client -n "${APPLICATIONS_NS}" -f "${rendered}"
  else
    oc apply -n "${APPLICATIONS_NS}" -f "${rendered}"
  fi

  if [[ "${DRY_RUN}" == false && "${RESTART_DASHBOARD}" == true ]]; then
    if oc get deploy "${DASHBOARD_DEPLOY}" -n "${APPLICATIONS_NS}" >/dev/null 2>&1; then
      log "Restarting ${DASHBOARD_DEPLOY}"
      oc rollout restart "deploy/${DASHBOARD_DEPLOY}" -n "${APPLICATIONS_NS}"
    else
      log "Dashboard deployment ${DASHBOARD_DEPLOY} not found; skipping restart"
    fi
  fi

  log "Done. Revert with: ${SCRIPT_DIR}/$(basename "$0") revert"
  rm -f -- "${rendered}"
}

cmd_revert() {
  check_cluster_prerequisites
  local resource
  for resource in "${BASELINE_RESOURCES[@]}"; do
    if oc get "${resource}" -n "${APPLICATIONS_NS}" >/dev/null 2>&1; then
      log "Deleting ${APPLICATIONS_NS}/${resource}"
      if [[ "${DRY_RUN}" == true ]]; then
        log "[dry-run] Would delete ${resource} -n ${APPLICATIONS_NS}"
      else
        oc delete "${resource}" -n "${APPLICATIONS_NS}"
      fi
    else
      log "Resource ${APPLICATIONS_NS}/${resource} not found; skipping"
    fi
  done

  if [[ "${DRY_RUN}" == false && "${RESTART_DASHBOARD}" == true ]]; then
    if oc get deploy "${DASHBOARD_DEPLOY}" -n "${APPLICATIONS_NS}" >/dev/null 2>&1; then
      log "Restarting ${DASHBOARD_DEPLOY}"
      oc rollout restart "deploy/${DASHBOARD_DEPLOY}" -n "${APPLICATIONS_NS}"
    fi
  fi

  log "Revert complete"
}

main() {
  parse_args "$@"
  case "${COMMAND}" in
    preview) cmd_preview ;;
    apply) cmd_apply ;;
    revert) cmd_revert ;;
  esac
}

main "$@"
