#!/usr/bin/env bash
set -euo pipefail

# prefetch-all.sh — Download all hermetic build dependencies for a component.
#
# Hermetic builds (Konflux/Tekton and local) require every dependency to be
# prefetched so the Dockerfile can build fully offline (no network access).
# This script orchestrates downloading all dependency types via a single
# Hermeto invocation, matching the Konflux pipeline pattern.
#
# Dependency types (all fetched by Hermeto in one call):
#   - generic: GPG keys, tarballs, VS Code .vsix (from artifacts.lock.yaml)
#   - pip:     Python wheels (from requirements.<flavor>.txt)
#   - npm:     Node packages (from package-lock.json via Tekton prefetch-input)
#   - rpm:     System packages (from rpms.lock.yaml)
#   - gomod:   Go modules (from go.mod/go.sum via Tekton prefetch-input)
#
# Design: Inspired by the Konflux prefetch-dependencies task, which passes
# all ecosystem specs as a single JSON array to one `hermeto fetch-deps` call:
#   https://github.com/konflux-ci/build-definitions/blob/main/task/prefetch-dependencies-oci-ta/0.3/prefetch-dependencies-oci-ta.yaml
# The Go wrapper is `konflux-build-cli`:
#   https://github.com/konflux-ci/konflux-build-cli/blob/main/pkg/commands/prefetch_dependencies/main.go
#
# Previously, this script called separate downloaders per ecosystem (wget for
# pip, download-npm.sh for npm, hermeto-fetch-rpm.sh for rpm, create-go-lockfile.sh
# for gomod). Each hermeto call mounted the repo root and internally copied the
# entire source tree — including accumulated cachi2/output/ from prior steps.
# This caused disk duplication that grew with each call (#3641).
#
# The single-invocation approach eliminates this: one source copy, one output
# dir, one unified bom.json, parallel downloads across all ecosystems.
#
# Usage:
#   # Upstream ODH (CentOS Stream base, no subscription):
#   ./scripts/lockfile-generators/prefetch-all.sh \
#       --component-dir codeserver/ubi9-python-3.12
#
#   # Downstream RHDS (RHEL base, requires subscription for RPMs):
#   ./scripts/lockfile-generators/prefetch-all.sh \
#       --component-dir codeserver/ubi9-python-3.12 --rhds \
#       --activation-key my-key --org my-org
#
#   # Custom flavor (e.g. cuda, rocm):
#   ./scripts/lockfile-generators/prefetch-all.sh \
#       --component-dir codeserver/ubi9-python-3.12 --flavor cuda
#
# Prerequisites: jq, podman, yq (optional, for npm/gomod auto-detection)

# shellcheck source-path=SCRIPTDIR
source "$(dirname "$0")/helpers/hermeto-common.sh"

SCRIPTS_PATH="scripts/lockfile-generators"

COMPONENT_DIR=""
VARIANT="odh"       # "odh" = upstream (CentOS Stream), "rhds" = downstream (RHEL)
FLAVOR="cpu"        # selects which pylock/requirements files to use (cpu, cuda, rocm)
ACTIVATION_KEY=""
ORG=""

show_help() {
  cat << 'HELPEOF'
Usage: scripts/lockfile-generators/prefetch-all.sh [OPTIONS]

Download all hermetic build dependencies into cachi2/output/deps/.

Options:
  --component-dir DIR     Component directory (required)
                          e.g. codeserver/ubi9-python-3.12
  --rhds                  Use downstream (RHDS) lockfiles instead of upstream (ODH)
  --flavor NAME           Lock file flavor (default: cpu)
  --activation-key KEY    Red Hat activation key for RHEL RPMs (optional)
  --org ORG               Red Hat organization ID for RHEL RPMs (optional)
  -h, --help              Show this help

Environment variables (preferred in CI to avoid leaking secrets):
  SUBSCRIPTION_ACTIVATION_KEY   Same as --activation-key
  SUBSCRIPTION_ORG              Same as --org
HELPEOF
}

error_exit() {
  echo "Error: $1" >&2
  exit 1
}

