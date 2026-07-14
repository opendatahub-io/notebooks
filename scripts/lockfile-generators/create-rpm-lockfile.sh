#!/usr/bin/env bash
set -euo pipefail

# create-rpm-lockfile.sh — Generate rpms.lock.yaml with exact RPM URLs and checksums.
#
# Hermetic builds (Konflux/cachi2) require a lockfile that pins every RPM
# package URL and checksum so they can be prefetched and installed offline.
#
# This script builds the notebook-rpm-lockfile image (from Dockerfile.rpm-lockfile),
# runs it with the repository mounted, and executes rpm-lockfile-prototype against
# the directory containing rpms.in.yaml (plus *.repo files).  The tool resolves
# all listed packages and their transitive dependencies for each architecture
# listed in rpms.in.yaml and writes rpms.lock.yaml in the same directory.
#
# With --download, it uses hermeto (hermetoproject/hermeto) to fetch all RPMs
# into cachi2/output/deps/rpm/ and create DNF repo metadata for local offline
# builds.  When a RHEL subscription is active, entitlement certs are extracted
# from the lockfile container and passed to hermeto for cdn.redhat.com auth.

# --- Configuration & Defaults ---
SCRIPTS_PATH="scripts/lockfile-generators"
UBI9_IMAGE="registry.redhat.io/ubi9:9.6"
UBI9_PYTHON312_IMAGE="registry.access.redhat.com/ubi9/python-312:latest"
ODH_BASE_IMAGE="quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest"

RPM_INPUT=""
ACTIVATION_KEY=""
ORG=""
BASE_IMAGE_OVERRIDE=""
RHEL_VERSION_OVERRIDE=""
DO_DOWNLOAD=false

# --- Functions ---
show_help() {
  cat << EOF
Usage: ./$SCRIPTS_PATH/create-rpm-lockfile.sh [OPTIONS]

This script builds a container image and runs rpm-lockfile-prototype to
generate an RPM lock file. It MUST be run from the repository root.

Options:
  --rpm-input FILE       Path to rpms.in.yaml
                         (e.g., codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.in.yaml)
  --base-image IMAGE     Base image for lockfile generation (RHDS only)
  --rhel-version VER     RHEL releasever for subscription-manager (RHDS only; e.g. 9.6, 9.8)
  --activation-key VALUE Red Hat activation key for subscription-manager
  --org VALUE            Red Hat organization ID for subscription-manager
  --download             After generating the lockfile, fetch all RPMs from rpms.lock.yaml
                         into ./cachi2/output/deps/rpm/ and create repo metadata (for dnf)
  --help                 Show this help message and exit

Examples:
  # Upstream (ODH):
  ./$SCRIPTS_PATH/create-rpm-lockfile.sh \\
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.in.yaml

  ./$SCRIPTS_PATH/create-rpm-lockfile.sh \\
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.in.yaml --download

  # Downstream (RHDS) for rhoai-2.25 ubi9/python-312 (public UBI repos, no subscription):
  ./$SCRIPTS_PATH/create-rpm-lockfile.sh \\
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rhds/rpms.in.yaml

  # Downstream (RHDS) with RHEL subscription (AIPCC / RHOAI 3.5+ only):
  ./$SCRIPTS_PATH/create-rpm-lockfile.sh \\
    --activation-key my-key --org my-org \\
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rhds/rpms.in.yaml
EOF
}

error_exit() {
  echo "Error: $1" >&2
  echo "Use --help for usage information." >&2
  exit 1
}

# --- Validation ---
# Ensure script is executed from repository root
if [[ ! -f "$SCRIPTS_PATH/Dockerfile.rpm-lockfile" ]]; then
  error_exit "This script MUST be run from the repository root."
