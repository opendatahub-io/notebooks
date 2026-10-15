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
PAUSE_WORKBENCHES_OPERATOR=true

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
  --operator-ns NS      Legacy platform operator namespace for fallback discovery
  --applications-ns NS  Override dashboard/applications namespace
  --dry-run             Client-side dry-run only (apply/revert)
  --no-restart-dashboard  Skip dashboard rollout after apply
  --no-pause-workbenches-operator  Do not scale down workbenches-operator (RHOAI 3.6+ may reconcile away edits)
  --clean-test          On revert, delete ImageStreams added by the last apply
  -h, --help            Show this help

Platform defaults:
  odh   operator: opendatahub-operator (pod label name=opendatahub-operator)
        applications: opendatahub, manifests: manifests/odh/base, dashboard: odh-dashboard
  rhoai platform operator: redhat-ods-operator (pod label name=rhods-operator)
        notebook manifests: workbenches-operator in redhat-ods-applications (RHOAI 3.6+)
        applications: redhat-ods-applications, manifests: manifests/rhoai/base, dashboard: rhods-dashboard
EOF
}

log() { printf '[apply-notebook-manifests-dev] %s\n' "$*" >&2; }
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
  "${KUSTOMIZE[@]}" "$@"
}

# Append KEY=value lines from overlay that are absent from dest (operator bundle may lag local manifests).
append_missing_env_keys() {
  local dest="$1"
  local overlay="$2"
  [[ -f "${overlay}" ]] || return 0

  local line key
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line//$'\r'/}"
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "${line}" == *"="* ]] || continue
    key="${line%%=*}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    if ! grep -q "^${key}=" "${dest}" 2>/dev/null; then
      printf '%s\n' "${line}" >> "${dest}"
    fi
  done < "${overlay}"
}

# Prefer local non-dummy values over operator params (dev testing personal/quay builds).
# Operator bundles often ship new ImageStreams as "dummy" until Konflux nudges digests;
# append_missing_env_keys alone cannot replace those placeholders.
overlay_local_env_overrides() {
  local dest="$1"
  local overlay="$2"
  [[ -f "${overlay}" && -f "${dest}" ]] || return 0

  local line key value tmp
  tmp="$(mktemp)"
  cp "${dest}" "${tmp}"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line//$'\r'/}"
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "${line}" == *"="* ]] || continue
    key="${line%%=*}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${line#*=}"
    [[ -n "${key}" && -n "${value}" && "${value}" != "dummy" ]] || continue
    if grep -q "^${key}=" "${tmp}" 2>/dev/null; then
      # Replace in-place (BSD/GNU sed portable via temp rewrite).
      local rewritten
      rewritten="$(mktemp)"
      awk -v k="${key}" -v v="${value}" '
        BEGIN { FS="="; OFS="=" }
        $1 == k { print k, v; next }
        { print }
      ' "${tmp}" > "${rewritten}"
      mv "${rewritten}" "${tmp}"
    else
      printf '%s\n' "${line}" >> "${tmp}"
    fi
  done < "${overlay}"
  mv "${tmp}" "${dest}"
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
      --no-pause-workbenches-operator)
        PAUSE_WORKBENCHES_OPERATOR=false
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
      --no-pause-workbenches-operator)
        PAUSE_WORKBENCHES_OPERATOR=false
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
  resolve_kustomize
  [[ -d "${MANIFESTS_DIR}" ]] || die "Manifest directory not found: ${MANIFESTS_DIR}"
}

readonly WORKBENCHES_OPERATOR_POD_LABEL="app.kubernetes.io/name=workbenches-operator"
readonly WORKBENCHES_OPERATOR_DEPLOY="workbenches-operator"

workbenches_operator_replicas_file() {
  printf '%s/workbenches-operator-replicas.txt' "${REVERT_DIR}"
}

workbenches_operator_paused_marker() {
  printf '%s/workbenches-operator-paused.txt' "${REVERT_DIR}"
}

workbenches_operator_deployment_exists() {
  oc get deployment "${WORKBENCHES_OPERATOR_DEPLOY}" -n "${APPLICATIONS_NS}" >/dev/null 2>&1
}

workbenches_operator_replicas() {
  oc get deployment "${WORKBENCHES_OPERATOR_DEPLOY}" -n "${APPLICATIONS_NS}" \
    -o jsonpath='{.spec.replicas}' 2>/dev/null || true
}

