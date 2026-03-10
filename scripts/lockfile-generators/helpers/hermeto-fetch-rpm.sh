#!/usr/bin/env bash
set -euo pipefail

# hermeto-fetch-rpm.sh — Download RPMs using Hermeto and create repo metadata.
#
# Fetches all RPMs listed in rpms.lock.yaml into cachi2/output/deps/rpm/
# and generates DNF repo metadata so Dockerfiles can `dnf install` offline.
#
# Hermeto (hermetoproject/hermeto) is a container-based tool that resolves
# RPM URLs from lockfiles and downloads them with optional SSL client-cert
# authentication for cdn.redhat.com (RHEL entitled content).
#
# For RHEL-entitled RPMs, entitlement certs are resolved in this order:
#   1. Auto-detect entitlement/ dir (created by the GHA "Add subscriptions"
#      workflow step, which registers the runner and writes PEM certs there).
#   2. Explicit --cert-dir with pre-extracted PEM files (manual/local use).
#   3. --activation-key + --org — spins up a disposable UBI9 container,
#      registers with subscription-manager, and extracts fresh certs.
#   4. None of the above — no SSL config is added; only public repos
#      (ODH/CentOS Stream) will work.

UBI9_IMAGE="registry.access.redhat.com/ubi9/ubi"
HERMETO_IMAGE="ghcr.io/hermetoproject/hermeto:0.46.2"
HERMETO_OUTPUT="./cachi2/output"

PREFETCH_DIR=""
CERT_DIR=""
ACTIVATION_KEY=""
ORG=""

show_help() {
  cat << 'EOF'
Usage: helpers/hermeto-fetch-rpm.sh [OPTIONS]

Download RPMs from rpms.lock.yaml using Hermeto and create repo metadata.

Options:
  --prefetch-dir DIR     Directory containing rpms.lock.yaml (required)
  --cert-dir DIR         Directory with pre-extracted entitlement PEM files
  --activation-key KEY   Red Hat activation key for RHEL cert extraction
  --org ORG              Red Hat organization ID for RHEL cert extraction
  --help                 Show this help

Environment variables (fallback when CLI args are not provided):
  SUBSCRIPTION_ACTIVATION_KEY   Same as --activation-key
  SUBSCRIPTION_ORG              Same as --org
EOF
}

