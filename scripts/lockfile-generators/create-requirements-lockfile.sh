#!/usr/bin/env bash
set -euo pipefail

# create-requirements-lockfile.sh — Resolve deps via RHOAI and download wheels.
#
# Why this script exists
# ----------------------
# Hermetic builds need every Python wheel prefetched.  This script:
#   1. Runs `uv pip compile` against a pyproject.toml with the RHOAI index as
#      the default source, producing a pylock.toml (PEP 665) that pins every
#      package to an RHOAI-provided wheel with sha256 hashes.
#   2. Generates a pip-compatible requirements.txt from the pylock.toml.
#   3. (--download) Downloads every wheel referenced in the pylock.toml into
#      cachi2/output/deps/pip/ for offline builds.
#
# The RHOAI index provides pre-built wheels for all target architectures
# (x86_64, aarch64, ppc64le, s390x), eliminating source builds entirely.
#
# This script MUST be run from the repository root.
#
# Examples
# --------
#   # Resolve + generate requirements.txt
#   ./scripts/lockfile-generators/create-requirements-lockfile.sh \
#       --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml
#
#   # Resolve + generate + download all wheels
#   ./scripts/lockfile-generators/create-requirements-lockfile.sh \
#       --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --download
#
#   # Custom flavor and RHOAI index
#   ./scripts/lockfile-generators/create-requirements-lockfile.sh \
#       --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml \
#       --flavor cuda --rhoai-index https://.../.../cuda-ubi9/simple/

SCRIPTS_PATH="scripts/lockfile-generators"

# --- Defaults ---
PYPROJECT=""
FLAVOR="cpu"
RHOAI_INDEX=""
DEFAULT_RHOAI_BASE="https://console.redhat.com/api/pypi/public-rhai/rhoai/3.4-EA1"
DO_DOWNLOAD=false

# Meta-packages that are local path sources — must be excluded from the lock
# output since they're not real PyPI packages.
NO_EMIT_PACKAGES=(
    odh-notebooks-meta-llmcompressor-deps
    odh-notebooks-meta-runtime-elyra-deps
    odh-notebooks-meta-runtime-datascience-deps
    odh-notebooks-meta-workbench-datascience-deps
)

# --- Functions ---
show_help() {
  cat << 'EOF'
Usage: ./scripts/lockfile-generators/create-requirements-lockfile.sh [OPTIONS]

Resolve Python dependencies via the RHOAI index and generate a pylock.toml +
requirements.txt with sha256 hashes for hermetic builds.

Options:
  --pyproject-toml FILE  Path to pyproject.toml (required)
                         (e.g. codeserver/ubi9-python-3.12/pyproject.toml)
  --flavor NAME          Lock file flavor (default: cpu).
                         Determines the output filename (pylock.<flavor>.toml)
                         and the RHOAI index URL (<flavor>-ubi9).
  --rhoai-index URL      Custom RHOAI simple-index URL.  If not given, derived
                         from --flavor as:
                           .../rhoai/3.4-EA1/<flavor>-ubi9/simple/
  --download             After generating the lock, download all wheels into
                         cachi2/output/deps/pip/ for offline builds.
  -h, --help             Show this help message and exit

Steps performed:
  1. uv pip compile → <project>/uv.lock.d/pylock.<flavor>.toml
  2. Convert pylock.toml → <project>/requirements.txt
  3. (--download) Download all wheels from pylock.toml URLs
EOF
}

error_exit() {
  echo "Error: $1" >&2
  echo "Use --help for usage information." >&2
  exit 1
}

# --- Validation ---
if [[ ! -d "$SCRIPTS_PATH" ]]; then
  error_exit "This script MUST be run from the repository root."
fi

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)           show_help; exit 0 ;;
    --pyproject-toml)    PYPROJECT="$2"; shift 2 ;;
    --flavor)            FLAVOR="$2"; shift 2 ;;
    --rhoai-index)       RHOAI_INDEX="$2"; shift 2 ;;
    --download)          DO_DOWNLOAD=true; shift ;;
    *)                   error_exit "Unknown argument: '$1'" ;;
  esac
done

[[ -z "$PYPROJECT" ]] && error_exit "--pyproject-toml is required."
[[ -f "$PYPROJECT" ]] || error_exit "File not found: $PYPROJECT"

# Derive paths
PROJECT_DIR="$(dirname "$PYPROJECT")"
PYLOCK_DIR="${PROJECT_DIR}/uv.lock.d"
PYLOCK_FILE="${PYLOCK_DIR}/pylock.${FLAVOR}.toml"
REQUIREMENTS_FILE="${PROJECT_DIR}/requirements.txt"

# Derive RHOAI index URL from flavor if not explicitly set
if [[ -z "$RHOAI_INDEX" ]]; then
  RHOAI_INDEX="${DEFAULT_RHOAI_BASE}/${FLAVOR}-ubi9/simple/"
fi

# Constraints file (relative to project dir, used by uv pip compile)
CONSTRAINTS_REL="../../dependencies/cve-constraints.txt"
CONSTRAINTS_ABS="${PROJECT_DIR}/${CONSTRAINTS_REL}"
if [[ ! -f "$CONSTRAINTS_ABS" ]]; then
  echo "Warning: constraints file not found at ${CONSTRAINTS_ABS}" >&2
  CONSTRAINTS_REL=""
fi

# --- Check for uv ---
if ! command -v uv &>/dev/null; then
  error_exit "'uv' is not installed. Install it with: pip install uv"
fi