wait_for_workbenches_operator_rollout() {
  oc rollout status "deployment/${WORKBENCHES_OPERATOR_DEPLOY}" -n "${APPLICATIONS_NS}" --timeout=180s \
    >/dev/null 2>&1 || true
}

ensure_workbenches_operator_for_bundle_read() {
  [[ "${PAUSE_WORKBENCHES_OPERATOR}" == true ]] || return 0
  workbenches_operator_deployment_exists || return 0
  [[ "$(workbenches_operator_replicas)" == "0" ]] || return 0
  [[ -f "$(workbenches_operator_paused_marker)" ]] \
    || die "${WORKBENCHES_OPERATOR_DEPLOY} is scaled to 0; run revert to resume or scale it up manually"

  log "${WORKBENCHES_OPERATOR_DEPLOY} is paused; scaling up temporarily to read manifest bundle"
  oc scale "deployment/${WORKBENCHES_OPERATOR_DEPLOY}" -n "${APPLICATIONS_NS}" --replicas=1
  wait_for_workbenches_operator_rollout
  RESOLVED_OPERATOR_POD=""
}

pause_workbenches_operator() {
  [[ "${PAUSE_WORKBENCHES_OPERATOR}" == true ]] || return 0
  [[ "${DRY_RUN}" == true ]] && return 0
  workbenches_operator_deployment_exists || {
    log "WARNING: ${WORKBENCHES_OPERATOR_DEPLOY} not found in ${APPLICATIONS_NS}; cannot pause reconciliation"
    return 0
  }

  local replicas_file current saved
  replicas_file="$(workbenches_operator_replicas_file)"
  current="$(workbenches_operator_replicas)"
  mkdir -p "${REVERT_DIR}"

  if [[ ! -f "${replicas_file}" && -n "${current}" && "${current}" != "0" ]]; then
    printf '%s\n' "${current}" > "${replicas_file}"
  fi

  saved="$(tr -d '[:space:]' < "${replicas_file}" 2>/dev/null || true)"
  [[ -n "${saved}" ]] || saved="1"

  if [[ "${current}" == "0" ]]; then
    return 0
  fi

  log "Pausing ${WORKBENCHES_OPERATOR_DEPLOY} (scale ${current} -> 0) so ImageStream edits are not reconciled away"
  oc scale "deployment/${WORKBENCHES_OPERATOR_DEPLOY}" -n "${APPLICATIONS_NS}" --replicas=0
  wait_for_workbenches_operator_rollout
  if [[ "$(workbenches_operator_replicas)" != "0" ]]; then
    die "Failed to pause ${WORKBENCHES_OPERATOR_DEPLOY} in ${APPLICATIONS_NS} (platform may have reset replicas)"
  fi
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$(workbenches_operator_paused_marker)"
  log "Run revert when finished testing to restore the operator baseline and resume ${WORKBENCHES_OPERATOR_DEPLOY} (scale -> ${saved})"
}

