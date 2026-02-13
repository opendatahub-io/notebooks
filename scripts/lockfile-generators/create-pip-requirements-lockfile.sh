#!/usr/bin/env bash
set -euo pipefail

# create-pip-requirements-lockfile.sh — Generate pinned requirements with hashes.
#
# Why this script exists
# ----------------------
# Hermetic builds (Konflux/cachi2) require fully pinned requirements files with
# sha256 hashes so that every wheel/sdist can be prefetched and verified offline.
# This script automates that process using `uv` as the resolver.
#
# Additionally, public PyPI does not publish pre-built wheels for ppc64le and
# s390x for many data-science packages (numpy, scipy, pandas, pyarrow, etc.).
# Red Hat OpenShift AI (RHOAI) maintains a PyPI index with those wheels.  The
# --rhoai flag discovers available RHOAI packages, writes a separate
# requirements-rhoai.txt (with --index-url pointing to the RHOAI mirror), and
# merges the RHOAI wheel hashes into requirements.txt so that
# `uv pip install --verify-hashes` accepts both PyPI and RHOAI wheels.
#
# Modes
# -----
#   1. "export" (default) — runs `uv export` against a pyproject.toml to produce
#      a fully pinned requirements.txt with integrity hashes.
#   2. "compile" — runs `uv pip compile` against a plain requirements .txt (e.g.
#      a build-dependency file) to resolve and pin all packages with hashes.
#      RHOAI generation is not supported in compile mode.
#
# Generated files
# ---------------
#   requirements.txt       — pinned packages from public PyPI (+ RHOAI hashes
#                            merged in when --rhoai is used)
#   requirements-rhoai.txt — RHOAI-only packages with --index-url, consumed by
#                            cachi2 as a second pip prefetch source
#
# The generated lockfiles are consumed by cachi2 / download-pip-packages.py to
# prefetch wheels into cachi2/output/deps/pip/ for hermetic (--network=none) builds.
#
# This script MUST be run from the repository root.

# --- Configuration & Defaults ---
SCRIPTS_PATH="scripts/lockfile-generators"

PYPROJECT=""
OUTPUT_FILE=""
COMPILE_INPUT=""
DO_DOWNLOAD=false
RHOAI_INDEX=""
DEFAULT_RHOAI_INDEX="https://console.redhat.com/api/pypi/public-rhai/rhoai/3.4-EA1/cpu-ubi9/simple/"

# --- Functions ---
show_help() {
  cat << EOF
Usage: ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh [OPTIONS]

Generate pinned requirements (with hashes) using uv. Supports two modes:

  export  (default)  Resolve from pyproject.toml using 'uv export'
  compile            Resolve from a plain requirements .txt using 'uv pip compile'

Options:
  --pyproject-toml FILE  Path to pyproject.toml
                         (e.g., codeserver/ubi9-python-3.12/pyproject.toml).
                         Required for export mode.
  --output FILE          Output file path
                           export mode default:  <project-dir>/requirements.txt
                           compile mode default: <project-dir>/prefetch-input/requirements-wheel-build.txt
  --compile FILE         Switch to compile mode: resolve the given plain requirements
                         file (e.g., a requirements-wheel-build.txt from a source tree)
                         using 'uv pip compile --generate-hashes'.
  --rhoai                After export, discover RHOAI pre-built wheels and generate
                         requirements-rhoai.txt (using the default RHOAI index).
                         Also merges RHOAI hashes into requirements.txt.
  --rhoai-index URL      Same as --rhoai but with a custom RHOAI index URL.
  --download             After generating lockfiles, fetch all wheels/sdists into
                         cachi2/output/deps/pip/ using download-pip-packages.py.
  --help                 Show this help message and exit

Examples:
  # Export from pyproject.toml (default mode)
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml

  # Export + generate RHOAI requirements + download all wheels
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --rhoai --download

  # Export with a custom RHOAI index URL
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml \\
    --rhoai-index https://console.redhat.com/api/pypi/public-rhai/rhoai/3.4/cpu-ubi9/simple/

  # Compile (pin) a plain requirements file
  ./$SCRIPTS_PATH/create-pip-requirements-lockfile.sh \\
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml \\
    --compile some-requirements.in \\
    --output some-requirements.txt
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
    --pyproject-toml) PYPROJECT="$2";     shift 2 ;;
    --output|-o)     OUTPUT_FILE="$2";    shift 2 ;;
    --compile)       COMPILE_INPUT="$2";  shift 2 ;;
    --rhoai)         RHOAI_INDEX="$DEFAULT_RHOAI_INDEX"; shift ;;
    --rhoai-index)   RHOAI_INDEX="$2";   shift 2 ;;
    --download)      DO_DOWNLOAD=true;   shift ;;
    *)               error_exit "Unknown argument: '$1'" ;;
  esac
done

# --- Required argument check ---
[[ -z "$PYPROJECT" ]] && error_exit "--pyproject-toml is required. E.g. --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml"
[[ -f "$PYPROJECT" ]] || error_exit "pyproject.toml not found at: $PYPROJECT"

