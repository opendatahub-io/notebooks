#!/usr/bin/env bash
set -euo pipefail

# create-pip-requirements-lockfile: Generate pinned requirements with hashes using uv.
#
# Supports two modes:
#   1. "export" (default) — runs `uv export` against a pyproject.toml to produce a fully
#      pinned requirements.txt with integrity hashes for every dependency.
#   2. "compile" — runs `uv pip compile` against a plain requirements .txt (e.g. Arrow's
#      requirements-wheel-build.txt) to resolve and pin all packages with hashes.
#
# The generated lockfiles are consumed by cachi2 / download-pip-packages.py to prefetch
# wheels for hermetic builds.
#
# This script MUST be run from the repository root.

# --- Configuration & Defaults ---
SCRIPTS_PATH="scripts/lockfile-generators"

IMAGE_DIR=""
OUTPUT_FILE=""
COMPILE_INPUT=""
DO_DOWNLOAD=false

# --- Functions ---
show_help() {
  cat << EOF
Usage: ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh [OPTIONS]

Generate pinned requirements (with hashes) using uv. Supports two modes:

  export  (default)  Resolve from pyproject.toml using 'uv export'
  compile            Resolve from a plain requirements .txt using 'uv pip compile'

Options:
  --image-dir VALUE    Path to image directory containing pyproject.toml
                       (e.g., codeserver/ubi9-python-3.12).  Required.
  --output FILE        Output file path
                         export mode default:  <image-dir>/requirements.txt
                         compile mode default: <image-dir>/prefetch-input/requirements-wheel-build.txt
  --compile FILE       Switch to compile mode: resolve the given plain requirements
                       file (e.g., a requirements-wheel-build.txt from a source tree)
                       using 'uv pip compile --generate-hashes'.
  --download           After generating the lockfile, fetch all wheels/sdists from
                       PyPI into cachi2/output/deps/pip/ using download-pip-packages.py.
  --help               Show this help message and exit

Examples:
  # Export from pyproject.toml (default mode)
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --image-dir codeserver/ubi9-python-3.12

  # Export to a custom output path
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --image-dir codeserver/ubi9-python-3.12 \\
    --output codeserver/ubi9-python-3.12/requirements-custom.txt

  # Compile (pin) Arrow's wheel-build requirements
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --image-dir codeserver/ubi9-python-3.12 \\
    --compile codeserver/ubi9-python-3.12/prefetch-input/arrow/python/requirements-wheel-build.txt

  # Compile (pin) build-system extras (older meson-python, Cython)
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --image-dir codeserver/ubi9-python-3.12 \\
    --compile codeserver/ubi9-python-3.12/prefetch-input/requirements-build-system-extras.in \\
    --output codeserver/ubi9-python-3.12/prefetch-input/requirements-build-system-extras.txt

  # Export and download all wheels/sdists into cachi2/output/deps/pip/
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --image-dir codeserver/ubi9-python-3.12 --download
EOF
}

error_exit() {
  echo "Error: $1" >&2
  echo "Use --help for usage information." >&2
  exit 1
}

# --- Validation ---
# Ensure script is executed from repository root
if [[ ! -d "$SCRIPTS_PATH" ]]; then
  error_exit "This script MUST be run from the repository root."
fi

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)       show_help; exit 0 ;;
    --image-dir)     IMAGE_DIR="$2";      shift 2 ;;
    --output|-o)     OUTPUT_FILE="$2";    shift 2 ;;
    --compile)       COMPILE_INPUT="$2";  shift 2 ;;
    --download)      DO_DOWNLOAD=true;   shift ;;
    *)               error_exit "Unknown argument: '$1'" ;;
  esac
done

# --- Required argument check ---
[[ -z "$IMAGE_DIR" ]] && error_exit "--image-dir is required. E.g. --image-dir codeserver/ubi9-python-3.12"

# --- Check for uv ---
if ! command -v uv &>/dev/null; then
  error_exit "'uv' is not installed. Install it with: pip install uv"
fi

# --- Mode dispatch ---
if [[ -n "$COMPILE_INPUT" ]]; then
  # ---- Compile mode: uv pip compile ----
  [[ -f "$COMPILE_INPUT" ]] || error_exit "Input requirements file not found: ${COMPILE_INPUT}"

  # Default output for compile mode
  if [[ -z "$OUTPUT_FILE" ]]; then
    OUTPUT_FILE="${IMAGE_DIR}/prefetch-input/requirements-wheel-build.txt"
  fi

  echo "--- Generating pip requirements lockfile (compile mode) ---"
  echo "  input  : ${COMPILE_INPUT}"
  echo "  output : ${OUTPUT_FILE}"
  echo ""

  uv pip compile \
    --generate-hashes \
    "${COMPILE_INPUT}" \
    -o "${OUTPUT_FILE}"

else
  # ---- Export mode: uv export ----
  PYPROJECT="${IMAGE_DIR}/pyproject.toml"
  [[ -f "$PYPROJECT" ]] || error_exit "pyproject.toml not found at ${PYPROJECT}"

  # Default output for export mode
  if [[ -z "$OUTPUT_FILE" ]]; then
    OUTPUT_FILE="${IMAGE_DIR}/requirements.txt"
  fi

  echo "--- Generating pip requirements lockfile (export mode) ---"
  echo "  pyproject.toml : ${PYPROJECT}"
  echo "  output         : ${OUTPUT_FILE}"
  echo ""

  uv export \
    --format requirements-txt \
    --project "${PYPROJECT}" \
    --output-file "${OUTPUT_FILE}" \
    --hashes \
    --no-annotate \
    --python 3.12

fi

echo ""
echo "--- Done: ${OUTPUT_FILE} ---"
wc -l "${OUTPUT_FILE}"

# --- Download wheels/sdists ---
if [[ "$DO_DOWNLOAD" == true ]]; then
  DOWNLOAD_SCRIPT="${SCRIPTS_PATH}/download-pip-packages.py"
  [[ -f "$DOWNLOAD_SCRIPT" ]] || error_exit "Download script not found at ${DOWNLOAD_SCRIPT}"

  echo ""
  echo "--- Downloading pip packages from ${OUTPUT_FILE} ---"
  python3 "${DOWNLOAD_SCRIPT}" "${OUTPUT_FILE}"
fi
