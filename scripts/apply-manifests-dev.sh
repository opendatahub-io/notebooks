#!/usr/bin/env bash
#
# Apply or revert local notebook ImageStream manifests on an ODH or RHOAI dev cluster.
#
# See docs/manifest-cluster-dev-testing.md for usage.
#
# Usage:
#   scripts/apply-manifests-dev.sh [--platform odh|rhoai] apply [--target applications|workbench|both]
#   scripts/apply-manifests-dev.sh [--platform odh|rhoai] revert [--clean-test]
#   scripts/apply-manifests-dev.sh [--platform odh|rhoai] preview
#   scripts/apply-manifests-dev.sh [--platform odh|rhoai] snapshot
#
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PLATFORM="rhoai"
PLATFORM_EXPLICIT=false
TARGET="applications"
REVERT_DIR=""
OPERATOR_NS=""
OPERATOR_NS_EXPLICIT=false
RESOLVED_OPERATOR_POD=""
APPLICATIONS_NS=""
DRY_RUN=false
CLEAN_TEST=false
RESTART_DASHBOARD=true

MANIFESTS_DIR=""
MANIFESTS_VARIANT=""
OPERATOR_POD_LABEL=""
OPERATOR_MANIFESTS_TAR_DIR=""
DASHBOARD_DEPLOY=""

usage() {
  cat <<'EOF'
Apply or revert local notebook ImageStream manifests on an ODH or RHOAI dev cluster.

Usage:
  scripts/apply-manifests-dev.sh [--platform odh|rhoai] <command> [options]

Commands:
  apply     Snapshot operator baseline, build manifests, apply to cluster
  revert    Restore operator baseline; use --clean-test to remove extras
  preview   Build and print manifests (no cluster changes)
  snapshot  Save operator baseline for later revert

Options:
  --platform PLATFORM   odh (upstream) or rhoai (default: rhoai)
  --target TARGET       applications (default), workbench, or both
  --revert-dir DIR      Snapshot directory (default: /tmp/<platform>-manifests-revert)
  --operator-ns NS      Override operator namespace (auto-discovered if wrong or omitted)
  --applications-ns NS  Override dashboard/applications namespace
  --dry-run             Client-side dry-run only (apply/revert)
  --no-restart-dashboard  Skip dashboard rollout after apply
  --clean-test          On revert, delete ImageStreams added by the last apply
  -h, --help            Show this help

Platform defaults:
  odh   operator: opendatahub-operator (pod label name=opendatahub-operator)
        applications: opendatahub, manifests: manifests/odh/base, dashboard: odh-dashboard
  rhoai operator: redhat-ods-operator (pod label name=rhods-operator)
        applications: redhat-ods-applications, manifests: manifests/rhoai/base, dashboard: rhods-dashboard
EOF
}

log() { printf '[apply-notebook-manifests-dev] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

configure_platform() {
  case "${PLATFORM}" in
    odh)
      MANIFESTS_VARIANT="odh"
      MANIFESTS_DIR="${REPO_ROOT}/manifests/odh/base"
      OPERATOR_POD_LABEL="name=opendatahub-operator"
      DASHBOARD_DEPLOY="odh-dashboard"
      OPERATOR_NS="${OPERATOR_NS:-opendatahub-operator}"
      APPLICATIONS_NS="${APPLICATIONS_NS:-opendatahub}"
      REVERT_DIR="${REVERT_DIR:-/tmp/odh-manifests-revert}"
      ;;
    rhoai)
      MANIFESTS_VARIANT="rhoai"
      MANIFESTS_DIR="${REPO_ROOT}/manifests/rhoai/base"
      OPERATOR_POD_LABEL="name=rhods-operator"
      DASHBOARD_DEPLOY="rhods-dashboard"
      OPERATOR_NS="${OPERATOR_NS:-redhat-ods-operator}"
      APPLICATIONS_NS="${APPLICATIONS_NS:-redhat-ods-applications}"
      REVERT_DIR="${REVERT_DIR:-/tmp/rhoai-manifests-revert}"
      ;;
    *)
      die "${PLATFORM} is not supported; use odh or rhoai"
      ;;
  esac
  OPERATOR_MANIFESTS_TAR_DIR="/opt/manifests/workbenches/notebooks/${MANIFESTS_VARIANT}"
  OPERATOR_MANIFESTS_PATH="${OPERATOR_MANIFESTS_TAR_DIR}/base"
}