error_exit() {
  echo "Error: $1" >&2
  exit 1
}

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefetch-dir)    [[ $# -ge 2 ]] || error_exit "--prefetch-dir requires a value"
                       PREFETCH_DIR="$2"; shift 2 ;;
    --cert-dir)        [[ $# -ge 2 ]] || error_exit "--cert-dir requires a value"
                       CERT_DIR="$2"; shift 2 ;;
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

# CLI args take priority; fall back to env vars so GHA can pass secrets
# without exposing them on the command line (GitHub Actions masks env vars
# in logs but command-line args are visible in process listings).
ACTIVATION_KEY="${ACTIVATION_KEY:-${SUBSCRIPTION_ACTIVATION_KEY:-}}"
ORG="${ORG:-${SUBSCRIPTION_ORG:-}}"

# The GHA "Add subscriptions" step (in build-notebooks-TEMPLATE.yaml) runs
# subscription-manager in a UBI9 container and writes the resulting PEM
# certs to entitlement/.  If that directory exists, use it directly —
# no need to register again.
if [[ -z "$CERT_DIR" ]] && ls entitlement/*.pem &>/dev/null; then
  CERT_DIR="entitlement"
fi

# HERMETO_JSON is the fetch-deps input spec.  For public repos it's just
# {"type": "rpm"}.  When entitlement certs are available, we add SSL
# client_cert/client_key/ca_bundle so hermeto can authenticate to
# cdn.redhat.com for entitled RHEL packages.
HERMETO_JSON='{"type": "rpm"}'
CDN_CERT_DIR=""
REG_LOG=""

# =========================================================================
# Cert path 1: reuse pre-extracted entitlement certs (--cert-dir or
#              auto-detected entitlement/ directory).
#
# Copy the PEM files into a staging dir with the layout hermeto expects
# (/etc/pki/entitlement/ and /etc/rhsm/ca/).  The RHSM CA cert is not
# included in the entitlement dir, so we pull it from the UBI9 image
# (which ships it even without registration).
# =========================================================================
if [[ -n "$CERT_DIR" ]] && [[ -d "$CERT_DIR" ]]; then
  echo "--- Using entitlement certs from $CERT_DIR ---"
  CDN_CERT_DIR=$(mktemp -d)
  mkdir -p "$CDN_CERT_DIR/etc/pki/entitlement" "$CDN_CERT_DIR/etc/rhsm/ca"
  cp "$CERT_DIR"/*.pem "$CDN_CERT_DIR/etc/pki/entitlement/" 2>/dev/null || true

  # UBI9 ships /etc/rhsm/ca/redhat-uep.pem (the RHSM CA) even without
  # registration, so we can extract it with a simple `cat`.
  podman run --rm "$UBI9_IMAGE" \
    cat /etc/rhsm/ca/redhat-uep.pem \
    > "$CDN_CERT_DIR/etc/rhsm/ca/redhat-uep.pem" 2>/dev/null || true

# =========================================================================
# Cert path 2: register with subscription-manager in a disposable container.
#
# Used when no pre-extracted certs are available (e.g. local dev without
# the GHA subscription step).  Spins up a UBI9 container, registers with
# the provided activation key + org, then tars out the resulting certs.
# =========================================================================
elif [[ -n "$ACTIVATION_KEY" ]] && [[ -n "$ORG" ]]; then
  echo "--- Registering subscription and extracting certs ---"
  CDN_CERT_DIR=$(mktemp -d)

  # Why temp file instead of a pipe?  With `set -euo pipefail`, a pipe
  # like `podman run ... | tar -xf -` would abort the entire script if
  # either side fails, before the cert-validation block gets to run and
  # print a useful error message.  Writing to a file + || true ensures
  # graceful fallthrough.
  #
  # Why save/restore xtrace?  The podman command passes secrets via
  # container env vars (-e SM_ORG, -e SM_KEY).  If the caller runs this
  # script with `bash -x`, the expanded values would appear in the trace.
  # Disabling xtrace around this block prevents that.
  CERT_TAR=$(mktemp)
  REG_LOG=$(mktemp)
  _xtrace_was_set=false; [[ $- == *x* ]] && _xtrace_was_set=true
  set +x 2>/dev/null
  podman run --rm \
    -e SM_ORG="$ORG" \
    -e SM_KEY="$ACTIVATION_KEY" \
    "$UBI9_IMAGE" \
    sh -c 'subscription-manager register --force --org="$SM_ORG" --activationkey="$SM_KEY" >/dev/null && tar -cf - /etc/pki/entitlement/ /etc/rhsm/ca/' \
    > "$CERT_TAR" 2>"$REG_LOG" || true
  "$_xtrace_was_set" && set -x
  # --force: the GHA "Add subscriptions" step may have already registered
  # the system, which causes mounts.conf to auto-mount host certs into
  # containers — making the container appear "already registered".
  if [[ -s "$CERT_TAR" ]]; then
    tar -xf "$CERT_TAR" -C "$CDN_CERT_DIR" 2>/dev/null || true
  fi
  rm -f "$CERT_TAR"
fi

# =========================================================================
# Validate extracted certs and build the hermeto SSL config.
#
# Both cert paths produce the same directory layout:
#   CDN_CERT_DIR/etc/pki/entitlement/<id>.pem      (client cert)
#   CDN_CERT_DIR/etc/pki/entitlement/<id>-key.pem  (client key)
#   CDN_CERT_DIR/etc/rhsm/ca/redhat-uep.pem        (CA bundle)
#
# If certs are missing, show any captured registration output (REG_LOG)
# to help diagnose the failure (wrong key? network issue?).
# =========================================================================
if [[ -n "$CDN_CERT_DIR" ]]; then
  CDN_CERT=$(find "$CDN_CERT_DIR/etc/pki/entitlement" -name '*.pem' ! -name '*-key.pem' 2>/dev/null | head -1 || true)
  CDN_KEY=$(find "$CDN_CERT_DIR/etc/pki/entitlement" -name '*-key.pem' 2>/dev/null | head -1 || true)
  CDN_CA="$CDN_CERT_DIR/etc/rhsm/ca/redhat-uep.pem"

  if [[ -z "$CDN_CERT" ]] || [[ -z "$CDN_KEY" ]]; then
    if [[ -n "$REG_LOG" ]] && [[ -s "$REG_LOG" ]]; then
      echo "  Registration output:" >&2
      cat "$REG_LOG" >&2
    fi
    rm -f "$REG_LOG"
    rm -rf "$CDN_CERT_DIR"
    error_exit "Failed to obtain entitlement certs. Check cert-dir, activation key, or org."
  fi
  rm -f "$REG_LOG"

  echo "  cert: $CDN_CERT"
  echo "  key:  $CDN_KEY"
  echo "  CA:   $CDN_CA"

  # Remap host paths to container mount paths — the cert dir is mounted
  # at /certs inside the hermeto container (see -v flag below).
  C_CERT="/certs${CDN_CERT#"$CDN_CERT_DIR"}"
  C_KEY="/certs${CDN_KEY#"$CDN_CERT_DIR"}"
  C_CA="/certs${CDN_CA#"$CDN_CERT_DIR"}"

  HERMETO_JSON=$(jq -n \
    --arg cert "$C_CERT" \
    --arg key  "$C_KEY" \
    --arg ca   "$C_CA" \
    '{"type":"rpm","options":{"ssl":{"client_cert":$cert,"client_key":$key,"ca_bundle":$ca}}}')
fi

# =========================================================================
# Download RPMs and generate repo metadata.
#
# hermeto fetch-deps wipes its --output directory on every run, so we use
# a staging dir to avoid destroying pip/npm/generic artifacts that other
# prefetch steps already placed in cachi2/output/deps/.
# =========================================================================
HERMETO_STAGING=$(mktemp -d)
trap 'rm -rf "$HERMETO_STAGING" ${CDN_CERT_DIR:+"$CDN_CERT_DIR"}' EXIT

echo "--- Downloading RPMs via hermeto ---"
podman run --rm \
  -v "$(pwd)/$PREFETCH_DIR:/source:z" \
  -v "$HERMETO_STAGING:/output:z" \
  ${CDN_CERT_DIR:+-v "$CDN_CERT_DIR:/certs:ro,z"} \
  "$HERMETO_IMAGE" \
  fetch-deps --source /source --output /output "$HERMETO_JSON"

# inject-files generates DNF .repo files pointing at the downloaded RPMs,
# so the Dockerfile can `dnf install` from the local repo.
echo "--- Generating repo metadata ---"
podman run --rm \
  -v "$HERMETO_STAGING:/output:z" \
  "$HERMETO_IMAGE" \
  inject-files /output --for-output-dir /cachi2/output

# Hermeto runs as root inside the container.  On rootful podman (GHA
# runners), the output files are owned by root:root.  Without this fix,
# the host user cannot move/modify them in later steps.
if ! test -w "$HERMETO_STAGING/deps/rpm" 2>/dev/null; then
  sudo chown -R "$(id -u):$(id -g)" "$HERMETO_STAGING" 2>/dev/null || true
fi

# Hermeto's .repo files lack module_hotfixes=1, which causes DNF's
# modular filtering to block packages (e.g. nodejs-devel) when the base
# image has a default module stream enabled (like nodejs:18 on UBI9).
# Injecting module_hotfixes=1 into every [repo] section disables that
# filtering so all prefetched packages are installable.
find "$HERMETO_STAGING/deps/rpm" -name '*.repo' -exec \
  perl -pi -e '$_ .= "module_hotfixes=1\n" if /^\[/' {} +

# Merge RPM output into the shared cachi2/output/ tree.  Other prefetch
# scripts (pip, npm, generic artifacts) may have already placed their
# output under cachi2/output/deps/, so we only replace the rpm/ subtree.
mkdir -p "$HERMETO_OUTPUT/deps"
rm -rf "$HERMETO_OUTPUT/deps/rpm"
mv "$HERMETO_STAGING/deps/rpm" "$HERMETO_OUTPUT/deps/rpm"
cp -f "$HERMETO_STAGING/bom.json" "$HERMETO_OUTPUT/bom.json"
cp -f "$HERMETO_STAGING/.build-config.json" "$HERMETO_OUTPUT/.build-config.json"

echo "Finished! RPMs are in $HERMETO_OUTPUT/deps/rpm"
