#!/usr/bin/env bash
set -euo pipefail

# prefetch-all.sh — Download all hermetic build dependencies for a component.
#
# Orchestrates generating lockfiles and downloading all dependency types
# (generic artifacts, pip wheels, npm packages, RPMs) into
# cachi2/output/deps/ for local and CI hermetic builds.
# Delegates to the four main lockfile-generator scripts with --download.
#
# After running this script, `make <target>` will auto-detect cachi2/output/
# and pass --volume + --build-arg LOCAL_BUILD=true to podman build.
#
# Usage:
#   # Basic — upstream ODH (CentOS Stream base, no subscription):
#   ./scripts/lockfile-generators/prefetch-all.sh \
#       --component-dir codeserver/ubi9-python-3.12
#
#   # Downstream RHDS (uses RHEL subscription repos):
#   ./scripts/lockfile-generators/prefetch-all.sh \
#       --component-dir codeserver/ubi9-python-3.12 --rhds \
#       --activation-key my-key --org my-org
#
#   # Custom flavor:
#   ./scripts/lockfile-generators/prefetch-all.sh \
#       --component-dir codeserver/ubi9-python-3.12 --flavor cuda
#
# Prerequisites: wget, python3 (with pyyaml), jq, podman, uv

SCRIPTS_PATH="scripts/lockfile-generators"

COMPONENT_DIR=""
VARIANT="odh"
FLAVOR="cpu"
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
HELPEOF
}

error_exit() {
  echo "Error: $1" >&2
  exit 1
}

# --- Validation ---
if [[ ! -d "$SCRIPTS_PATH" ]]; then
  error_exit "This script must be run from the repository root."
fi

# --- Argument Parsing ---
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

PREFETCH_DIR="$COMPONENT_DIR/prefetch-input"
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
# Generates artifacts.lock.yaml and downloads GPG keys, nfpm RPMs, node
# headers, electron binaries, etc. into cachi2/output/deps/generic/.
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
# Generates pylock.<flavor>.toml + requirements.<flavor>.txt, then
# downloads all wheels into cachi2/output/deps/pip/.
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
# Downloads npm tarballs into cachi2/output/deps/npm/ by extracting
# resolved URLs from package-lock.json files.
#
# Preferred: use --tekton-file (or auto-detect from .tekton/) which
# processes all npm directories in a single pass.  Requires yq.
# Fallback: discover package-lock.json files and process one by one.
# =========================================================================
echo "=== [3/4] NPM packages ==="

npm_done=false

# Auto-detect tekton file if not provided
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
# Step 4: RPMs (create-rpm-lockfile.sh --download)
# Generates rpms.lock.yaml, then downloads RPM packages into
# cachi2/output/deps/rpm/ via Hermeto, creating DNF repo metadata.
# Requires podman (to run the hermeto and rpm-lockfile containers).
#
# Optimization: if rpms.lock.yaml already exists (committed), skip the
# lockfile regeneration and just download.  This avoids a cross-platform
# issue where create-rpm-lockfile.sh builds an x86_64 container that
# won't run on arm64 CI runners without QEMU.
# =========================================================================
RPM_INPUT="$VARIANT_DIR/rpms.in.yaml"
RPM_LOCKFILE="$VARIANT_DIR/rpms.lock.yaml"
if [[ -f "$RPM_INPUT" ]]; then
  echo "=== [4/4] RPMs ==="
  if [[ -f "$RPM_LOCKFILE" ]]; then
    echo "  rpms.lock.yaml exists — downloading RPMs only (skipping lockfile regeneration)"
    HERMETO_ARGS=(--prefetch-dir "$VARIANT_DIR")
    if [[ -n "$ACTIVATION_KEY" ]] && [[ -n "$ORG" ]]; then
      HERMETO_ARGS+=(--activation-key "$ACTIVATION_KEY" --org "$ORG")
    fi
    "$SCRIPTS_PATH/helpers/hermeto-fetch-rpm.sh" "${HERMETO_ARGS[@]}"
  else
    echo "  rpms.lock.yaml not found — generating lockfile and downloading"
    RPM_ARGS=(--rpm-input "$RPM_INPUT" --download)
    if [[ -n "$ACTIVATION_KEY" ]] && [[ -n "$ORG" ]]; then
      RPM_ARGS+=(--activation-key "$ACTIVATION_KEY" --org "$ORG")
    fi
    "$SCRIPTS_PATH/create-rpm-lockfile.sh" "${RPM_ARGS[@]}"
  fi
  STEPS_RUN=$((STEPS_RUN + 1))
  echo ""
else
  echo "=== [4/4] RPMs — SKIPPED (no $RPM_INPUT) ==="
  STEPS_SKIPPED=$((STEPS_SKIPPED + 1))
fi

# =========================================================================
# Summary
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