parse_args() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 1
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --platform)
        PLATFORM="${2:?}"
        PLATFORM_EXPLICIT=true
        shift 2
        ;;
      --target)
        TARGET="${2:?}"
        shift 2
        ;;
      --revert-dir)
        REVERT_DIR="${2:?}"
        shift 2
        ;;
      --operator-ns)
        OPERATOR_NS="${2:?}"
        OPERATOR_NS_EXPLICIT=true
        shift 2
        ;;
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
      --clean-test)
        CLEAN_TEST=true
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      apply | revert | preview | snapshot)
        COMMAND="$1"
        shift
        break
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done

  [[ -n "${COMMAND:-}" ]] || die "Missing command (apply, revert, preview, snapshot)"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --target)
        TARGET="${2:?}"
        shift 2
        ;;
      --revert-dir)
        REVERT_DIR="${2:?}"
        shift 2
        ;;
      --operator-ns)
        OPERATOR_NS="${2:?}"
        OPERATOR_NS_EXPLICIT=true
        shift 2
        ;;
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
      --clean-test)
        CLEAN_TEST=true
        shift
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done

  case "${COMMAND}" in
    apply | revert | preview | snapshot) ;;
    *)
      die "Unknown command: ${COMMAND}"
      ;;
  esac

  case "${TARGET}" in
    applications | workbench | both) ;;
    *)
      die "--target must be applications, workbench, or both"
      ;;
  esac

  if [[ "${COMMAND}" == "revert" && -z "${REVERT_DIR}" ]]; then
    local primary_revert_dir secondary_revert_dir
    if [[ "${PLATFORM}" == "odh" ]]; then
      primary_revert_dir=/tmp/odh-manifests-revert
      secondary_revert_dir=/tmp/rhoai-manifests-revert
    else
      primary_revert_dir=/tmp/rhoai-manifests-revert
      secondary_revert_dir=/tmp/odh-manifests-revert
    fi

    if [[ -f "${primary_revert_dir}/platform.txt" ]]; then
      REVERT_DIR="${primary_revert_dir}"
    elif [[ -f "${secondary_revert_dir}/platform.txt" ]]; then
      REVERT_DIR="${secondary_revert_dir}"
    fi
  fi

  if [[ "${COMMAND}" == "revert" && "${PLATFORM_EXPLICIT}" == false \
        && -n "${REVERT_DIR}" && -f "${REVERT_DIR}/platform.txt" ]]; then
    PLATFORM="$(tr -d '[:space:]' < "${REVERT_DIR}/platform.txt")"
  fi

  configure_platform
}

save_revert_metadata() {
  printf '%s\n' "${PLATFORM}" > "${REVERT_DIR}/platform.txt"
  printf '%s\n' "${OPERATOR_NS}" > "${REVERT_DIR}/operator-ns.txt"
}

check_cluster_prerequisites() {
  need_cmd oc

  oc whoami >/dev/null 2>&1 || die "Not logged in to OpenShift (oc whoami failed)"

  local wb_state
  wb_state="$(oc get datasciencecluster default-dsc \
    -o jsonpath='{.spec.components.workbenches.managementState}' 2>/dev/null || true)"
  [[ "${wb_state}" == "Managed" ]] || die "Workbenches must be Managed (got: ${wb_state:-<unset>})"
}

check_build_prerequisites() {
  check_cluster_prerequisites
  need_cmd kustomize
  [[ -d "${MANIFESTS_DIR}" ]] || die "Manifest directory not found: ${MANIFESTS_DIR}"
}

operator_pod_labels_for_platform() {
  case "${PLATFORM}" in
    rhoai) printf '%s\n' "name=rhods-operator" "name=opendatahub-operator" ;;
    odh) printf '%s\n' "name=opendatahub-operator" "name=rhods-operator" ;;
  esac
}

