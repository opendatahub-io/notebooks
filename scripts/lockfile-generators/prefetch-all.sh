#!/usr/bin/env bash
set -euo pipefail

# prefetch-all.sh — Download all hermetic build dependencies for a component.
#
# Hermetic builds (Konflux/Tekton and local) require every dependency to be
# prefetched so the Dockerfile can build fully offline (no network access).
# This script orchestrates downloading all four dependency types:
#
#   1. Generic artifacts — GPG keys, nfpm-built RPMs, Node.js headers,
#      Electron binaries (into cachi2/output/deps/generic/).
#   2. Pip wheels — Python packages resolved from pyproject.toml
#      (into cachi2/output/deps/pip/).
#   3. NPM packages — tarballs resolved from package-lock.json files
#      (into cachi2/output/deps/npm/).
#   4. RPMs — system packages resolved from rpms.lock.yaml via Hermeto
#      (into cachi2/output/deps/rpm/).
#
# Each step is skipped if its input file is not present in the component's
# prefetch-input/<variant>/ directory.
#
# After running this script, `make <target>` auto-detects cachi2/output/
# and passes --volume + --build-arg LOCAL_BUILD=true to podman build.
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
# Prerequisites: wget, python3 (with pyyaml), jq, podman, uv

SCRIPTS_PATH="scripts/lockfile-generators"

