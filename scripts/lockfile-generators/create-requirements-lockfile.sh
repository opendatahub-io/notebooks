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
# =========================================================================
echo ""
echo "=== Step 2: Converting pylock.toml → requirements.txt ==="

python3 - "$PYLOCK_FILE" "$REQUIREMENTS_FILE" "$RHOAI_INDEX" << 'PYEOF'
import sys
import tomllib
from pathlib import Path

pylock_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
index_url = sys.argv[3] if len(sys.argv) > 3 else ""

with open(pylock_path, "rb") as f:
    data = tomllib.load(f)

lines = []
if index_url:
    lines.append(f"--index-url {index_url}")

for pkg in data.get("packages", []):
    name = pkg["name"]
    version = pkg["version"]
    marker = pkg.get("marker", "")

    hashes = []
    for whl in pkg.get("wheels", []):
        for algo, digest in whl.get("hashes", {}).items():
            hashes.append(f"--hash={algo}:{digest}")

    entry = f"{name}=={version}"
    if marker:
        entry += f" ; {marker}"
    if hashes:
        entry += " \\\n" + " \\\n".join(f"    {h}" for h in hashes)

    lines.append(entry)

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("\n".join(lines) + "\n")
pkg_count = len(lines) - (1 if index_url else 0)
print(f"  Generated {output_path} ({pkg_count} packages)")
PYEOF

echo ""
echo "--- Done: ${REQUIREMENTS_FILE} ---"
wc -l "${REQUIREMENTS_FILE}"

# =========================================================================
# Step 3 (optional): Download all wheels from pylock.toml
# =========================================================================
if [[ "$DO_DOWNLOAD" == true ]]; then
  echo ""
  echo "=== Step 3: Downloading wheels ==="

  python3 - "$PYLOCK_FILE" << 'PYEOF'
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path

OUT_DIR = Path("cachi2/output/deps/pip")
OUT_DIR.mkdir(parents=True, exist_ok=True)

pylock_path = Path(sys.argv[1])
with open(pylock_path, "rb") as f:
    data = tomllib.load(f)

to_fetch = []
for pkg in data.get("packages", []):
    name, version = pkg["name"], pkg["version"]
    for whl in pkg.get("wheels", []):
        url = whl.get("url", "")
        sha = whl.get("hashes", {}).get("sha256", "")
        if url and sha:
            filename = url.rsplit("/", 1)[-1].split("?")[0].split("#")[0]
            to_fetch.append((name, version, url, filename, sha))

total = len(to_fetch)
print(f"  {total} wheel(s) to download into {OUT_DIR}/\n")

for idx, (name, version, url, filename, expected) in enumerate(to_fetch, 1):
    dest = OUT_DIR / filename
    print(f"[{idx}/{total}] {name}=={version}  {filename}")
    if not dest.exists():
        print(f"  Downloading: {url}")
        subprocess.run(["wget", "-q", "-O", str(dest), url], check=True)
    else:
        print(f"  Already exists, skipping download.")
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        print(f"  ERROR: checksum mismatch (got {actual}, expected {expected})",
              file=sys.stderr)
        sys.exit(1)
    print(f"  Checksum OK (sha256:{actual[:16]}...)")

print(f"\nDone: {total} file(s) present and validated in {OUT_DIR}/")
PYEOF
fi

echo ""
echo "=== All done ==="
echo "  pylock.toml      : ${PYLOCK_FILE}"
echo "  requirements.txt : ${REQUIREMENTS_FILE}"
if [[ "$DO_DOWNLOAD" == true ]]; then
  echo "  wheels           : cachi2/output/deps/pip/"
fi