operator_candidate_namespaces() {
  if [[ "${OPERATOR_NS_EXPLICIT}" == true && -n "${OPERATOR_NS}" ]]; then
    printf '%s\n' "${OPERATOR_NS}"
    return
  fi
  case "${PLATFORM}" in
    rhoai)
      printf '%s\n' "redhat-ods-operator" "openshift-operators" "opendatahub-operator"
      ;;
    odh)
      printf '%s\n' "opendatahub-operator" "openshift-operators" "redhat-ods-operator"
      ;;
  esac
}

resolve_operator() {
  local ns label pod
  local -a tried=()
  local explicit_ns=""
  if [[ "${OPERATOR_NS_EXPLICIT}" == true ]]; then
    explicit_ns="${OPERATOR_NS}"
  fi

  while IFS= read -r ns; do
    [[ -n "${ns}" ]] || continue
    while IFS= read -r label; do
      [[ -n "${label}" ]] || continue
      tried+=("${ns} (${label})")
      pod="$(oc get po -l "${label}" -n "${ns}" \
        -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | awk '{print $1}')"
      if [[ -n "${pod}" ]]; then
        OPERATOR_NS="${ns}"
        OPERATOR_POD_LABEL="${label}"
        RESOLVED_OPERATOR_POD="${pod}"
        if [[ -n "${explicit_ns}" && "${explicit_ns}" != "${ns}" ]]; then
          log "Operator not in ${explicit_ns}; using ${OPERATOR_NS}/${RESOLVED_OPERATOR_POD} (${OPERATOR_POD_LABEL})"
        else
          log "Using operator pod ${OPERATOR_NS}/${RESOLVED_OPERATOR_POD} (${OPERATOR_POD_LABEL})"
        fi
        return 0
      fi
    done < <(operator_pod_labels_for_platform)
  done < <(operator_candidate_namespaces)

  if [[ -n "${explicit_ns}" ]]; then
    log "No running operator pod in ${explicit_ns}; searching other namespaces..."
    OPERATOR_NS_EXPLICIT=false
    resolve_operator
    return $?
  fi

  die "Could not find a running operator pod. Tried: ${tried[*]}"
}

ensure_operator_resolved() {
  if [[ -z "${RESOLVED_OPERATOR_POD}" ]]; then
    resolve_operator
  fi
}

workbench_namespace() {
  oc get workbenches default-workbenches \
    -o jsonpath='{.spec.workbenchNamespace}' 2>/dev/null \
    || die "Workbenches CR default-workbenches not found"
}

imagestream_names_from_build() {
  local dir="$1"
  kustomize build "${dir}" | awk '
    /^kind: ImageStream$/ { is=1; next }
    is && /^  name: / { print $2; is=0 }
  ' | sort -u
}

target_namespaces() {
  local wb_ns=""
  case "${TARGET}" in
    applications) printf '%s\n' "${APPLICATIONS_NS}" ;;
    workbench)
      wb_ns="$(workbench_namespace)"
      [[ -n "${wb_ns}" ]] || die "Workbench namespace is unset"
      printf '%s\n' "${wb_ns}"
      ;;
    both)
      wb_ns="$(workbench_namespace)"
      [[ -n "${wb_ns}" ]] || die "Workbench namespace is unset"
      printf '%s\n' "${APPLICATIONS_NS}"
      if [[ "${wb_ns}" != "${APPLICATIONS_NS}" ]]; then
        printf '%s\n' "${wb_ns}"
      fi
      ;;
  esac
}

