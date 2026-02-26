#!/usr/bin/env bash
set -euo pipefail

# hermeto-fetch-rpm.sh — Download RPMs using Hermeto and create repo metadata.
#
# Uses hermetoproject/hermeto in a container to fetch all RPMs listed in
# rpms.lock.yaml into cachi2/output/deps/rpm/ and generate repo metadata.
# When RHEL entitlement certs are needed (for cdn.redhat.com), extracts them
# from the notebook-rpm-lockfile container image.
#
# This is an alternative to helpers/download-rpms.sh (which uses wget directly).
# Hermeto handles SSL cert-based auth natively, making it the better choice
# when downloading from RHEL repos that require entitlement.

HERMETO_IMAGE="ghcr.io/hermetoproject/hermeto:0.46.2"
HERMETO_OUTPUT="./cachi2/output"

PREFETCH_DIR=""
ACTIVATION_KEY=""
ORG=""

show_help() {
  cat << 'EOF'
Usage: helpers/hermeto-fetch-rpm.sh [OPTIONS]

Download RPMs from rpms.lock.yaml using Hermeto and create repo metadata.

Options:
  --prefetch-dir DIR     Directory containing rpms.lock.yaml (required)
  --activation-key KEY   Red Hat activation key (enables RHEL cert extraction)
  --org ORG              Red Hat organization ID (enables RHEL cert extraction)
  --help                 Show this help
EOF
}

error_exit() {
  echo "Error: $1" >&2
  echo "Use --help for usage information." >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefetch-dir)    [[ $# -ge 2 ]] || error_exit "--prefetch-dir requires a value"
                       PREFETCH_DIR="$2"; shift 2 ;;
    --activation-key)  [[ $# -ge 2 ]] || error_exit "--activation-key requires a value"
                       ACTIVATION_KEY="$2"; shift 2 ;;
    --org)             [[ $# -ge 2 ]] || error_exit "--org requires a value"
                       ORG="$2"; shift 2 ;;
    -h|--help)         show_help; exit 0 ;;
    *)                 error_exit "Unknown argument: '$1'" ;;
  esac
done

[[ -z "$PREFETCH_DIR" ]] && error_exit "--prefetch-dir is required."
[[ -f "$PREFETCH_DIR/rpms.lock.yaml" ]] || error_exit "rpms.lock.yaml not found in $PREFETCH_DIR"

# Build the hermeto JSON input — add SSL config when using RHEL subscription
# so hermeto can authenticate to cdn.redhat.com for entitled content.
HERMETO_JSON='{"type": "rpm"}'
CDN_CERT_DIR=""

if [[ -n "$ACTIVATION_KEY" ]] && [[ -n "$ORG" ]]; then
  echo "--- Extracting entitlement certs for hermeto ---"
  CDN_CERT_DIR=$(mktemp -d)
  podman run --rm --platform=linux/x86_64 \
    localhost/notebook-rpm-lockfile:latest \
    sh -c 'tar -cf - /etc/pki/entitlement/ /etc/rhsm/ca/ 2>/dev/null' \
    | tar -xf - -C "$CDN_CERT_DIR" 2>/dev/null || true

  CDN_CERT=$(find "$CDN_CERT_DIR/etc/pki/entitlement" -name '*.pem' ! -name '*-key.pem' 2>/dev/null | head -1)
  CDN_KEY=$(find "$CDN_CERT_DIR/etc/pki/entitlement" -name '*-key.pem' 2>/dev/null | head -1)
  CDN_CA="$CDN_CERT_DIR/etc/rhsm/ca/redhat-uep.pem"

  if [[ -z "$CDN_CERT" ]] || [[ -z "$CDN_KEY" ]]; then
    rm -rf "$CDN_CERT_DIR"
    error_exit "Failed to extract entitlement certs from notebook-rpm-lockfile image. Ensure subscription-manager registration succeeded."
  fi

  # Remap paths to container mount point
  C_CERT="/certs${CDN_CERT#"$CDN_CERT_DIR"}"
  C_KEY="/certs${CDN_KEY#"$CDN_CERT_DIR"}"
  C_CA="/certs${CDN_CA#"$CDN_CERT_DIR"}"

  HERMETO_JSON="{\"type\": \"rpm\", \"options\": {\"ssl\": {\"client_cert\": \"$C_CERT\", \"client_key\": \"$C_KEY\", \"ca_bundle\": \"$C_CA\"}}}"
fi

# Hermeto's fetch-deps wipes its output directory, so we use a staging dir
# to avoid destroying existing content (pip wheels, npm packages, generic
# artifacts) that other scripts placed in cachi2/output/deps/.
HERMETO_STAGING=$(mktemp -d)
trap 'rm -rf "$HERMETO_STAGING" ${CDN_CERT_DIR:+"$CDN_CERT_DIR"}' EXIT

echo "--- Downloading RPMs via hermeto (staging: $HERMETO_STAGING) ---"
podman run --rm \
  -v "$(pwd)/$PREFETCH_DIR:/source:z" \
  -v "$HERMETO_STAGING:/output:z" \
  ${CDN_CERT_DIR:+-v "$CDN_CERT_DIR:/certs:ro,z"} \
  "$HERMETO_IMAGE" \
  fetch-deps --source /source --output /output "$HERMETO_JSON"

echo "--- Generating repo metadata via hermeto ---"
podman run --rm \
  -v "$HERMETO_STAGING:/output:z" \
  "$HERMETO_IMAGE" \
  inject-files /output --for-output-dir /cachi2/output

# Fix ownership: hermeto runs as root inside the container; on rootful podman
# (e.g. GHA runners) the created files are owned by root and the host user
# cannot modify or move them.  Reclaim ownership if needed.
if ! test -w "$HERMETO_STAGING/deps/rpm" 2>/dev/null; then
  echo "--- Fixing file ownership (rootful podman detected) ---"
  sudo chown -R "$(id -u):$(id -g)" "$HERMETO_STAGING" 2>/dev/null || true
fi

# Hermeto's generated repo files lack module_hotfixes, which causes DNF's
# modular filtering to block packages (e.g. nodejs-devel) when the base image
# has a default module stream enabled. Inject module_hotfixes=1 into every
# repo section so LOCAL_BUILD Dockerfiles work without extra sed hacks.
find "$HERMETO_STAGING/deps/rpm" -name '*.repo' -exec \
  perl -pi -e '$_ .= "module_hotfixes=1\n" if /^\[/' {} +

# Merge RPM output into the real cachi2/output without wiping other dep types.
mkdir -p "$HERMETO_OUTPUT/deps"
rm -rf "$HERMETO_OUTPUT/deps/rpm"
mv "$HERMETO_STAGING/deps/rpm" "$HERMETO_OUTPUT/deps/rpm"
cp -f "$HERMETO_STAGING/bom.json" "$HERMETO_OUTPUT/bom.json"
cp -f "$HERMETO_STAGING/.build-config.json" "$HERMETO_OUTPUT/.build-config.json"

echo "Finished! RPMs are located in $HERMETO_OUTPUT/deps/rpm"