resume_workbenches_operator() {
  [[ "${PAUSE_WORKBENCHES_OPERATOR}" == true ]] || return 0
  [[ "${DRY_RUN}" == true ]] && return 0
  workbenches_operator_deployment_exists || return 0
  [[ -f "$(workbenches_operator_paused_marker)" ]] || return 0

  local replicas_file replicas
  replicas_file="$(workbenches_operator_replicas_file)"
  replicas="1"
  if [[ -f "${replicas_file}" ]]; then
    replicas="$(tr -d '[:space:]' < "${replicas_file}")"
  fi
  [[ -n "${replicas}" && "${replicas}" != "0" ]] || replicas=1

  log "Resuming ${WORKBENCHES_OPERATOR_DEPLOY} (scale -> ${replicas})"
  oc scale "deployment/${WORKBENCHES_OPERATOR_DEPLOY}" -n "${APPLICATIONS_NS}" --replicas="${replicas}"
  wait_for_workbenches_operator_rollout
  rm -f "$(workbenches_operator_paused_marker)"
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

running_pods_for_label() {
  local ns="$1"
  local label="$2"
  oc get po -l "${label}" -n "${ns}" \
    -o jsonpath='{range .items[?(@.status.phase=="Running")]}{.metadata.name}{"\n"}{end}' 2>/dev/null
}

find_manifest_bundle_pod_for_label() {
  local ns="$1"
  local label="$2"
  local pod

  while IFS= read -r pod; do
    [[ -n "${pod}" ]] || continue
    if pod_has_notebook_manifest_bundle "${ns}" "${pod}"; then
      printf '%s' "${pod}"
      return 0
    fi
  done < <(running_pods_for_label "${ns}" "${label}")
  return 1
}

pod_has_notebook_manifest_bundle() {
  local ns="$1"
  local pod="$2"
  oc exec -n "${ns}" "${pod}" -- \
    test -f "${OPERATOR_MANIFESTS_PATH}/params-latest.env" >/dev/null 2>&1
}

try_manifest_bundle_pod() {
  local ns="$1"
  local label="$2"
  local pod

  [[ -n "${ns}" && -n "${label}" ]] || return 1
  pod="$(find_manifest_bundle_pod_for_label "${ns}" "${label}")" || return 1
  [[ -n "${pod}" ]] || return 1

  OPERATOR_NS="${ns}"
  OPERATOR_POD_LABEL="${label}"
  RESOLVED_OPERATOR_POD="${pod}"
  return 0
}

manifest_bundle_pod_candidates() {
  local ns label

  printf '%s\t%s\n' "${APPLICATIONS_NS}" "${WORKBENCHES_OPERATOR_POD_LABEL}"

  if [[ "${OPERATOR_NS_EXPLICIT}" == true && -n "${OPERATOR_NS}" ]]; then
    if [[ "${OPERATOR_NS}" != "${APPLICATIONS_NS}" ]]; then
      printf '%s\t%s\n' "${OPERATOR_NS}" "${WORKBENCHES_OPERATOR_POD_LABEL}"
    fi
    while IFS= read -r label; do
      [[ -n "${label}" ]] || continue
      printf '%s\t%s\n' "${OPERATOR_NS}" "${label}"
    done < <(operator_pod_labels_for_platform)
    return
  fi

  while IFS= read -r ns; do
    [[ -n "${ns}" ]] || continue
    while IFS= read -r label; do
      [[ -n "${label}" ]] || continue
      printf '%s\t%s\n' "${ns}" "${label}"
    done < <(operator_pod_labels_for_platform)
  done < <(operator_candidate_namespaces)
}

resolve_operator() {
  local ns label
  local -a tried=()
  local explicit_ns=""
  if [[ "${OPERATOR_NS_EXPLICIT}" == true ]]; then
    explicit_ns="${OPERATOR_NS}"
  fi

  while IFS=$'\t' read -r ns label; do
    [[ -n "${ns}" && -n "${label}" ]] || continue
    tried+=("${ns} (${label})")
    if try_manifest_bundle_pod "${ns}" "${label}"; then
      if [[ -n "${explicit_ns}" && "${explicit_ns}" != "${ns}" ]]; then
        log "Notebook manifests not in ${explicit_ns}; using ${OPERATOR_NS}/${RESOLVED_OPERATOR_POD} (${OPERATOR_POD_LABEL})"
      else
        log "Using notebook manifest bundle pod ${OPERATOR_NS}/${RESOLVED_OPERATOR_POD} (${OPERATOR_POD_LABEL})"
      fi
      return 0
    fi
  done < <(manifest_bundle_pod_candidates)

  if [[ -n "${explicit_ns}" ]]; then
    log "No notebook manifest bundle in ${explicit_ns}; searching other namespaces..."
    OPERATOR_NS_EXPLICIT=false
    resolve_operator
    return $?
  fi

  die "Could not find a pod with ${OPERATOR_MANIFESTS_PATH}/params-latest.env. Tried: ${tried[*]}"
}

ensure_operator_resolved() {
  if [[ -z "${RESOLVED_OPERATOR_POD}" ]]; then
    resolve_operator
  fi
}

workbench_namespace() {
  # Prefer the FQ resource name: clusters may also register
  # workbenches.444444-components.platform.opendatahub.io, and the short name
  # "workbenches" can resolve to that empty group (NotFound).
  local ns=""
  ns="$(oc get workbenches.components.platform.opendatahub.io default-workbenches \
    -o jsonpath='{.spec.workbenchNamespace}' 2>/dev/null || true)"
  if [[ -z "${ns}" ]]; then
    ns="$(oc get datasciencecluster default-dsc \
      -o jsonpath='{.spec.components.workbenches.workbenchNamespace}' 2>/dev/null || true)"
  fi
  [[ -n "${ns}" ]] || die "Workbenches CR default-workbenches not found (and DSC workbenchNamespace unset)"
  printf '%s\n' "${ns}"
}

imagestream_names_from_build() {
  local dir="$1"
  kustomize_build "${dir}" | awk '
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

pod_has_tar() {
  local pod="$1"
  oc exec -n "${OPERATOR_NS}" "${pod}" -- tar --version >/dev/null 2>&1 \
    || oc exec -n "${OPERATOR_NS}" "${pod}" -- sh -c 'command -v tar >/dev/null 2>&1' >/dev/null 2>&1
}

decode_base64_to_file() {
  local src="$1"
  local dest="$2"
  if base64 -d < "${src}" > "${dest}" 2>/dev/null; then
    return 0
  fi
  if base64 -D < "${src}" > "${dest}" 2>/dev/null; then
    return 0
  fi
  openssl base64 -d -A -in "${src}" -out "${dest}"
}

# Reject paths that could escape local_path (streamed copy has no tar/oc cp sanitization).
safe_manifest_bundle_relpath() {
  local rel="$1"
  if [[ -z "${rel}" || "${rel}" == /* ]]; then
    return 1
  fi
  if [[ "/${rel}/" == */../* ]]; then
    return 1
  fi
  return 0
}

# One oc exec round trip (find + base64). Per-file oc exec cat can take many minutes.
copy_remote_tree_from_pod_stream() {
  local pod="$1"
  local remote_path="$2"
  local local_path="$3"
  local payload b64_chunk line rel dest file_count

  mkdir -p "${local_path}"
  payload="$(mktemp)"
  b64_chunk="$(mktemp)"
  file_count=0
  dest=""

  log "Streaming manifest tree from ${OPERATOR_NS}/${pod}:${remote_path} (single oc exec)..."

  if ! oc exec -n "${OPERATOR_NS}" "${pod}" -- sh -c "
    set -eu
    root='${remote_path}'
    [ -d \"\${root}\" ] || exit 1
    if ! command -v base64 >/dev/null 2>&1; then
      echo 'base64 not found in pod' >&2
      exit 1
    fi
    find \"\${root}\" -type f | LC_ALL=C sort | while IFS= read -r path; do
      rel=\${path#\"\${root}/\"}
      if [ \"\${rel}\" = \"\${path}\" ]; then
        rel=\${path#\"\${root}\"}
        rel=\${rel#/}
      fi
      printf 'FILE:%s\n' \"\${rel}\"
      base64 \"\${path}\"
      printf 'ENDFILE\n'
    done
  " > "${payload}"; then
    rm -f "${payload}" "${b64_chunk}"
    die "Failed to stream manifest bundle from ${OPERATOR_NS}/${pod}"
  fi

  if [[ ! -s "${payload}" ]]; then
    rm -f "${payload}" "${b64_chunk}"
    die "Empty manifest bundle at ${remote_path} in ${OPERATOR_NS}/${pod}"
  fi

  : > "${b64_chunk}"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" == FILE:* ]]; then
      if [[ -n "${dest}" ]]; then
        decode_base64_to_file "${b64_chunk}" "${dest}"
        file_count=$((file_count + 1))
      fi
      : > "${b64_chunk}"
      rel="${line#FILE:}"
      if ! safe_manifest_bundle_relpath "${rel}"; then
        rm -f "${payload}" "${b64_chunk}"
        die "Refusing unsafe path from ${OPERATOR_NS}/${pod}: ${rel}"
      fi
      dest="${local_path}/${rel}"
      mkdir -p "$(dirname "${dest}")"
    elif [[ "${line}" == ENDFILE ]]; then
      if [[ -n "${dest}" ]]; then
        decode_base64_to_file "${b64_chunk}" "${dest}"
        file_count=$((file_count + 1))
        dest=""
        : > "${b64_chunk}"
      fi
    else
      printf '%s\n' "${line}" >> "${b64_chunk}"
    fi
  done < "${payload}"

  if [[ -n "${dest}" ]]; then
    decode_base64_to_file "${b64_chunk}" "${dest}"
    file_count=$((file_count + 1))
  fi

  rm -f "${payload}" "${b64_chunk}"

  if [[ "${file_count}" -eq 0 ]]; then
    die "No files copied from ${remote_path} in ${OPERATOR_NS}/${pod}"
  fi
  log "Copied ${file_count} manifest file(s) from pod"
}

copy_manifest_bundle_base_from_pod() {
  local pod="$1"
  local local_base="${REVERT_DIR}/base"
  local remote_base="${OPERATOR_MANIFESTS_PATH}"
  local remote_cp_src

  rm -rf "${local_base}"

  if pod_has_tar "${pod}"; then
    log "Copying manifest bundle with tar from ${OPERATOR_NS}/${pod}"
    oc exec -n "${OPERATOR_NS}" "${pod}" -- \
      tar cf - -C "${OPERATOR_MANIFESTS_TAR_DIR}" base \
      | tar xf - -C "${REVERT_DIR}"
    return 0
  fi

  remote_cp_src="${OPERATOR_NS}/${pod}:${remote_base}"
  if command -v oc >/dev/null 2>&1 \
    && oc cp "${remote_cp_src}" "${local_base}" >/dev/null 2>&1; then
    log "Copied manifest bundle from ${OPERATOR_NS}/${pod}"
    return 0
  fi

  copy_remote_tree_from_pod_stream "${pod}" "${remote_base}" "${local_base}"
}

snapshot_baseline() {
  local pod="$1"
  mkdir -p "${REVERT_DIR}"
  save_revert_metadata
  log "Platform: ${PLATFORM} — snapshotting operator baseline to ${REVERT_DIR}/base"

  copy_manifest_bundle_base_from_pod "${pod}"

  kustomize_build "${REVERT_DIR}/base" > "${REVERT_DIR}/rendered-before.yaml"
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
  local workdir operator_params operator_commits
  workdir="$(mktemp -d)"
  cp -r "${MANIFESTS_DIR}/." "${workdir}/"

  operator_params="$(mktemp)"
  operator_commits="$(mktemp)"
  oc exec -n "${OPERATOR_NS}" "${pod}" -- \
    cat "${OPERATOR_MANIFESTS_PATH}/params-latest.env" > "${operator_params}"
  oc exec -n "${OPERATOR_NS}" "${pod}" -- \
    cat "${OPERATOR_MANIFESTS_PATH}/commit-latest.env" > "${operator_commits}" 2>/dev/null || : > "${operator_commits}"

  cp "${operator_params}" "${workdir}/params-latest.env"
  append_missing_env_keys "${workdir}/params-latest.env" "${MANIFESTS_DIR}/params-latest.env"
  overlay_local_env_overrides "${workdir}/params-latest.env" "${MANIFESTS_DIR}/params-latest.env"

  if [[ -s "${operator_commits}" ]]; then
    cp "${operator_commits}" "${workdir}/commit-latest.env"
  else
    : > "${workdir}/commit-latest.env"
  fi
  append_missing_env_keys "${workdir}/commit-latest.env" "${MANIFESTS_DIR}/commit-latest.env"
  overlay_local_env_overrides "${workdir}/commit-latest.env" "${MANIFESTS_DIR}/commit-latest.env"

  rm -f "${operator_params}" "${operator_commits}"
  log "Using operator params/commit env with local keys merged (non-dummy local overrides win)"

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
  ensure_workbenches_operator_for_bundle_read
  ensure_operator_resolved
  snapshot_baseline "${RESOLVED_OPERATOR_POD}"
}

cmd_preview() {
  check_build_prerequisites
  local workdir
  ensure_workbenches_operator_for_bundle_read
  ensure_operator_resolved
  workdir="$(build_workdir "${RESOLVED_OPERATOR_POD}")"

  log "Previewing ${PLATFORM} kustomize build from ${MANIFESTS_DIR}"
  kustomize_build "${workdir}"
  log "Resource counts:"
  kustomize_build "${workdir}" | awk '/^kind: / { counts[$2]++ } END { for (k in counts) print counts[k], k }' | sort -rn

  cleanup_temp_files "${workdir}" ""
}

cmd_apply() {
  check_build_prerequisites
  local workdir rendered
  ensure_workbenches_operator_for_bundle_read
  ensure_operator_resolved
  workdir="$(build_workdir "${RESOLVED_OPERATOR_POD}")"
  rendered="$(mktemp)"

  snapshot_baseline "${RESOLVED_OPERATOR_POD}"
  pause_workbenches_operator

  kustomize_build "${workdir}" > "${rendered}"
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

  pause_workbenches_operator

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

  resume_workbenches_operator

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