snapshot_baseline() {
  local pod="$1"
  mkdir -p "${REVERT_DIR}"
  save_revert_metadata
  log "Platform: ${PLATFORM} — snapshotting operator baseline to ${REVERT_DIR}/base"

  oc exec -n "${OPERATOR_NS}" "${pod}" -- \
    tar cf - -C "${OPERATOR_MANIFESTS_TAR_DIR}" base \
    | tar xf - -C "${REVERT_DIR}"

  kustomize build "${REVERT_DIR}/base" > "${REVERT_DIR}/rendered-before.yaml"
  imagestream_names_from_build "${REVERT_DIR}/base" > "${REVERT_DIR}/baseline-imagestream-names.txt"

  target_namespaces > "${REVERT_DIR}/snapshot-namespaces.txt"
  local ns
  while IFS= read -r ns; do
    oc get imagestreams -n "${ns}" -l opendatahub.io/component=true -o yaml \
      > "${REVERT_DIR}/imagestreams-${ns}-before.yaml" 2>/dev/null || true
    oc get imagestreams -n "${ns}" -l opendatahub.io/component=true \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' \
      > "${REVERT_DIR}/imagestreams-${ns}-before.txt" 2>/dev/null || true
  done < "${REVERT_DIR}/snapshot-namespaces.txt"

  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${REVERT_DIR}/snapshot-time.txt"
  log "Baseline snapshot complete ($(wc -l < "${REVERT_DIR}/baseline-imagestream-names.txt") ImageStreams)"
}

build_workdir() {
  local pod="$1"
  local workdir
  workdir="$(mktemp -d)"
  cp -r "${MANIFESTS_DIR}/." "${workdir}/"

  oc exec -n "${OPERATOR_NS}" "${pod}" -- \
    cat "${OPERATOR_MANIFESTS_PATH}/params-latest.env" > "${workdir}/params-latest.env"
  oc exec -n "${OPERATOR_NS}" "${pod}" -- \
    cat "${OPERATOR_MANIFESTS_PATH}/commit-latest.env" > "${workdir}/commit-latest.env"

  printf '%s' "${workdir}"
}

apply_to_namespace() {
  local ns="$1"
  local rendered="$2"

  if [[ "${DRY_RUN}" == true ]]; then
    log "[dry-run] Would apply to namespace ${ns}"
    oc apply --dry-run=client -n "${ns}" -f "${rendered}"
  else
    log "Applying to namespace ${ns}"
    oc apply -n "${ns}" -f "${rendered}"
  fi
}

cmd_snapshot() {
  check_build_prerequisites
  ensure_operator_resolved
  snapshot_baseline "${RESOLVED_OPERATOR_POD}"
}

cmd_preview() {
  check_build_prerequisites
  local workdir
  ensure_operator_resolved
  workdir="$(build_workdir "${RESOLVED_OPERATOR_POD}")"

  log "Previewing ${PLATFORM} kustomize build from ${MANIFESTS_DIR}"
  kustomize build "${workdir}"
  log "Resource counts:"
  kustomize build "${workdir}" | awk '/^kind: / { counts[$2]++ } END { for (k in counts) print counts[k], k }' | sort -rn

  cleanup_temp_files "${workdir}" ""
}

cmd_apply() {
  check_build_prerequisites
  local workdir rendered
  ensure_operator_resolved
  workdir="$(build_workdir "${RESOLVED_OPERATOR_POD}")"
  rendered="$(mktemp)"

  snapshot_baseline "${RESOLVED_OPERATOR_POD}"

  kustomize build "${workdir}" > "${rendered}"
  imagestream_names_from_build "${workdir}" > "${REVERT_DIR}/applied-imagestream-names.txt"
  target_namespaces > "${REVERT_DIR}/applied-namespaces.txt"

  log "Build summary:"
  awk '/^kind: / { counts[$2]++ } END { for (k in counts) print "  ", counts[k], k }' "${rendered}" | sort -rn >&2

  while IFS= read -r ns; do
    [[ -n "${ns}" ]] || continue
    apply_to_namespace "${ns}" "${rendered}"
  done < "${REVERT_DIR}/applied-namespaces.txt"

  if [[ "${DRY_RUN}" == false && "${RESTART_DASHBOARD}" == true ]]; then
    if oc get deploy "${DASHBOARD_DEPLOY}" -n "${APPLICATIONS_NS}" >/dev/null 2>&1; then
      log "Restarting ${DASHBOARD_DEPLOY}"
      oc rollout restart "deploy/${DASHBOARD_DEPLOY}" -n "${APPLICATIONS_NS}"
    fi
  fi

  log "Done. Revert with: ${SCRIPT_DIR}/$(basename "$0") revert --clean-test (active plat: ${PLATFORM})"
  log "Snapshot saved in ${REVERT_DIR}"
  cleanup_temp_files "${workdir}" "${rendered}"
}

