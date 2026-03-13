#!/usr/bin/env bash
set -euo pipefail

# hermeto-fetch-gomod.sh — Download Go modules using Hermeto.
#
# Fetches all Go dependencies for a module (go.mod + go.sum) into
# cachi2/output/deps/gomod/ so Dockerfiles can build Go code offline
# (e.g. GOPROXY=file:///cachi2/output/deps/gomod).
#
# Hermeto (hermetoproject/hermeto) runs in a container, reads go.mod/go.sum
# from the given source directory, and downloads modules into the output
# directory. No separate lockfile is needed — go.sum pins dependencies.

HERMETO_IMAGE="ghcr.io/hermetoproject/hermeto:0.46.2"
HERMETO_OUTPUT="./cachi2/output"

PREFETCH_DIR=""

show_help() {
  cat << 'EOF'
Usage: helpers/hermeto-fetch-gomod.sh [OPTIONS]

Download Go modules for a directory containing go.mod using Hermeto.

Options:
  --prefetch-dir DIR     Directory containing go.mod and go.sum (required)
  --help                 Show this help
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
    -h|--help)         show_help; exit 0 ;;
    *)                 error_exit "Unknown argument: '$1'" ;;
  esac
done

[[ -z "$PREFETCH_DIR" ]] && error_exit "--prefetch-dir is required."
[[ -f "$PREFETCH_DIR/go.mod" ]] || error_exit "go.mod not found in $PREFETCH_DIR"
[[ -f "$PREFETCH_DIR/go.sum" ]] || error_exit "go.sum not found in $PREFETCH_DIR"

# Hermeto requires the source to be a git repo with an 'origin' remote (it
# uses it for SBOM). Mount the repo root and pass the gomod path as JSON.
[[ -d .git ]] || error_exit "This script must be run from the repository root (no .git found)."
HERMETO_JSON=$(jq -n --arg path "$PREFETCH_DIR" '{type: "gomod", path: $path}')

# Hermeto fetch-deps wipes its --output directory on every run. Use a staging
# dir so we can merge into the shared cachi2/output/ without destroying other
# dep types (pip, npm, rpm, generic).
HERMETO_STAGING=$(mktemp -d)
trap 'rm -rf "$HERMETO_STAGING"' EXIT

echo "--- Downloading Go modules via hermeto ---"
podman run --rm \
  -v "$(pwd):/source:z" \
  -v "$HERMETO_STAGING:/output:z" \
  "$HERMETO_IMAGE" \
  fetch-deps --source /source --output /output "$HERMETO_JSON"

# Hermeto may run as root; fix ownership so the host user can use the files.
if ! test -w "$HERMETO_STAGING/deps/gomod" 2>/dev/null; then
  sudo chown -R "$(id -u):$(id -g)" "$HERMETO_STAGING" 2>/dev/null || true
fi

# Merge into shared cachi2/output. If multiple gomod prefetch paths are used,
# later runs merge into the same deps/gomod tree (Go module cache layout).
mkdir -p "$HERMETO_OUTPUT/deps/gomod"
if [[ -d "$HERMETO_STAGING/deps/gomod" ]]; then
  cp -a "$HERMETO_STAGING/deps/gomod"/* "$HERMETO_OUTPUT/deps/gomod/" 2>/dev/null || true
elif [[ -d "$HERMETO_STAGING/deps" ]]; then
  # Some hermeto versions may use a different subdir; merge whatever is under deps/
  for sub in "$HERMETO_STAGING/deps"/*/; do
    [[ -d "$sub" ]] && cp -a "$sub"* "$HERMETO_OUTPUT/deps/gomod/" 2>/dev/null || true
  done
fi
# Preserve bom and build-config if present (last run wins)
[[ -f "$HERMETO_STAGING/bom.json" ]] && cp -f "$HERMETO_STAGING/bom.json" "$HERMETO_OUTPUT/bom.json"
[[ -f "$HERMETO_STAGING/.build-config.json" ]] && cp -f "$HERMETO_STAGING/.build-config.json" "$HERMETO_OUTPUT/.build-config.json"

echo "Finished! Go modules are in $HERMETO_OUTPUT/deps/gomod"
