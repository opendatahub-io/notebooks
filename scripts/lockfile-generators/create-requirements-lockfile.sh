#!/usr/bin/env bash
set -euo pipefail

# create-requirements-lockfile.sh — Generate requirements.<flavor>.txt for hermetic builds.
#
# Why this script exists
# ----------------------
# Hermetic builds need every Python wheel prefetched.  This script:
#   1. Delegates to pylocks_generator.py to generate pylock.<flavor>.toml
#      (or pylock.toml + sync when PROJECT_DIR is under PUBLIC_INDEX_PROJECTS).
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
PYLOCKS_GENERATOR="scripts/pylocks_generator.py"

# --- Defaults ---
PYPROJECT=""
FLAVOR="cpu"
DO_DOWNLOAD=false

# --- Functions ---
show_help() {
  cat << 'EOF'
Usage: ./scripts/lockfile-generators/create-requirements-lockfile.sh [OPTIONS]

Generate pylock.<flavor>.toml (via pylocks_generator.py) and convert it to
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
  1. pylocks_generator.py rh-index or public-index (see PUBLIC_INDEX_PROJECTS in script)
  2. Convert pylock → <project>/requirements.<flavor>.txt
  3. (--download) Download all wheels from the lockfile URLs
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
  error_exit "pylocks_generator.py not found at ${PYLOCKS_GENERATOR}"
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
REQUIREMENTS_FILE="${PROJECT_DIR}/requirements.${FLAVOR}.txt"

# Read build args from build-args/<flavor>.conf (same source as pylocks_generator.py)
CONF_FILE="${PROJECT_DIR}/build-args/${FLAVOR}.conf"
INDEX_URL=""
if [[ -f "$CONF_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONF_FILE"
fi

# Use public-index when PROJECT_DIR equals a listed path or is a subdirectory (e.g. .../tensorflow/ubi9-python-3.12).
PUBLIC_INDEX_PROJECTS=(
  jupyter/rocm/tensorflow
)

PYLOCKS_MODE="rh-index"
for _d in "${PUBLIC_INDEX_PROJECTS[@]}"; do
  if [[ "$PROJECT_DIR" == "$_d" || "$PROJECT_DIR" == "$_d/"* ]]; then
    PYLOCKS_MODE="public-index"
    break
  fi
done

PYLOCK_FILE="${PROJECT_DIR}/uv.lock.d/pylock.${FLAVOR}.toml"
REQUIREMENTS_INDEX_URL="$INDEX_URL"
if [[ "$PYLOCKS_MODE" == "public-index" ]]; then
  PYLOCK_FILE="${PROJECT_DIR}/pylock.toml"
  REQUIREMENTS_INDEX_URL=""
fi

# =========================================================================
# Step 1: Generate pylock.toml via pylocks_generator.py
#
# Delegates to the same script CI uses (ci/generate_code.sh), ensuring the
# generated pylock.toml is identical to what check-generated-code expects.
# =========================================================================
echo "=== Step 1: Generating pylock via pylocks_generator.py ==="
echo "  project dir : ${PROJECT_DIR}"
echo "  flavor      : ${FLAVOR}"
echo "  index mode  : ${PYLOCKS_MODE}"
echo ""

./uv run "$PYLOCKS_GENERATOR" "$PYLOCKS_MODE" "$PROJECT_DIR"

if [[ ! -f "$PYLOCK_FILE" ]]; then
  error_exit "pylocks_generator.py did not produce ${PYLOCK_FILE}"
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

if [[ -n "$REQUIREMENTS_INDEX_URL" ]]; then
  python3 "${SCRIPTS_PATH}/helpers/pylock-to-requirements.py" \
      "$PYLOCK_FILE" "$REQUIREMENTS_FILE" "$REQUIREMENTS_INDEX_URL"
else
  python3 "${SCRIPTS_PATH}/helpers/pylock-to-requirements.py" \
      "$PYLOCK_FILE" "$REQUIREMENTS_FILE"
fi

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
# Each wheel's sha256 checksum is verified after download (or on cache hit).
# A file is skipped only when present on disk and its digest matches this URL's
# expected hash; otherwise it is removed and fetched again.
# =========================================================================
if [[ "$DO_DOWNLOAD" == true ]]; then
  echo ""
  echo "=== Step 3: Downloading wheels ==="

  # Output directory must match Cachi2 layout so prefetched wheels are found
  # during hermetic/offline builds (e.g. Docker COPY from cachi2/output/deps/pip).
  OUT_DIR="cachi2/output/deps/pip"
  mkdir -p "$OUT_DIR"

  # Use sha256sum on Linux, shasum -a 256 on macOS (portable).
  if command -v sha256sum &>/dev/null; then
    sha256_of() { sha256sum "$1" | cut -d' ' -f1; }
  else
    sha256_of() { shasum -a 256 "$1" | cut -d' ' -f1; }
  fi

  # Count lines in pylock that look like "url = \"...\" ... sha256 = \"...\""
  # (one per wheel; multi-line wheel blocks have one such line per wheel).
  total=$(grep -c 'url = ".*sha256 = "' "$PYLOCK_FILE" || true)
  echo "  ${total} wheel(s) to download into ${OUT_DIR}/"
  echo ""

  idx=0
  # Read one line per wheel from the lockfile (same pattern as above).
  while IFS= read -r line; do
    idx=$((idx + 1))

    # Extract URL and expected sha256 from lockfile line (TOML-style).
    url=$(echo "$line" | sed 's/.*url = "\([^"]*\)".*/\1/')
    sha=$(echo "$line" | sed 's/.*sha256 = "\([^"]*\)".*/\1/')

    if [[ -z "$url" || -z "$sha" ]]; then
      echo "  ERROR: failed to parse url or sha256 from lockfile line (wheel ${idx})" >&2
      echo "  line: ${line:0:120}..." >&2
      exit 1
    fi

    # Filename is the last path segment of the URL, without query/fragment.
    filename="${url##*/}"; filename="${filename%%[?#]*}"
    if [[ -z "$filename" ]]; then
      echo "  ERROR: could not derive filename from URL (wheel ${idx})" >&2
      echo "  URL: ${url}" >&2
      exit 1
    fi
    dest="${OUT_DIR}/${filename}"

    echo "[${idx}/${total}] ${filename}"

    # Resume partial runs: reuse a file only if its digest matches this wheel.
    if [[ -f "$dest" ]]; then
      actual=$(sha256_of "$dest")
      if [[ "$actual" == "$sha" ]]; then
        echo "  Already present (checksum OK), skipping download."
      else
        echo "  WARNING: Ignoring stale or mismatched cached wheel (digest does not match this lockfile entry)." >&2
        echo "    file:     ${dest}" >&2
        echo "    got:      ${actual}" >&2
        echo "    expected: ${sha}" >&2
        echo "  Removing cached file and re-downloading." >&2
        rm -f "$dest"
      fi
    fi

    if [[ ! -f "$dest" ]]; then
      echo "  Downloading: ${url}"
      if ! wget -q -O "$dest" "$url"; then
        echo "  ERROR: download failed for ${filename}" >&2
        echo "  URL: ${url}" >&2
        echo "  Run 'wget -O /dev/null \"${url}\"' to see the full error." >&2
        rm -f "$dest"
        exit 1
      fi
    fi

    # Verify digest so corrupted downloads are detected.
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