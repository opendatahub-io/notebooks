#!/usr/bin/env bash
set -euo pipefail

# ----------------------------
# CONFIGURATION
# ----------------------------
CPU_INDEX="--index-url=https://console.redhat.com/api/pypi/public-rhai/rhoai/3.0/cpu-ubi9/simple/"
CUDA_INDEX="--index-url=https://console.redhat.com/api/pypi/public-rhai/rhoai/3.0/cuda-ubi9/simple/"
ROCM_INDEX="--index-url=https://console.redhat.com/api/pypi/public-rhai/rhoai/3.0/rocm-ubi9/simple/"

MAIN_DIRS=("jupyter" "runtimes" "rstudio" "codeserver")

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
info()  { echo -e "🔹 \033[1;34m$1\033[0m"; }
warn()  { echo -e "⚠️  \033[1;33m$1\033[0m"; }
error() { echo -e "❌ \033[1;31m$1\033[0m"; }
ok()    { echo -e "✅ \033[1;32m$1\033[0m"; }

# ----------------------------
# PRE-FLIGHT CHECK
# ----------------------------
if ! command -v uv &>/dev/null; then
  error "uv command not found. Please install uv: https://github.com/astral-sh/uv"
  exit 1
fi

# (Optional) check uv version (requires version >= 0.4.0)
UV_MIN_VERSION="0.4.0"
UV_VERSION=$(uv --version 2>/dev/null | awk '{print $2}' || echo "0.0.0")

version_ge() {
  # returns 0 if $1 >= $2
  [ "$(printf '%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

if ! version_ge "$UV_VERSION" "$UV_MIN_VERSION"; then
  error "uv version $UV_VERSION found, but >= $UV_MIN_VERSION is required."
  error "Please upgrade uv: https://github.com/astral-sh/uv"
  exit 1
fi

# ----------------------------
# GET TARGET DIRECTORIES
# ----------------------------
if [ $# -gt 0 ]; then
  TARGET_DIRS=("$1")
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
  mkdir -p uv.lock
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
    local output="uv.lock/pylock.${flavor}.toml"

    echo "➡️ Generating ${flavor^^} lock file..."
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
      warn "${flavor^^} lock failed in $TARGET_DIR"
      rm -f "$output"
      DIR_SUCCESS=false
    else
      ok "${flavor^^} lock generated successfully."
    fi
  }

  $HAS_CPU && run_lock "cpu" "$CPU_INDEX"
  $HAS_CUDA && run_lock "cuda" "$CUDA_INDEX"
  $HAS_ROCM && run_lock "rocm" "$ROCM_INDEX"

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
fi
