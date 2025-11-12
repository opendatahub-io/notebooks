#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# pylocks_generator.sh
#
# This script generates Python dependency lock files (pylock.toml) for multiple
# directories using either internal AIPCC wheel indexes or the public PyPI index.
#
# Features:
#   • Supports multiple Python project directories, detected by pyproject.toml.
#   • Detects available Dockerfile flavors (CPU, CUDA, ROCm) for AIPCC index mode.
#   • Validates Python version extracted from directory name (expects format .../ubi9-python-X.Y).
#   • Generates per-flavor locks in 'uv.lock/' for AIPCC index mode.
#   • Overwrites existing pylock.toml in-place for public PyPI index mode.
#
# Index Modes:
#   • aipcc-index  -> Uses internal Red Hat AIPCC wheel indexes. Generates uv.lock/pylock.<flavor>.toml for each detected flavor.
#   • public-index -> Uses public PyPI index. Updates pylock.toml in the project directory.
#                    Default mode if not specified.
#
# Usage:
#   1. Lock using default public index for all projects in MAIN_DIRS:
#        bash pylocks_generator.sh
#
#   2. Lock using AIPCC index for a specific directory:
#        bash pylocks_generator.sh aipcc-index jupyter/minimal/ubi9-python-3.12
#
#   3. Lock using public index for a specific directory:
#        bash pylocks_generator.sh public-index jupyter/minimal/ubi9-python-3.12
#
# Notes:
#   • If the script fails for a directory, it lists the failed directories at the end.
#   • Public index mode does not create uv.lock directories keeps the old format.
#   • Python version extraction depends on directory naming convention; invalid formats are skipped.
# =============================================================================

# ----------------------------
# CONFIGURATION
# ----------------------------
CPU_INDEX="--index-url=https://console.redhat.com/api/pypi/public-rhai/rhoai/3.0/cpu-ubi9/simple/"
CUDA_INDEX="--index-url=https://console.redhat.com/api/pypi/public-rhai/rhoai/3.0/cuda-ubi9/simple/"
ROCM_INDEX="--index-url=https://console.redhat.com/api/pypi/public-rhai/rhoai/3.0/rocm-ubi9/simple/"
PUBLIC_INDEX="--index-url=https://pypi.org/simple"

MAIN_DIRS=("jupyter" "runtimes" "rstudio" "codeserver")

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
info()  { echo -e "🔹 \033[1;34m$1\033[0m"; }
warn()  { echo -e "⚠️  \033[1;33m$1\033[0m"; }
error() { echo -e "❌ \033[1;31m$1\033[0m"; }
ok()    { echo -e "✅ \033[1;32m$1\033[0m"; }

uppercase() {
  echo "$1" | tr '[:lower:]' '[:upper:]'
}

# ----------------------------
# PRE-FLIGHT CHECK
# ----------------------------
if ! command -v uv &>/dev/null; then
  error "uv command not found. Please install uv: https://github.com/astral-sh/uv"
  exit 1
fi

UV_MIN_VERSION="0.4.0"
UV_VERSION=$(uv --version 2>/dev/null | awk '{print $2}' || echo "0.0.0")