delete_test_added_imagestreams() {
  local applied="${REVERT_DIR}/applied-imagestream-names.txt"
  local ns_file="${REVERT_DIR}/applied-namespaces.txt"
  [[ -f "${applied}" ]] \
    || die "Missing snapshot files in ${REVERT_DIR}; run apply or snapshot first"
  [[ -f "${ns_file}" ]] || die "Missing ${ns_file}; run apply first"

  local ns name before_names
  while IFS= read -r ns; do
    [[ -n "${ns}" ]] || continue
    before_names="${REVERT_DIR}/imagestreams-${ns}-before.txt"
    [[ -f "${before_names}" ]] || die "Missing ${before_names}; cannot safely clean test ImageStreams"
    while IFS= read -r name; do
      [[ -n "${name}" ]] || continue
      if grep -Fxq -- "${name}" "${before_names}"; then
        continue
      fi
      if oc get imagestream "${name}" -n "${ns}" >/dev/null 2>&1; then
        log "Deleting test-added ImageStream ${ns}/${name}"
        if [[ "${DRY_RUN}" == true ]]; then
          log "[dry-run] Would delete imagestream ${name} -n ${ns}"
        else
          oc delete imagestream "${name}" -n "${ns}"
        fi
      fi
    done < "${applied}"
  done < "${ns_file}"
}

cmd_revert() {
  check_cluster_prerequisites
  [[ -f "${REVERT_DIR}/rendered-before.yaml" ]] \
    || die "No revert snapshot at ${REVERT_DIR}/rendered-before.yaml — run apply or snapshot first"

  local ns ns_file wb_ns
  ns_file="${REVERT_DIR}/applied-namespaces.txt"
  [[ -f "${ns_file}" ]] || ns_file="${REVERT_DIR}/snapshot-namespaces.txt"
  if [[ -f "${ns_file}" ]]; then
    while IFS= read -r ns; do
      [[ -n "${ns}" ]] || continue
      log "Restoring baseline in ${ns}"
      if [[ "${DRY_RUN}" == true ]]; then
        oc apply --dry-run=client -n "${ns}" -f "${REVERT_DIR}/rendered-before.yaml"
      else
        oc apply -n "${ns}" -f "${REVERT_DIR}/rendered-before.yaml"
      fi
    done < "${ns_file}"
  else
    log "Restoring baseline in ${APPLICATIONS_NS}"
    if [[ "${DRY_RUN}" == true ]]; then
      oc apply --dry-run=client -n "${APPLICATIONS_NS}" -f "${REVERT_DIR}/rendered-before.yaml"
    else
      oc apply -n "${APPLICATIONS_NS}" -f "${REVERT_DIR}/rendered-before.yaml"
    fi
    wb_ns="$(workbench_namespace)"
    if [[ "${wb_ns}" != "${APPLICATIONS_NS}" ]]; then
      log "Restoring baseline in ${wb_ns}"
      if [[ "${DRY_RUN}" == true ]]; then
        oc apply --dry-run=client -n "${wb_ns}" -f "${REVERT_DIR}/rendered-before.yaml"
      else
        oc apply -n "${wb_ns}" -f "${REVERT_DIR}/rendered-before.yaml"
      fi
    fi
  fi

  if [[ "${CLEAN_TEST}" == true ]]; then
    log "Removing ImageStreams not in operator baseline"
    delete_test_added_imagestreams
  fi

  log "Revert complete. ImageStreams from before your test may still exist — that is expected."
}

cleanup_temp_files() {
  local workdir="${1:-}"
  local rendered="${2:-}"

  if [[ -n "${workdir}" ]]; then
    rm -rf -- "${workdir}"
  fi
  if [[ -n "${rendered}" ]]; then
    rm -f -- "${rendered}"
  fi
}

main() {
  parse_args "$@"
  case "${COMMAND}" in
    snapshot) cmd_snapshot ;;
    preview) cmd_preview ;;
    apply) cmd_apply ;;
    revert) cmd_revert ;;
  esac
}

main "$@"
