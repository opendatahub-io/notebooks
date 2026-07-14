#!/usr/bin/env bash
set -euo pipefail

# create-go-lockfile.sh — Prefetch Go modules for hermetic builds using Hermeto.
#
# Go dependencies are pinned in go.sum (no separate lockfile). This script
# discovers gomod-type prefetch-input paths (from a Tekton file or a single
# --prefetch-dir) and runs hermeto fetch-deps for each, writing modules
# into cachi2/output/deps/gomod/ so Dockerfiles can build offline.
#
# Usage:
#   # From Tekton: discover all gomod paths and fetch each
#   ./scripts/lockfile-generators/create-go-lockfile.sh --tekton-file .tekton/foo-pull-request.yaml
#
#   # Single directory (must contain go.mod and go.sum)
#   ./scripts/lockfile-generators/create-go-lockfile.sh --prefetch-dir jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli
#
# Must be run from the repository root.

SCRIPTS_PATH="scripts/lockfile-generators"
TEKTON_FILE=""
PREFETCH_DIR=""

show_help() {
  cat << EOF
Usage: $SCRIPTS_PATH/create-go-lockfile.sh [OPTIONS]

Prefetch Go modules for hermetic builds. At least one of --tekton-file or
--prefetch-dir is required. Run from the repository root.

Options:
  --tekton-file PATH   Tekton PipelineRun YAML; extract gomod-type prefetch-input paths
  --prefetch-dir PATH   Single directory containing go.mod and go.sum
  -h, --help            Show this help
EOF
}

error_exit() {
  echo "Error: $1" >&2
  exit 1
}

# Print gomod prefetch-input paths from a Tekton file (one per line).
extract_gomod_paths_from_tekton() {
  local tekton_file="$1"
  yq eval '
    .spec.params[]
    | select(.name == "prefetch-input")
    | .value[]
    | select(.type == "gomod")
    | .path
  ' "$tekton_file"
}

# --- Validation: run from repo root ---
if [[ ! -d "$SCRIPTS_PATH" ]]; then
  error_exit "This script must be run from the repository root."
fi

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tekton-file)   [[ $# -ge 2 ]] || error_exit "--tekton-file requires a value"
                     TEKTON_FILE="$2"; shift 2 ;;
    --prefetch-dir)  [[ $# -ge 2 ]] || error_exit "--prefetch-dir requires a value"
                     PREFETCH_DIR="$2"; shift 2 ;;
    -h|--help)       show_help; exit 0 ;;
    --help)          show_help; exit 0 ;;
    *)               error_exit "Unknown argument: '$1'" ;;
  esac
done

[[ -z "$TEKTON_FILE" && -z "$PREFETCH_DIR" ]] && error_exit "At least one of --tekton-file or --prefetch-dir is required."

if [[ -n "$TEKTON_FILE" && ! -f "$TEKTON_FILE" ]]; then
  error_exit "Tekton file not found: $TEKTON_FILE"
fi
if [[ -n "$PREFETCH_DIR" ]]; then
  [[ -d "$PREFETCH_DIR" ]] || error_exit "Prefetch directory not found: $PREFETCH_DIR"
  [[ -f "$PREFETCH_DIR/go.mod" ]] || error_exit "go.mod not found in $PREFETCH_DIR"
fi

if [[ -n "$TEKTON_FILE" ]]; then
  command -v yq &>/dev/null || error_exit "yq is required for --tekton-file (https://github.com/mikefarah/yq)."
fi

# --- Collect gomod directories to process ---
gomod_paths=()
if [[ -n "$PREFETCH_DIR" ]]; then
  gomod_paths+=("$PREFETCH_DIR")
fi
if [[ -n "$TEKTON_FILE" ]]; then
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    gomod_paths+=("$p")
  done <<< "$(extract_gomod_paths_from_tekton "$TEKTON_FILE")"
fi

# Deduplicate (in case both --prefetch-dir and Tekton list the same path)
gomod_paths=($(printf '%s\n' "${gomod_paths[@]}" | sort -u))

if [[ ${#gomod_paths[@]} -eq 0 ]]; then
  echo "No gomod prefetch paths to process."
  exit 0
fi

echo "Go module prefetch: ${#gomod_paths[@]} path(s)"
for dir in "${gomod_paths[@]}"; do
  [[ -f "$dir/go.mod" ]] && [[ -f "$dir/go.sum" ]] || {
    echo "Skipping $dir (missing go.mod or go.sum)" >&2
    continue
  }
  echo "--- Fetching Go modules for $dir ---"
  "$SCRIPTS_PATH/helpers/hermeto-fetch-gomod.sh" --prefetch-dir "$dir"
done

echo "create-go-lockfile.sh finished. Go modules are in cachi2/output/deps/gomod/"
