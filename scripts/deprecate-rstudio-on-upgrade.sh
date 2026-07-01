#!/usr/bin/env bash
# Deprecate and remove leftover RStudio workbench resources after upgrading
# from RHOAI 3.4 to 3.5 (or ODH equivalent). RStudio was removed from the
# notebooks main branch in RHAIENG-4776; upgraded clusters can retain orphaned
# BuildConfigs and ImageStreams from the previous release.
#
# See docs/rstudio-deprecation-upgrade.md for usage and background.

set -euo pipefail

readonly SCRIPT_NAME="${0##*/}"

# BuildConfigs shipped in RHOAI 3.4 manifests/rhoai/base/*-rstudio-buildconfig.yaml
readonly RSTUDIO_BUILDCONFIGS=(
  rstudio-server-rhel9
  cuda-rstudio-server-rhel9
)

# Internal ImageStreams created alongside those BuildConfigs.
readonly RSTUDIO_BUILD_IMAGESTREAMS=(
  rstudio-rhel9
  cuda-rstudio-rhel9
)

# Workbench ImageStreams shown in the spawner UI (RHOAI 3.4 shipped GPU only;
# CPU imagestream existed in ODH manifests and may be present on some clusters).
readonly RSTUDIO_NOTEBOOK_IMAGESTREAMS=(
  rstudio-notebook
  rstudio-gpu-notebook
)

NAMESPACE=""
DRY_RUN=false

log() {
  printf '[%s] %s\n' "${SCRIPT_NAME}" "$*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [OPTIONS]

Remove orphaned RStudio BuildConfigs and mark any remaining RStudio workbench
ImageStreams as deprecated after upgrading to RHOAI 3.5.

Options:
  -n, --namespace NAME   Target namespace (default: auto-detect)
  --dry-run              Print actions without modifying the cluster
  -h, --help             Show this help message

Examples:
  ${SCRIPT_NAME}
  ${SCRIPT_NAME} -n redhat-ods-applications
  ${SCRIPT_NAME} --dry-run
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

detect_namespace() {
  local candidate
  for candidate in redhat-ods-applications opendatahub; do
    if oc get namespace "${candidate}" >/dev/null 2>&1; then
      printf '%s' "${candidate}"
      return 0
    fi
  done
  return 1
}

resolve_namespace() {
  if [[ -n "${NAMESPACE}" ]]; then
    oc get namespace "${NAMESPACE}" >/dev/null 2>&1 \
      || die "Namespace '${NAMESPACE}' was not found"
    return
  fi

  NAMESPACE="$(detect_namespace || true)"
  [[ -n "${NAMESPACE}" ]] \
    || die "Could not auto-detect namespace; pass -n redhat-ods-applications (RHOAI) or -n opendatahub (ODH)"
  log "Using namespace: ${NAMESPACE}"
}

delete_resource() {
  local kind="$1"
  local name="$2"

  if ! oc get "${kind}" "${name}" -n "${NAMESPACE}" >/dev/null 2>&1; then
    log "Skip ${kind}/${name}: not found"
    return 0
  fi

  if [[ "${DRY_RUN}" == true ]]; then
    log "[dry-run] Would delete ${kind}/${name}"
    return 0
  fi

  oc delete "${kind}" "${name}" -n "${NAMESPACE}" --wait=false
  log "Deleted ${kind}/${name}"
}

deprecate_imagestream() {
  local name="$1"

  if ! oc get imagestream "${name}" -n "${NAMESPACE}" >/dev/null 2>&1; then
    log "Skip ImageStream/${name}: not found"
    return 0
  fi

  local patch
  patch="$(oc get imagestream "${name}" -n "${NAMESPACE}" -o json | jq -c '
    .spec.tags |= map(
      .annotations = (.annotations // {}) |
      .annotations["opendatahub.io/image-tag-outdated"] = "true" |
      .annotations["opendatahub.io/workbench-image-recommended"] = "false"
    )
  ')"

  if [[ "${DRY_RUN}" == true ]]; then
    local tags
    tags="$(printf '%s' "${patch}" | jq -r '[.spec.tags[].name] | join(", ")')"
    log "[dry-run] Would deprecate ImageStream/${name} tags: ${tags:-<none>}"
    return 0
  fi

  oc patch imagestream "${name}" -n "${NAMESPACE}" --type=merge -p "${patch}"
  log "Deprecated all tags on ImageStream/${name}"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -n|--namespace)
        [[ $# -ge 2 ]] || die "Missing value for ${1}"
        NAMESPACE="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1 (use --help)"
        ;;
    esac
  done
}

main() {
  parse_args "$@"

  require_command oc
  require_command jq

  oc whoami >/dev/null 2>&1 || die "Not logged in to a cluster (run 'oc login' first)"
  resolve_namespace

  log "Starting RStudio deprecation cleanup in namespace ${NAMESPACE}"

  local bc
  for bc in "${RSTUDIO_BUILDCONFIGS[@]}"; do
    delete_resource buildconfig "${bc}"
  done

  local build_is
  for build_is in "${RSTUDIO_BUILD_IMAGESTREAMS[@]}"; do
    delete_resource imagestream "${build_is}"
  done

  local notebook_is
  for notebook_is in "${RSTUDIO_NOTEBOOK_IMAGESTREAMS[@]}"; do
    deprecate_imagestream "${notebook_is}"
  done

  if [[ "${DRY_RUN}" == true ]]; then
    log "Dry run complete. Re-run without --dry-run to apply changes."
  else
    log "RStudio deprecation cleanup complete."
    log "Existing RStudio workbenches keep running; new workbenches can no longer select these images."
  fi
}

main "$@"