# =========================================================================
# Step 1: uv pip compile → pylock.toml
# =========================================================================
echo "=== Step 1: Generating pylock.toml ==="
echo "  pyproject.toml : ${PYPROJECT}"
echo "  output         : ${PYLOCK_FILE}"
echo "  flavor         : ${FLAVOR}"
echo "  RHOAI index    : ${RHOAI_INDEX}"
echo ""

mkdir -p "$PYLOCK_DIR"

# Build the --no-emit-package flags
NO_EMIT_FLAGS=()
for pkg in "${NO_EMIT_PACKAGES[@]}"; do
  NO_EMIT_FLAGS+=(--no-emit-package "$pkg")
done

# Build the constraints flag
CONSTRAINTS_FLAGS=()
if [[ -n "$CONSTRAINTS_REL" ]]; then
  CONSTRAINTS_FLAGS=(--constraints="$CONSTRAINTS_REL")
fi

# Run uv pip compile from the project directory so relative paths resolve
(
  cd "$PROJECT_DIR"
  uv pip compile pyproject.toml \
    --output-file "uv.lock.d/pylock.${FLAVOR}.toml" \
    --format pylock.toml \
    --refresh \
    --upgrade \
    --generate-hashes \
    --emit-index-url \
    --python-version=3.12 \
    --universal \
    --no-annotate \
    "${NO_EMIT_FLAGS[@]}" \
    "${CONSTRAINTS_FLAGS[@]}" \
    --default-index="$RHOAI_INDEX" \
    --index="$RHOAI_INDEX"
)

echo ""
echo "--- Done: ${PYLOCK_FILE} ---"
wc -l "$PYLOCK_FILE"

# =========================================================================
# Step 2: Convert pylock.toml → requirements.txt
#
# The pylock.toml (PEP 665) format is not yet supported by pip or cachi2.
# This step converts it to a pip-compatible requirements.txt with
# --hash=sha256:… lines for integrity verification.
#
# The helper script (helpers/pylock-to-requirements.py) parses the TOML,
# extracts name, version, markers, and sha256 hashes from each [[packages]]
# entry, and writes them in the standard requirements format.
# =========================================================================
echo ""
echo "=== Step 2: Converting pylock.toml → requirements.txt ==="

python3 "${SCRIPTS_PATH}/helpers/pylock-to-requirements.py" \
    "$PYLOCK_FILE" "$REQUIREMENTS_FILE" "$RHOAI_INDEX"

echo ""
echo "--- Done: ${REQUIREMENTS_FILE} ---"
wc -l "${REQUIREMENTS_FILE}"

# =========================================================================
# Step 3 (optional): Download all wheels from pylock.toml
#
# Downloads every wheel referenced in the pylock.toml into
# cachi2/output/deps/pip/ for local offline builds (podman).
# In Konflux, cachi2 handles this automatically via prefetch-input.
#
# Each wheel's sha256 checksum is verified after download.
# Files already present in the output directory are skipped.
# =========================================================================
if [[ "$DO_DOWNLOAD" == true ]]; then
  echo ""
  echo "=== Step 3: Downloading wheels ==="

  OUT_DIR="cachi2/output/deps/pip"
  mkdir -p "$OUT_DIR"

  # Detect sha256 command: sha256sum (Linux/GNU), shasum (macOS/BSD)
  if command -v sha256sum &>/dev/null; then
    sha256_of() { sha256sum "$1" | cut -d' ' -f1; }
  else
    sha256_of() { shasum -a 256 "$1" | cut -d' ' -f1; }
  fi

  # In pylock.toml, each wheel entry lives on a single line with both the
  # download URL and its sha256 hash in the same inline TOML table:
  #   { url = "https://..../pkg-1.0-py3-none-any.whl", hashes = { sha256 = "abc..." } }
  # We grep for lines containing both fields, then extract with sed.
  total=$(grep -c 'url = ".*sha256 = "' "$PYLOCK_FILE" || true)
  echo "  ${total} wheel(s) to download into ${OUT_DIR}/"
  echo ""

  idx=0
  while IFS= read -r line; do
    idx=$((idx + 1))

    # Extract the URL and expected sha256 hash from the TOML inline table
    url=$(echo "$line" | sed 's/.*url = "\([^"]*\)".*/\1/')
    sha=$(echo "$line" | sed 's/.*sha256 = "\([^"]*\)".*/\1/')

    # Derive the filename from the URL (strip query string and fragment)
    filename="${url##*/}"; filename="${filename%%[?#]*}"
    dest="${OUT_DIR}/${filename}"

    echo "[${idx}/${total}] ${filename}"

    # Download only if the file doesn't already exist (skip re-downloads)
    if [[ ! -f "$dest" ]]; then
      echo "  Downloading: ${url}"
      wget -q -O "$dest" "$url"
    else
      echo "  Already exists, skipping download."
    fi

    # Always verify checksum (even for pre-existing files)
    actual=$(sha256_of "$dest")
    if [[ "$actual" != "$sha" ]]; then
      echo "  ERROR: checksum mismatch (got ${actual}, expected ${sha})" >&2
      exit 1
    fi
    echo "  Checksum OK (sha256:${actual:0:16}...)"
  done < <(grep 'url = ".*sha256 = "' "$PYLOCK_FILE")

  echo ""
  echo "Done: ${total} file(s) present and validated in ${OUT_DIR}/"
fi

echo ""
echo "=== All done ==="
echo "  pylock.toml      : ${PYLOCK_FILE}"
echo "  requirements.txt : ${REQUIREMENTS_FILE}"
if [[ "$DO_DOWNLOAD" == true ]]; then
  echo "  wheels           : cachi2/output/deps/pip/"
fi