COMPONENT_DIR=""
VARIANT="odh"       # "odh" = upstream (CentOS Stream), "rhds" = downstream (RHEL)
FLAVOR="cpu"        # selects which pylock/requirements files to use (cpu, cuda, rocm)
TEKTON_FILE=""
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
  --tekton-file FILE      Tekton PipelineRun YAML for npm path discovery
                          (auto-detected from .tekton/ if omitted)
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
    --tekton-file)       [[ $# -ge 2 ]] || error_exit "--tekton-file requires a value"
                         TEKTON_FILE="$2"; shift 2 ;;
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
# without exposing them on the command line.  GitHub Actions masks env var
# values in logs, but command-line args appear in process listings.
ACTIVATION_KEY="${ACTIVATION_KEY:-${SUBSCRIPTION_ACTIVATION_KEY:-}}"
ORG="${ORG:-${SUBSCRIPTION_ORG:-}}"

# Activation key and org must be provided together — one without the other
# is always a mistake (subscription-manager needs both to register).
if [[ -n "$ACTIVATION_KEY" && -z "$ORG" ]] || [[ -z "$ACTIVATION_KEY" && -n "$ORG" ]]; then
  error_exit "--activation-key/--org (or SUBSCRIPTION_ACTIVATION_KEY/SUBSCRIPTION_ORG env vars) must be provided together."
fi

# Export secrets as env vars so child scripts (hermeto-fetch-rpm.sh,
# create-rpm-lockfile.sh) inherit them automatically.  This avoids passing
# secrets as command-line arguments, which would be visible in `ps` output
# and shell traces (`set -x`).
if [[ -n "$ACTIVATION_KEY" ]]; then
  export SUBSCRIPTION_ACTIVATION_KEY="$ACTIVATION_KEY"
  export SUBSCRIPTION_ORG="$ORG"
fi

# --- Variant selection ---
# Each component has prefetch-input/odh/ (upstream, CentOS Stream packages)
# and optionally prefetch-input/rhds/ (downstream, RHEL packages).
# The variant determines which lockfiles are used for all four steps.
#
# In GHA CI, the template passes --rhds explicitly for subscription builds.
# For standalone/local use, auto-detect: if the caller provided subscription
# credentials and the rhds lockfiles exist, switch automatically.
PREFETCH_DIR="$COMPONENT_DIR/prefetch-input"
if [[ "$VARIANT" == "odh" ]] && [[ -n "$ACTIVATION_KEY" ]] && [[ -d "$PREFETCH_DIR/rhds" ]]; then
  echo "Subscription credentials provided — switching to RHDS variant"
  VARIANT="rhds"
fi

VARIANT_DIR="$PREFETCH_DIR/$VARIANT"
[[ -d "$VARIANT_DIR" ]] || error_exit "Variant directory not found: $VARIANT_DIR"

echo "=============================================="
echo " prefetch-all.sh"
echo "  component : $COMPONENT_DIR"
echo "  variant   : $VARIANT"
echo "  flavor    : $FLAVOR"
echo "  prefetch  : $PREFETCH_DIR"
echo "  lockfiles : $VARIANT_DIR"
echo "=============================================="
echo ""

STEPS_RUN=0
STEPS_SKIPPED=0

# =========================================================================
# Step 1: Generic artifacts (create-artifact-lockfile.py)
#
# Downloads non-package artifacts listed in artifacts.in.yaml: GPG keys
# for RPM signature verification, nfpm-packaged RPMs (e.g. code-server),
# Node.js headers for native addons, Electron binaries, etc.
# Output: cachi2/output/deps/generic/
# =========================================================================
ARTIFACTS_INPUT="$VARIANT_DIR/artifacts.in.yaml"
if [[ -f "$ARTIFACTS_INPUT" ]]; then
  echo "=== [1/4] Generic artifacts ==="
  python3 "$SCRIPTS_PATH/create-artifact-lockfile.py" \
      --artifact-input "$ARTIFACTS_INPUT"
  STEPS_RUN=$((STEPS_RUN + 1))
  echo ""
else
  echo "=== [1/4] Generic artifacts — SKIPPED (no $ARTIFACTS_INPUT) ==="
  STEPS_SKIPPED=$((STEPS_SKIPPED + 1))
fi

# =========================================================================
# Step 2: Pip wheels (create-requirements-lockfile.sh --download)
#
# Resolves Python dependencies from pyproject.toml using uv, generates
# pylock.<flavor>.toml + requirements.<flavor>.txt, then downloads all
# wheels.  The --flavor flag selects which optional dependency groups
# to include (e.g. cpu vs cuda have different torch/triton packages).
# Output: cachi2/output/deps/pip/
# =========================================================================
PYPROJECT="$COMPONENT_DIR/pyproject.toml"
if [[ -f "$PYPROJECT" ]]; then
  echo "=== [2/4] Pip wheels ==="
  "$SCRIPTS_PATH/create-requirements-lockfile.sh" \
      --pyproject-toml "$PYPROJECT" --flavor "$FLAVOR" --download
  STEPS_RUN=$((STEPS_RUN + 1))
  echo ""
else
  echo "=== [2/4] Pip wheels — SKIPPED (no $PYPROJECT) ==="
  STEPS_SKIPPED=$((STEPS_SKIPPED + 1))
fi

# =========================================================================
# Step 3: NPM packages (download-npm.sh)
#
# Downloads npm tarballs by extracting resolved URLs from package-lock.json
# files.  Two strategies:
#
#   Preferred: use --tekton-file (or auto-detect from .tekton/) to find all
#   npm directories referenced in the Tekton PipelineRun.  This processes
#   all lockfiles in a single invocation and requires yq.
#
#   Fallback: recursively find package-lock.json files under prefetch-input/
#   and process each one individually.
#
# Output: cachi2/output/deps/npm/
# =========================================================================
echo "=== [3/4] NPM packages ==="

npm_done=false

# Try to auto-detect the Tekton PipelineRun YAML that references this
# component's prefetch-input directory.  The Tekton file lists all npm
# lockfile paths as task parameters, so download-npm.sh can process them
# all at once instead of discovering them one by one.
if [[ -z "$TEKTON_FILE" ]] && [[ -d ".tekton" ]] && command -v yq &>/dev/null; then
  auto_tekton=$(grep -rl "$COMPONENT_DIR/prefetch-input" .tekton/*pull-request*.yaml 2>/dev/null | head -1) || true
  if [[ -n "$auto_tekton" ]]; then
    TEKTON_FILE="$auto_tekton"
    echo "  Auto-detected tekton file: $TEKTON_FILE"
  fi
fi

if [[ -n "$TEKTON_FILE" ]]; then
  if [[ ! -f "$TEKTON_FILE" ]]; then
    echo "  Warning: Tekton file not found: $TEKTON_FILE — falling back to auto-discovery"
  elif ! command -v yq &>/dev/null; then
    echo "  Warning: yq not found — falling back to auto-discovery"
  else
    "$SCRIPTS_PATH/download-npm.sh" --tekton-file "$TEKTON_FILE"
    npm_done=true
  fi
fi

# Fallback: find and process package-lock.json files individually.
# Excludes node_modules/ to avoid processing installed (non-lockfile) copies.
if [[ "$npm_done" != true ]]; then
  echo "  Discovering package-lock.json files under $PREFETCH_DIR..."
  npm_count=0
  while IFS= read -r -d '' lock; do
    echo "  Processing: $lock"
    "$SCRIPTS_PATH/download-npm.sh" --lock-file "$lock"
    npm_count=$((npm_count + 1))
  done < <(find "$PREFETCH_DIR" -not -path "*/node_modules/*" -name "package-lock.json" -print0 2>/dev/null)

  if [[ $npm_count -eq 0 ]]; then
    echo "  No package-lock.json files found — skipping npm download"
    STEPS_SKIPPED=$((STEPS_SKIPPED + 1))
  else
    echo "  Processed $npm_count package-lock.json file(s)"
  fi
fi

if [[ "$npm_done" == true ]] || [[ ${npm_count:-0} -gt 0 ]]; then
  STEPS_RUN=$((STEPS_RUN + 1))
fi
echo ""

# =========================================================================
# Step 4: RPMs (hermeto-fetch-rpm.sh or create-rpm-lockfile.sh --download)
#
# Downloads OS-level RPM packages into cachi2/output/deps/rpm/ and creates
# DNF repo metadata so the Dockerfile can `dnf install` offline.
#
# Two modes depending on whether rpms.lock.yaml already exists:
#
#   Committed lockfile (rpms.lock.yaml present): call hermeto-fetch-rpm.sh
#   directly to download only.  This is the normal CI path — lockfiles are
#   committed to the repo and regenerated separately.
#
#   No lockfile: call create-rpm-lockfile.sh --download, which first
#   generates rpms.lock.yaml (requires building a container with
#   rpm-lockfile-prototype), then downloads.  This path is x86_64-only
#   because the lockfile generator container is built for that arch.
#
# Subscription credentials (if provided) are passed to child scripts via
# exported env vars (SUBSCRIPTION_ACTIVATION_KEY / SUBSCRIPTION_ORG),
# not command-line args.  hermeto-fetch-rpm.sh handles cert extraction.
#
# Output: cachi2/output/deps/rpm/
# =========================================================================
RPM_INPUT="$VARIANT_DIR/rpms.in.yaml"
RPM_LOCKFILE="$VARIANT_DIR/rpms.lock.yaml"
if [[ -f "$RPM_INPUT" ]]; then
  echo "=== [4/4] RPMs ==="
  if [[ -f "$RPM_LOCKFILE" ]]; then
    echo "  rpms.lock.yaml exists — downloading RPMs only (skipping lockfile regeneration)"
    "$SCRIPTS_PATH/helpers/hermeto-fetch-rpm.sh" --prefetch-dir "$VARIANT_DIR"
  else
    echo "  rpms.lock.yaml not found — generating lockfile and downloading"
    "$SCRIPTS_PATH/create-rpm-lockfile.sh" --rpm-input "$RPM_INPUT" --download
  fi
  STEPS_RUN=$((STEPS_RUN + 1))
  echo ""
else
  echo "=== [4/4] RPMs — SKIPPED (no $RPM_INPUT) ==="
  STEPS_SKIPPED=$((STEPS_SKIPPED + 1))
fi

# =========================================================================
# Summary — show what ran, what was skipped, and disk usage per dep type.
# =========================================================================
echo "=============================================="
echo " prefetch-all.sh complete"
echo "  Steps run    : $STEPS_RUN"
echo "  Steps skipped: $STEPS_SKIPPED"
echo ""
echo " Dependencies are in: cachi2/output/deps/"
if [[ -d "cachi2/output/deps" ]]; then
  echo ""
  du -sh cachi2/output/deps/*/ 2>/dev/null || true
fi
echo ""
echo " Next: run 'make <target>' — it will auto-detect cachi2/output/"
echo "       and mount it with LOCAL_BUILD=true."
echo "=============================================="