version_ge() {
  [ "$(printf '%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

if ! version_ge "$UV_VERSION" "$UV_MIN_VERSION"; then
  error "uv version $UV_VERSION found, but >= $UV_MIN_VERSION is required."
  error "Please upgrade uv: https://github.com/astral-sh/uv"
  exit 1
fi

# ----------------------------
# ARGUMENT PARSING
# ----------------------------
# default to public-index if not provided
INDEX_MODE="${1:-public-index}"
TARGET_DIR_ARG="${2:-}"

# Validate mode
if [[ "$INDEX_MODE" != "aipcc-index" && "$INDEX_MODE" != "public-index" ]]; then
  error "Invalid mode '$INDEX_MODE'. Valid options: aipcc-index, public-index"
  exit 1
fi
info "Using index mode: $INDEX_MODE"

# ----------------------------
# GET TARGET DIRECTORIES
# ----------------------------
if [ -n "$TARGET_DIR_ARG" ]; then
  TARGET_DIRS=("$TARGET_DIR_ARG")
else
  info "Scanning main directories for Python projects..."
  TARGET_DIRS=()
  for base in "${MAIN_DIRS[@]}"; do
    if [ -d "$base" ]; then
      while IFS= read -r -d '' pyproj; do
        TARGET_DIRS+=("$(dirname "$pyproj")")
      done < <(find "$base" -type f -name "pyproject.toml" -print0)
    fi
  done
fi

if [ ${#TARGET_DIRS[@]} -eq 0 ]; then
  error "No directories containing pyproject.toml were found."
  exit 1
fi

# ----------------------------
# MAIN LOOP
# ----------------------------
FAILED_DIRS=()
SUCCESS_DIRS=()

for TARGET_DIR in "${TARGET_DIRS[@]}"; do
  echo
  echo "==================================================================="
  info "Processing directory: $TARGET_DIR"
  echo "==================================================================="

  cd "$TARGET_DIR" || continue
  PYTHON_VERSION="${PWD##*-}"

  # Validate Python version extraction
  if [[ ! "$PYTHON_VERSION" =~ ^[0-9]+\.[0-9]+$ ]]; then
    warn "Could not extract valid Python version from directory name: $PWD"
    warn "Expected directory format: .../ubi9-python-X.Y"
    cd - >/dev/null
    continue
  fi

  # Detect available Dockerfiles (flavors)
  HAS_CPU=false
  HAS_CUDA=false
  HAS_ROCM=false
  [ -f "Dockerfile.cpu" ] && HAS_CPU=true
  [ -f "Dockerfile.cuda" ] && HAS_CUDA=true
  [ -f "Dockerfile.rocm" ] && HAS_ROCM=true

  if ! $HAS_CPU && ! $HAS_CUDA && ! $HAS_ROCM; then
    warn "No Dockerfiles found in $TARGET_DIR (cpu/cuda/rocm). Skipping."
    cd - >/dev/null
    continue
  fi

  echo "📦 Python version: $PYTHON_VERSION"
  echo "🧩 Detected flavors:"
  $HAS_CPU && echo "  • CPU"
  $HAS_CUDA && echo "  • CUDA"
  $HAS_ROCM && echo "  • ROCm"
  echo

  DIR_SUCCESS=true

  run_lock() {
    local flavor="$1"
    local index="$2"
    local output
    local desc

    if [[ "$INDEX_MODE" == "public-index" ]]; then
      output="pylock.toml"
      desc="pylock.toml (public index)"
      echo "➡️ Generating pylock.toml from public PyPI index..."
    else
      mkdir -p uv.lock
      output="uv.lock/pylock.${flavor}.toml"
      desc="$(uppercase "$flavor") lock file"
      echo "➡️ Generating $(uppercase "$flavor") lock file..."
    fi

    set +e
    uv pip compile pyproject.toml \
      --output-file "$output" \
      --format pylock.toml \
      --generate-hashes \
      --emit-index-url \
      --python-version="$PYTHON_VERSION" \
      --python-platform linux \
      --no-annotate \
      $index
    local status=$?
    set -e

    if [ $status -ne 0 ]; then
      warn "Failed to generate $desc in $TARGET_DIR"
      rm -f "$output"
      DIR_SUCCESS=false
    else
      if [[ "$INDEX_MODE" == "public-index" ]]; then
        ok "pylock.toml generated successfully."
      else
        ok "$(uppercase "$flavor") lock generated successfully."
      fi
    fi
  }

  # Run lock generation
  if [[ "$INDEX_MODE" == "public-index" ]]; then
    # public-index always updates pylock.toml in place
    run_lock "cpu" "$PUBLIC_INDEX"
  else
    $HAS_CPU && run_lock "cpu" "$CPU_INDEX"
    $HAS_CUDA && run_lock "cuda" "$CUDA_INDEX"
    $HAS_ROCM && run_lock "rocm" "$ROCM_INDEX"
  fi

  if $DIR_SUCCESS; then
    SUCCESS_DIRS+=("$TARGET_DIR")
  else
    FAILED_DIRS+=("$TARGET_DIR")
  fi

  cd - >/dev/null
done

# ----------------------------
# SUMMARY
# ----------------------------
echo
echo "==================================================================="
ok "Lock generation complete."
echo "==================================================================="

if [ ${#SUCCESS_DIRS[@]} -gt 0 ]; then
  echo "✅ Successfully generated locks for:"
  for d in "${SUCCESS_DIRS[@]}"; do
    echo "  • $d"
  done
fi

if [ ${#FAILED_DIRS[@]} -gt 0 ]; then
  echo
  warn "Failed lock generation for:"
  for d in "${FAILED_DIRS[@]}"; do
    echo "  • $d"
    echo "Please comment out the missing package to continue and report the missing package to aipcc"
  done
  exit 1
fi