fi

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)           show_help; exit 0 ;;
    --activation-key)    [[ $# -ge 2 ]] || error_exit "--activation-key requires a value"
                         ACTIVATION_KEY="$2"; shift 2 ;;
    --org)               [[ $# -ge 2 ]] || error_exit "--org requires a value"
                         ORG="$2";            shift 2 ;;
    --rpm-input)         [[ $# -ge 2 ]] || error_exit "--rpm-input requires a value"
                         RPM_INPUT="$2";      shift 2 ;;
    --base-image)        [[ $# -ge 2 ]] || error_exit "--base-image requires a value"
                         BASE_IMAGE_OVERRIDE="$2"; shift 2 ;;
    --rhel-version)      [[ $# -ge 2 ]] || error_exit "--rhel-version requires a value"
                         RHEL_VERSION_OVERRIDE="$2"; shift 2 ;;
    --download)          DO_DOWNLOAD=true;   shift ;;
    *)                   error_exit "Unknown argument: '$1'" ;;
  esac
done

# Fall back to env vars when CLI args are not provided (GHA passes secrets
# this way so they never appear in shell command traces).
ACTIVATION_KEY="${ACTIVATION_KEY:-${SUBSCRIPTION_ACTIVATION_KEY:-}}"
ORG="${ORG:-${SUBSCRIPTION_ORG:-}}"

# --- Required argument check ---
[[ -z "$RPM_INPUT" ]] && error_exit "--rpm-input is required. E.g. --rpm-input codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.in.yaml"
[[ -f "$RPM_INPUT" ]] || error_exit "rpms.in.yaml not found at: $RPM_INPUT"

# Derive the prefetch-input directory from the rpms.in.yaml path
PREFETCH_DIR="$(dirname "$RPM_INPUT")"

# --- Base image and RHEL version ---
# RHDS on rhoai-2.25 uses ubi9/python-312 (public UBI repos, no subscription).
# ODH uses CentOS Stream base. RHOAI 3.5+ AIPCC uses subscription + RHEL 9.6 EUS.
if [[ -n "$ACTIVATION_KEY" ]] && [[ -n "$ORG" ]]; then
  if [[ -n "$BASE_IMAGE_OVERRIDE" ]]; then
    BASE_IMAGE="$BASE_IMAGE_OVERRIDE"
    RHEL_VERSION="${RHEL_VERSION_OVERRIDE:-9.8}"
  else
    BASE_IMAGE="$UBI9_IMAGE"
    RHEL_VERSION="${RHEL_VERSION_OVERRIDE:-9.6}"
  fi
elif [[ "$RPM_INPUT" == *prefetch-input/rhds/* ]]; then
  BASE_IMAGE="${BASE_IMAGE_OVERRIDE:-$UBI9_PYTHON312_IMAGE}"
  RHEL_VERSION=""
else
  BASE_IMAGE="${BASE_IMAGE_OVERRIDE:-$ODH_BASE_IMAGE}"
  RHEL_VERSION=""
fi

echo "Lockfile generator base image: $BASE_IMAGE"
if [[ -n "$RHEL_VERSION" ]]; then
  echo "RHEL releasever: $RHEL_VERSION (subscription)"
else
  echo "Using public repos from rpms.in.yaml (no subscription)"
fi

# First build the image, so we can run rpm-lockfile-prototype inside it
CACHE_ARGS=()
if [[ -n "${CONTAINER_BUILD_CACHE_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  CACHE_ARGS=($CONTAINER_BUILD_CACHE_ARGS)
fi

if podman image exists localhost/notebook-rpm-lockfile:latest 2>/dev/null; then
  echo "--- Reusing existing Lockfile Generator Image (rm it to rebuild after changing base/subscription) ---"
else
  echo "--- Building Lockfile Generator Image ---"
  podman build \
      -f "$SCRIPTS_PATH/Dockerfile.rpm-lockfile" \
      --platform=linux/x86_64 \
      --build-arg RHEL_VERSION="$RHEL_VERSION" \
      --build-arg BASE_IMAGE="$BASE_IMAGE" \
      --build-arg ACTIVATION_KEY="$ACTIVATION_KEY" \
      --build-arg ORG="$ORG" \
      ${CACHE_ARGS+"${CACHE_ARGS[@]}"} \
      -t notebook-rpm-lockfile "$SCRIPTS_PATH"
fi

# Second run rpm-lockfile-prototype to generate the lockfile
CONTAINER_WORKDIR="/workspace/$SCRIPTS_PATH"
echo "--- Generating Lockfile using rpm-lockfile-prototype --"
podman_run_args=(--rm -i)
[[ -t 1 ]] && podman_run_args+=(-t)
podman run "${podman_run_args[@]}" \
    -v "$(pwd):/workspace" \
    --platform=linux/x86_64 \
    -w "$CONTAINER_WORKDIR" \
    -e PREFETCH_INPUT_DIR="$PREFETCH_DIR" \
    -e RHEL_VERSION="$RHEL_VERSION" \
    localhost/notebook-rpm-lockfile:latest \
    ./helpers/rpm-lockfile-generate.sh

# Download RPMs and create repository metadata (for dnf)
if [[ "$DO_DOWNLOAD" == true ]]; then
  LOCKFILE="$PREFETCH_DIR/rpms.lock.yaml"
  if [[ ! -f "$LOCKFILE" ]]; then
    error_exit "Lockfile not found at $LOCKFILE (required for --download)."
  fi

  HERMETO_ARGS=(--prefetch-dir "$PREFETCH_DIR")
  if [[ -n "$ACTIVATION_KEY" ]] && [[ -n "$ORG" ]]; then
    HERMETO_ARGS+=(--activation-key "$ACTIVATION_KEY" --org "$ORG")
  fi
  "$SCRIPTS_PATH/helpers/hermeto-fetch-rpm.sh" "${HERMETO_ARGS[@]}"
fi
