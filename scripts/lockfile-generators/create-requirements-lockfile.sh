#!/usr/bin/env bash
set -euo pipefail

# create-requirements-lockfile.sh — Generate requirements.<flavor>.txt for hermetic builds.
#
# Why this script exists
# ----------------------
# Hermetic builds need every Python wheel prefetched.  This script:
#   1. Delegates to pylocks_generator.sh to generate pylock.<flavor>.toml
#      (ensures consistency with CI's check-generated-code).
#   2. Converts the pylock to a pip-compatible requirements.<flavor>.txt.
#   3. (--download) Downloads every wheel into cachi2/output/deps/pip/.
#
# This script MUST be run from the repository root.
#
# Examples
# --------
#   # Generate pylock + requirements.txt
#   ./scripts/lockfile-generators/create-requirements-lockfile.sh \
#       --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml
#
#   # Generate + download all wheels
#   ./scripts/lockfile-generators/create-requirements-lockfile.sh \
#       --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --download
#
#   # Custom flavor
#   ./scripts/lockfile-generators/create-requirements-lockfile.sh \
#       --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --flavor cuda

SCRIPTS_PATH="scripts/lockfile-generators"
PYLOCKS_GENERATOR="scripts/pylocks_generator.sh"

# --- Defaults ---
PYPROJECT=""
FLAVOR="cpu"
DO_DOWNLOAD=false

# --- Functions ---
show_help() {
  cat << 'EOF'
Usage: ./scripts/lockfile-generators/create-requirements-lockfile.sh [OPTIONS]

Generate pylock.<flavor>.toml (via pylocks_generator.sh) and convert it to
a pip-compatible requirements.<flavor>.txt with sha256 hashes.

Options:
  --pyproject-toml FILE  Path to pyproject.toml (required)
                         (e.g. codeserver/ubi9-python-3.12/pyproject.toml)
  --flavor NAME          Lock file flavor (default: cpu).
                         Must match a Dockerfile.<flavor> and
                         build-args/<flavor>.conf in the project directory.
  --download             After generating, download all wheels into
                         cachi2/output/deps/pip/ for offline builds.
  -h, --help             Show this help message and exit

Steps performed:
  1. pylocks_generator.sh → <project>/uv.lock.d/pylock.<flavor>.toml
  2. Convert pylock.<flavor>.toml → <project>/requirements.<flavor>.txt
  3. (--download) Download all wheels from pylock.<flavor>.toml URLs
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
if [[ ! -f "$PYLOCKS_GENERATOR" ]]; then
  error_exit "pylocks_generator.sh not found at ${PYLOCKS_GENERATOR}"
fi

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)           show_help; exit 0 ;;
    --pyproject-toml)    PYPROJECT="$2"; shift 2 ;;
    --flavor)            FLAVOR="$2"; shift 2 ;;
    --download)          DO_DOWNLOAD=true; shift ;;
    *)                   error_exit "Unknown argument: '$1'" ;;
  esac
done

[[ -z "$PYPROJECT" ]] && error_exit "--pyproject-toml is required."
[[ -f "$PYPROJECT" ]] || error_exit "File not found: $PYPROJECT"

# Derive paths
PROJECT_DIR="$(dirname "$PYPROJECT")"
PYLOCK_FILE="${PROJECT_DIR}/uv.lock.d/pylock.${FLAVOR}.toml"
REQUIREMENTS_FILE="${PROJECT_DIR}/requirements.${FLAVOR}.txt"

# Read build args from build-args/<flavor>.conf (same source as pylocks_generator.sh)
CONF_FILE="${PROJECT_DIR}/build-args/${FLAVOR}.conf"
INDEX_URL=""
if [[ -f "$CONF_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONF_FILE"
fi

# =========================================================================
# Step 1: Generate pylock.toml via pylocks_generator.sh
#
# Delegates to the same script CI uses (ci/generate_code.sh), ensuring the
# generated pylock.toml is identical to what check-generated-code expects.
# =========================================================================
echo "=== Step 1: Generating pylock via pylocks_generator.sh ==="
echo "  project dir : ${PROJECT_DIR}"
echo "  flavor      : ${FLAVOR}"
echo ""

bash "$PYLOCKS_GENERATOR" rh-index "$PROJECT_DIR"

if [[ ! -f "$PYLOCK_FILE" ]]; then
  error_exit "pylocks_generator.sh did not produce ${PYLOCK_FILE}"
fi

echo ""
echo "--- Done: ${PYLOCK_FILE} ---"
wc -l "$PYLOCK_FILE"

# =========================================================================
# Step 2: Convert pylock.<flavor>.toml → requirements.<flavor>.txt
#
# The pylock.toml (PEP 751) format is not yet supported by pip or cachi2.
# This step converts it to a pip-compatible requirements.txt with
# --hash=sha256:… lines for integrity verification.
# =========================================================================
echo ""
echo "=== Step 2: Converting pylock.${FLAVOR}.toml → requirements.${FLAVOR}.txt ==="

python3 "${SCRIPTS_PATH}/helpers/pylock-to-requirements.py" \
    "$PYLOCK_FILE" "$REQUIREMENTS_FILE" "$INDEX_URL"

echo ""
echo "--- Done: ${REQUIREMENTS_FILE} ---"
wc -l "${REQUIREMENTS_FILE}"

# =========================================================================
# Step 3 (optional): Download all wheels from pylock.toml
#
# Downloads every wheel referenced in the pylock into
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

  if command -v sha256sum &>/dev/null; then
    sha256_of() { sha256sum "$1" | cut -d' ' -f1; }
  else
    sha256_of() { shasum -a 256 "$1" | cut -d' ' -f1; }
  fi

  total=$(grep -c 'url = ".*sha256 = "' "$PYLOCK_FILE" || true)
  echo "  ${total} wheel(s) to download into ${OUT_DIR}/"
  echo ""

  idx=0
  while IFS= read -r line; do
    idx=$((idx + 1))

    url=$(echo "$line" | sed 's/.*url = "\([^"]*\)".*/\1/')
    sha=$(echo "$line" | sed 's/.*sha256 = "\([^"]*\)".*/\1/')

    filename="${url##*/}"; filename="${filename%%[?#]*}"
    dest="${OUT_DIR}/${filename}"

    echo "[${idx}/${total}] ${filename}"

    if [[ ! -f "$dest" ]]; then
      echo "  Downloading: ${url}"
      wget -q -O "$dest" "$url"
    else
      echo "  Already exists, skipping download."
    fi

    actual=$(sha256_of "$dest")
    if [[ "$actual" != "$sha" ]]; then
      echo "  ERROR: checksum mismatch (got ${actual}, expected ${sha})" >&2
      rm -f "$dest"
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
echo "  requirements     : ${REQUIREMENTS_FILE}"
if [[ "$DO_DOWNLOAD" == true ]]; then
  echo "  wheels           : cachi2/output/deps/pip/"
fi