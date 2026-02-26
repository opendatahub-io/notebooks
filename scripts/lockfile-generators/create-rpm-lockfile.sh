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
ODH_BASE_IMAGE="quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest"

RPM_INPUT=""
ACTIVATION_KEY=""
ORG=""
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

  # Downstream (RHDS) with RHEL subscription:
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
    --download)          DO_DOWNLOAD=true;   shift ;;
    *)                   error_exit "Unknown argument: '$1'" ;;
  esac
done

# --- Required argument check ---
[[ -z "$RPM_INPUT" ]] && error_exit "--rpm-input is required. E.g. --rpm-input codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.in.yaml"
[[ -f "$RPM_INPUT" ]] || error_exit "rpms.in.yaml not found at: $RPM_INPUT"

# Derive the prefetch-input directory from the rpms.in.yaml path
PREFETCH_DIR="$(dirname "$RPM_INPUT")"

# --- Base image and RHEL version ---
# With activation key + org: use UBI9 and pin release. Otherwise: use ODH base image (CentOS Stream), no releasever.
if [[ -n "$ACTIVATION_KEY" ]] && [[ -n "$ORG" ]]; then
  BASE_IMAGE="$UBI9_IMAGE"
  RHEL_VERSION="9.6"
else
  BASE_IMAGE="$ODH_BASE_IMAGE"
  RHEL_VERSION=""
fi

# First build the image, so we can run rpm-lockfile-prototype inside it
echo "--- Building Lockfile Generator Image ---"
podman build \
    -f "$SCRIPTS_PATH/Dockerfile.rpm-lockfile" \
    --platform linux/x86_64 \
    --build-arg RHEL_VERSION="$RHEL_VERSION" \
    --build-arg BASE_IMAGE="$BASE_IMAGE" \
    --build-arg ACTIVATION_KEY="$ACTIVATION_KEY" \
    --build-arg ORG="$ORG" \
    -t notebook-rpm-lockfile "$SCRIPTS_PATH"

# Second run rpm-lockfile-prototype to generate the lockfile
echo "--- Generating Lockfile using rpm-lockfile-prototype --"
TTY_FLAG=""
[ -t 1 ] && TTY_FLAG="-t"
podman run --rm -i $TTY_FLAG \
    -v "$(pwd):/workspace" \
    --platform linux/x86_64 \
    localhost/notebook-rpm-lockfile:latest \
    sh -c "cd /workspace/$SCRIPTS_PATH && ./helpers/rpm-lockfile-generate.sh prefetch-input=$PREFETCH_DIR"

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