# find_tekton_yaml COMPONENT_DIR VARIANT
# Finds .tekton/*pull-request*.yaml files that build this component for the
# given variant by matching the pipeline's dockerfile param. Requires yq;
# must be run from repo root.
#
#   ODH (upstream):  dockerfile is COMPONENT_DIR/Dockerfile.* (excludes Dockerfile.konflux.*).
#   RHDS (downstream): dockerfile is COMPONENT_DIR/Dockerfile.konflux.*
# Outputs matching file paths one per line. Returns 0 if at least one match.
find_tekton_yaml() {
  local comp_dir="$1"
  local variant="$2"
  local found=0
  local f dockerfile_path
  if [[ ! -d ".tekton" ]] || ! command -v yq &>/dev/null; then
    return 1
  fi
  for f in .tekton/*pull-request*.yaml; do
    [[ -f "$f" ]] || continue
    dockerfile_path=$(yq -r '.spec.params[] | select(.name == "dockerfile") | .value' "$f" 2>/dev/null)
    [[ -n "$dockerfile_path" ]] || continue
    if [[ "$variant" == "odh" ]]; then
      if [[ "$dockerfile_path" == "$comp_dir/Dockerfile."* ]] && [[ "$dockerfile_path" != "$comp_dir/Dockerfile.konflux."* ]]; then
        echo "$f"
        found=1
      fi
    elif [[ "$variant" == "rhds" ]]; then
      if [[ "$dockerfile_path" == "$comp_dir/Dockerfile.konflux."* ]]; then
        echo "$f"
        found=1
      fi
    fi
  done
  [[ $found -eq 1 ]]
}

# Must run from the repo root because all paths (lockfiles, Tekton YAMLs,
# Dockerfiles) are relative to it.
if [[ ! -d "$SCRIPTS_PATH" ]]; then
  error_exit "This script must be run from the repository root."
fi

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --component-dir)     [[ $# -ge 2 ]] || error_exit "--component-dir requires a value"
                         COMPONENT_DIR="$2"; shift 2 ;;
    --rhds)              VARIANT="rhds"; shift ;;
    --flavor)            [[ $# -ge 2 ]] || error_exit "--flavor requires a value"
                         FLAVOR="$2"; shift 2 ;;
    --activation-key)    [[ $# -ge 2 ]] || error_exit "--activation-key requires a value"
                         ACTIVATION_KEY="$2"; shift 2 ;;
    --org)               [[ $# -ge 2 ]] || error_exit "--org requires a value"
                         ORG="$2"; shift 2 ;;
    -h|--help)           show_help; exit 0 ;;
    *)                   error_exit "Unknown argument: '$1'" ;;
  esac
done

[[ -z "$COMPONENT_DIR" ]] && error_exit "--component-dir is required."
[[ -d "$COMPONENT_DIR" ]] || error_exit "Component directory not found: $COMPONENT_DIR"

# CLI args take priority; fall back to env vars so GHA can pass secrets
# without exposing them on the command line.
ACTIVATION_KEY="${ACTIVATION_KEY:-${SUBSCRIPTION_ACTIVATION_KEY:-}}"
ORG="${ORG:-${SUBSCRIPTION_ORG:-}}"

if [[ -n "$ACTIVATION_KEY" && -z "$ORG" ]] || [[ -z "$ACTIVATION_KEY" && -n "$ORG" ]]; then
  error_exit "--activation-key/--org (or SUBSCRIPTION_ACTIVATION_KEY/SUBSCRIPTION_ORG env vars) must be provided together."
fi

if [[ -n "$ACTIVATION_KEY" ]]; then
  export SUBSCRIPTION_ACTIVATION_KEY="$ACTIVATION_KEY"
  export SUBSCRIPTION_ORG="$ORG"
fi

# --- Variant selection ---
# Each component uses COMPONENT_DIR/prefetch-input when present; Jupyter
# notebook dirs that share upstream RPM/generic locks use repo-root
# prefetch-input/.
PREFETCH_DIR="$COMPONENT_DIR/prefetch-input"
if [[ ! -d "$PREFETCH_DIR" ]] && [[ -d prefetch-input ]]; then
  if grep -rq 'prefetch-input/' "$COMPONENT_DIR"/Dockerfile* 2>/dev/null; then
    PREFETCH_DIR="prefetch-input"
  fi
fi
if [[ -z "${CI:-}" ]] && [[ "$VARIANT" == "odh" ]] && [[ -n "$ACTIVATION_KEY" ]] && [[ -d "$PREFETCH_DIR/rhds" ]]; then
  echo "Subscription credentials provided — switching to RHDS variant"
  VARIANT="rhds"
fi

VARIANT_DIR="$PREFETCH_DIR/$VARIANT"
if [[ ! -d "$VARIANT_DIR" ]]; then
  echo "Note: Variant directory not found ($VARIANT_DIR). Generic and RPM will be skipped."
fi

echo "=============================================="
echo " prefetch-all.sh"
echo "  component : $COMPONENT_DIR"
echo "  variant   : $VARIANT"
echo "  flavor    : $FLAVOR"
echo "  prefetch  : $PREFETCH_DIR"
echo "  lockfiles : $VARIANT_DIR"
echo "=============================================="
echo ""

# =========================================================================
# Phase 1: Ensure lockfiles exist (generation only, no downloads)
#
# Hermeto downloads from existing lockfiles. If any are missing, generate
# them first. In normal CI, all lockfiles are committed to the repo.
# =========================================================================
echo "--- Phase 1: Lockfile generation (if needed) ---"

# Pip: generate requirements.<flavor>.txt if not present
REQUIREMENTS_FILE="$COMPONENT_DIR/requirements.${FLAVOR}.txt"
if [[ -f "$COMPONENT_DIR/pyproject.toml" ]] && [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  echo "Generating $REQUIREMENTS_FILE from pyproject.toml..."
  "$SCRIPTS_PATH/create-requirements-lockfile.sh" \
      --pyproject-toml "$COMPONENT_DIR/pyproject.toml" --flavor "$FLAVOR"
fi

# RPM: generate rpms.lock.yaml if rpms.in.yaml exists but lockfile doesn't
RPM_INPUT="$VARIANT_DIR/rpms.in.yaml"
RPM_LOCKFILE="$VARIANT_DIR/rpms.lock.yaml"
if [[ -f "$RPM_INPUT" ]] && [[ ! -f "$RPM_LOCKFILE" ]]; then
  echo "Generating $RPM_LOCKFILE from $RPM_INPUT..."
  "$SCRIPTS_PATH/create-rpm-lockfile.sh" --rpm-input "$RPM_INPUT"
fi

# Generic: artifacts.lock.yaml should already be committed.
# If missing, generate from artifacts.in.yaml (downloads files to compute checksums).
ARTIFACTS_INPUT="$VARIANT_DIR/artifacts.in.yaml"
ARTIFACTS_LOCKFILE="$VARIANT_DIR/artifacts.lock.yaml"
if [[ -f "$ARTIFACTS_INPUT" ]] && [[ ! -f "$ARTIFACTS_LOCKFILE" ]]; then
  echo "Generating $ARTIFACTS_LOCKFILE from $ARTIFACTS_INPUT..."
  python3 "$SCRIPTS_PATH/create-artifact-lockfile.py" \
      --artifact-input "$ARTIFACTS_INPUT"
fi

echo ""

# =========================================================================
# Phase 2: Build Hermeto input JSON
#
# Construct a JSON array matching the prefetch-input format used by the
# Konflux .tekton/*.yaml files. Each entry specifies the ecosystem type
# and path to its lockfile/source.
# =========================================================================
echo "--- Phase 2: Building Hermeto input ---"

HERMETO_INPUT='[]'
ECOSYSTEMS_INCLUDED=""

# Generic artifacts (from artifacts.lock.yaml)
if [[ -f "$ARTIFACTS_LOCKFILE" ]]; then
  HERMETO_INPUT=$(echo "$HERMETO_INPUT" | jq --arg path "$VARIANT_DIR" \
    '. + [{"type":"generic","path":$path}]')
  ECOSYSTEMS_INCLUDED+="generic "
  echo "  + generic: $ARTIFACTS_LOCKFILE"
fi

# Pip wheels (from requirements.<flavor>.txt)
if [[ -f "$REQUIREMENTS_FILE" ]]; then
  # Use BUILD_ARCH (e.g. linux/s390x) when set (GHA cross-builds via QEMU),
  # otherwise fall back to the host architecture.
  if [[ -n "${BUILD_ARCH:-}" ]]; then
    case "${BUILD_ARCH##*/}" in
      amd64) ARCH="x86_64" ;;
      arm64) ARCH="aarch64" ;;
      *) ARCH="${BUILD_ARCH##*/}" ;;
    esac
  else
    ARCH=$(uname -m)
  fi
  # Only use binary arch filter for x86_64/aarch64. For ppc64le/s390x, many
  # packages have environment markers like `platform_machine != 'ppc64le'` that
  # exclude them from those arches. Hermeto doesn't respect these markers during
  # binary filtering — it tries to find arch-specific wheels that don't exist,
  # causing PackageRejected errors (e.g. bcrypt on ppc64le).
  # Without binary filter, hermeto downloads sdists + any-arch wheels only.
  PIP_ENTRY=$(jq -n --arg path "$COMPONENT_DIR" --arg req "requirements.${FLAVOR}.txt" \
    '{"type":"pip","path":$path,"requirements_files":[$req]}')
  if [[ "$ARCH" == "x86_64" || "$ARCH" == "aarch64" ]]; then
    PIP_ENTRY=$(echo "$PIP_ENTRY" | jq --arg arch "$ARCH" '. + {"binary":{"arch":$arch,"os":"linux"}}')
  fi
  HERMETO_INPUT=$(echo "$HERMETO_INPUT" | jq --argjson entry "$PIP_ENTRY" '. + [$entry]')
  ECOSYSTEMS_INCLUDED+="pip "
  echo "  + pip: $REQUIREMENTS_FILE (arch=$ARCH, binary_filter=$([[ "$ARCH" == "x86_64" || "$ARCH" == "aarch64" ]] && echo yes || echo no))"