# Derive the project directory from the pyproject.toml path.
# All generated files (requirements.txt, requirements-rhoai.txt) are written here.
PROJECT_DIR="$(dirname "$PYPROJECT")"

# --- Check for uv ---
if ! command -v uv &>/dev/null; then
  error_exit "'uv' is not installed. Install it with: pip install uv"
fi

# --- Step 1: Resolve and pin all packages with hashes ---
if [[ -n "$COMPILE_INPUT" ]]; then
  # ---- Compile mode ----
  # Resolve a plain requirements .txt input file using `uv pip compile`.
  # Produces a fully pinned output with sha256 hashes for every package.
  [[ -f "$COMPILE_INPUT" ]] || error_exit "Input requirements file not found: ${COMPILE_INPUT}"

  if [[ -z "$OUTPUT_FILE" ]]; then
    OUTPUT_FILE="${PROJECT_DIR}/prefetch-input/requirements-wheel-build.txt"
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
  # ---- Export mode (default) ----
  # Resolve from pyproject.toml using `uv export`.  This reads the project's
  # dependency tree and produces a requirements.txt with pinned versions and
  # sha256 hashes.  Only PyPI hashes are included at this stage; RHOAI hashes
  # are merged in Step 2 below (if --rhoai is given).

  if [[ -z "$OUTPUT_FILE" ]]; then
    OUTPUT_FILE="${PROJECT_DIR}/requirements.txt"
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

# --- Step 2: RHOAI requirements generation (export mode only) ---
# Discover which packages from requirements.txt are also available on the RHOAI
# PyPI index.  For each match, collect the RHOAI wheel hashes and:
#   a) Write requirements-rhoai.txt — a separate file with --index-url pointing
#      to the RHOAI mirror, consumed by cachi2 as a second pip prefetch source.
#   b) Merge the RHOAI hashes into requirements.txt (--merge-hashes) so that
#      `uv pip install --verify-hashes` accepts both PyPI and RHOAI wheels
#      from the same requirements.txt at install time.
# See generate-rhoai-requirements.py for full details.
if [[ -n "$RHOAI_INDEX" ]]; then
  if [[ -n "$COMPILE_INPUT" ]]; then
    echo "Warning: --rhoai/--rhoai-index is only supported in export mode; skipping." >&2
  else
    RHOAI_SCRIPT="${SCRIPTS_PATH}/generate-rhoai-requirements.py"
    [[ -f "$RHOAI_SCRIPT" ]] || error_exit "RHOAI generator not found at ${RHOAI_SCRIPT}"

    RHOAI_OUTPUT="${PROJECT_DIR}/requirements-rhoai.txt"

    echo ""
    echo "--- Generating RHOAI requirements ---"
    echo "  index  : ${RHOAI_INDEX}"
    echo "  output : ${RHOAI_OUTPUT}"
    echo ""

    python3 "${RHOAI_SCRIPT}" \
      --requirements "${OUTPUT_FILE}" \
      --output "${RHOAI_OUTPUT}" \
      --rhoai-index "${RHOAI_INDEX}" \
      --merge-hashes \
      --prefer-rhoai-version

    echo ""
    echo "--- Done: ${RHOAI_OUTPUT} ---"
    wc -l "${RHOAI_OUTPUT}"
  fi
fi

# --- Step 3: Download wheels/sdists into local cachi2 cache ---
# Fetch all packages from both requirements.txt (PyPI) and requirements-rhoai.txt
# (RHOAI index) into cachi2/output/deps/pip/.  This populates the local cache
# used by `podman build --build-arg LOCAL_BUILD=true` for offline builds.
# In Konflux CI, cachi2 handles prefetching automatically; this step is for
# local development and testing only.
if [[ "$DO_DOWNLOAD" == true ]]; then
  DOWNLOAD_SCRIPT="${SCRIPTS_PATH}/download-pip-packages.py"
  [[ -f "$DOWNLOAD_SCRIPT" ]] || error_exit "Download script not found at ${DOWNLOAD_SCRIPT}"

  # Download PyPI packages from requirements.txt
  echo ""
  echo "--- Downloading pip packages from ${OUTPUT_FILE} ---"
  python3 "${DOWNLOAD_SCRIPT}" "${OUTPUT_FILE}"

  # Download RHOAI packages from requirements-rhoai.txt (if generated in Step 2)
  if [[ -n "$RHOAI_INDEX" && -z "$COMPILE_INPUT" ]]; then
    RHOAI_OUTPUT="${PROJECT_DIR}/requirements-rhoai.txt"
    if [[ -f "$RHOAI_OUTPUT" ]]; then
      echo ""
      echo "--- Downloading RHOAI packages from ${RHOAI_OUTPUT} ---"
      python3 "${DOWNLOAD_SCRIPT}" "${RHOAI_OUTPUT}"
    fi
  fi
fi