fi

# NPM and GoMod (auto-detect from Tekton prefetch-input)
tekton_file=""
if [[ -d ".tekton" ]] && command -v yq &>/dev/null; then
  # Prefer the active variant's Tekton file; fall back to the other variant.
  tekton_file=$(find_tekton_yaml "$COMPONENT_DIR" "$VARIANT" 2>/dev/null | head -1) || true
  if [[ -z "$tekton_file" ]]; then
    fallback_variant=$([[ "$VARIANT" == "rhds" ]] && echo "odh" || echo "rhds")
    tekton_file=$(find_tekton_yaml "$COMPONENT_DIR" "$fallback_variant" 2>/dev/null | head -1) || true
  fi
fi

if [[ -n "$tekton_file" ]]; then
  echo "  Tekton file: $tekton_file"

  # Extract npm entries from Tekton prefetch-input
  npm_entries=$(yq eval -o=json '
    .spec.params[]
    | select(.name == "prefetch-input")
    | .value[]
    | select(.type == "npm")
  ' "$tekton_file" 2>/dev/null) || true
  if [[ -n "$npm_entries" ]]; then
    # Add each npm entry to the combined input
    while IFS= read -r entry; do
      [[ -z "$entry" ]] && continue
      HERMETO_INPUT=$(echo "$HERMETO_INPUT" | jq --argjson entry "$entry" '. + [$entry]')
    done < <(echo "$npm_entries" | jq -c '.')
    ECOSYSTEMS_INCLUDED+="npm "
    echo "  + npm: from Tekton prefetch-input"
  fi

  # Extract gomod entries from Tekton prefetch-input
  gomod_entries=$(yq eval -o=json '
    .spec.params[]
    | select(.name == "prefetch-input")
    | .value[]
    | select(.type == "gomod")
  ' "$tekton_file" 2>/dev/null) || true
  if [[ -n "$gomod_entries" ]]; then
    while IFS= read -r entry; do
      [[ -z "$entry" ]] && continue
      HERMETO_INPUT=$(echo "$HERMETO_INPUT" | jq --argjson entry "$entry" '. + [$entry]')
    done < <(echo "$gomod_entries" | jq -c '.')
    ECOSYSTEMS_INCLUDED+="gomod "
    echo "  + gomod: from Tekton prefetch-input"
  fi
else
  echo "  No Tekton file found — npm and gomod will be skipped"
fi

# RPM (from rpms.lock.yaml)
if [[ -f "$RPM_LOCKFILE" ]]; then
  HERMETO_INPUT=$(echo "$HERMETO_INPUT" | jq --arg path "$VARIANT_DIR" \
    '. + [{"type":"rpm","path":$path}]')
  ECOSYSTEMS_INCLUDED+="rpm "
  echo "  + rpm: $RPM_LOCKFILE"
fi

INPUT_COUNT=$(echo "$HERMETO_INPUT" | jq 'length')
if [[ "$INPUT_COUNT" -eq 0 ]]; then
  echo ""
  echo "No lockfiles found — nothing to prefetch."
  exit 0
fi

echo ""
echo "  Hermeto input ($INPUT_COUNT entries): $ECOSYSTEMS_INCLUDED"
echo "$HERMETO_INPUT" | jq -c '.[]' | while read -r entry; do
  echo "    $(echo "$entry" | jq -c '{type,path}')"
done
echo ""

# =========================================================================
# Phase 3: Run Hermeto (single invocation)
#
# One podman run call with all ecosystem specs. Hermeto handles parallel
# downloads internally via asyncio.
# =========================================================================
echo "--- Phase 3: Hermeto fetch-deps ---"

# Clear any prior output to avoid hermeto copying it during source backup.
# Hermeto copies the entire /source/ tree internally (resolver.py:58); with an
# empty cachi2/output/ the copy is just the repo source (~1 GB).
if [[ -d "$HERMETO_OUTPUT" ]]; then
  echo "Clearing prior $HERMETO_OUTPUT..."
  rm -rf "$HERMETO_OUTPUT"
fi
mkdir -p "$HERMETO_OUTPUT"

# Staging directory: prefer LVM path on GHA runners (root fs has limited space).
# Falls back to /tmp on non-GHA systems.
_LVM_TMP="${HOME}/.local/share/containers/tmp"
mkdir -p "$_LVM_TMP" 2>/dev/null || true
HERMETO_STAGING=$(mktemp -d --tmpdir="$_LVM_TMP" 2>/dev/null || mktemp -d)
# Hermeto's RPM handler creates root-owned directories even with --userns=keep-id.
# podman unshare maps root back to the current user for cleanup.
CDN_CERT_DIR=""
# Hermeto runs as root in the container; output files are root-owned.
# podman unshare maps root to the current user for cleanup.
trap 'podman unshare rm -rf "$HERMETO_STAGING" || rm -rf "$HERMETO_STAGING"; rm -rf "${CDN_CERT_DIR:-}"' EXIT

# Build podman volume mounts.
# Note: we do NOT use --userns=keep-id here because hermeto's RPM handler
# needs real root to read RHSM entitlement certs mounted from the host.
# Root-owned output files are cleaned up via `podman unshare rm -rf` in the
# EXIT trap.
PODMAN_MOUNTS=(
  -v "$(pwd):/source:z"
  -v "$HERMETO_STAGING:/output:z"
)

# Mount RHSM entitlement certs if present (created by GHA "Add subscriptions"
# step in build-notebooks-TEMPLATE.yaml). Hermeto needs both the entitlement
# PEMs and the RHSM CA cert (redhat-uep.pem) to authenticate to cdn.redhat.com.
# See hermeto-fetch-rpm.sh for the original cert handling logic.
# Konflux has its own registerRHSM() in Go:
#   https://github.com/konflux-ci/konflux-build-cli/blob/main/pkg/commands/prefetch_dependencies/main.go
if ls entitlement/*.pem &>/dev/null; then
  CDN_CERT_DIR=$(mktemp -d)
  mkdir -p "$CDN_CERT_DIR/etc/pki/entitlement" "$CDN_CERT_DIR/etc/rhsm/ca"
  cp entitlement/*.pem "$CDN_CERT_DIR/etc/pki/entitlement/" 2>/dev/null || true
  # UBI9 ships the RHSM CA cert even without registration.
  podman run --rm registry.access.redhat.com/ubi9/ubi \
    cat /etc/rhsm/ca/redhat-uep.pem \
    > "$CDN_CERT_DIR/etc/rhsm/ca/redhat-uep.pem" 2>/dev/null || true
  PODMAN_MOUNTS+=(-v "$CDN_CERT_DIR:/certs:ro,z")
  echo "  Mounting RHSM entitlement certs (with CA)"
fi

# Concurrency: hermeto default is 5 (conservative).
# DNF uses max_parallel_downloads=10 in aipcc.sh.
# uv saturates network by default on GHA runners.
# 20 is a pragmatic middle ground for parallel wheel/RPM/npm downloads.
CONCURRENCY="${HERMETO_RUNTIME__CONCURRENCY_LIMIT:-20}"

echo "  Image: $HERMETO_IMAGE"
echo "  Concurrency: $CONCURRENCY"
echo "  Staging: $HERMETO_STAGING"
echo ""

podman run --rm \
  "${PODMAN_MOUNTS[@]}" \
  -e "HERMETO_RUNTIME__CONCURRENCY_LIMIT=$CONCURRENCY" \
  "$HERMETO_IMAGE" \
  fetch-deps \
    --source /source \
    --output /output \
    "$HERMETO_INPUT"

echo ""
echo "Hermeto fetch-deps completed."

# =========================================================================
# Phase 4: Merge output and generate env files
#
# Hermeto writes to the staging dir. Copy results to the shared cachi2/output/
# tree, then run inject-files to generate DNF repo metadata.
# =========================================================================
echo "--- Phase 4: Merge and inject ---"

# Fix ownership — hermeto runs as root inside the container.
podman unshare chown -R "$(id -u):$(id -g)" "$HERMETO_STAGING" 2>/dev/null || \
  sudo chown -R "$(id -u):$(id -g)" "$HERMETO_STAGING" 2>/dev/null || true

# Move entire staging output to shared cachi2/output/.
# With a single hermeto invocation, staging has the complete output —
# no need to merge ecosystem-by-ecosystem.
rm -rf "$HERMETO_OUTPUT"
mv "$HERMETO_STAGING" "$HERMETO_OUTPUT"
# Clear the trap since staging no longer exists
trap - EXIT

# Generate DNF repo metadata and env files via hermeto inject-files
# (creates repos.d/ with .repo files pointing to downloaded RPMs)
if [[ -d "$HERMETO_OUTPUT/deps/rpm" ]]; then
  echo "  Running hermeto inject-files for RPM repo metadata..."
  podman run --rm \
    -v "$HERMETO_OUTPUT:/output:z" \
    "$HERMETO_IMAGE" \
    inject-files /output --for-output-dir /cachi2/output
fi

echo ""

# =========================================================================
# Summary
# =========================================================================
echo "=============================================="
echo " prefetch-all.sh complete"
echo "  component  : $COMPONENT_DIR"
echo "  variant    : $VARIANT"
echo "  flavor     : $FLAVOR"
echo "  ecosystems : $ECOSYSTEMS_INCLUDED"
echo "  tekton file: ${tekton_file:-none}"
echo ""
echo " Dependencies are in: $HERMETO_OUTPUT/deps/"
if [[ -d "$HERMETO_OUTPUT/deps" ]]; then
  echo ""
  du -sh "$HERMETO_OUTPUT/deps/"*/ 2>/dev/null || true
fi
if [[ -f "$HERMETO_OUTPUT/bom.json" ]]; then
  echo ""
  echo " SBOM: $HERMETO_OUTPUT/bom.json"
  echo "   Components: $(jq '.components | length' "$HERMETO_OUTPUT/bom.json" 2>/dev/null || echo '?')"
fi
echo ""
echo " Next: run 'make <target>' — it will auto-detect cachi2/output/"
echo "       and mount it automatically."
echo "=============================================="
