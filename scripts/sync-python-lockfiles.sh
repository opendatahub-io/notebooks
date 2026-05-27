#!/usr/bin/env bash
set -Eeuxo pipefail

error() {
  printf '%s\n' "$*" >&2
}

# Red Hat's build tooling depends on requirements.txt files with hashes
# Namely, Konflux (https://konflux-ci.dev/), and Cachi2 (https://github.com/containerbuildsystem/cachi2).

# Optional behavior:
# - If FORCE_LOCKFILES_UPGRADE=1 (env) or --upgrade (arg) is provided, perform a
#   ground-up relock and force upgrades using `uv pip compile --upgrade`.
#   This is intended for scheduled runs, while manual runs should default to off.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
CVE_CONSTRAINTS_FILE="$ROOT_DIR/dependencies/cve-constraints.txt"
# Default to the repo-root ./uv wrapper; override with UV=/path/to/your/wrapper
UV="${UV:-$ROOT_DIR/uv}"
export UV

ADDITIONAL_UV_FLAGS=""
for arg in "$@"; do
  case "$arg" in
    --upgrade)
      FORCE_LOCKFILES_UPGRADE=1
      ;;
  esac
done

if [[ "${FORCE_LOCKFILES_UPGRADE:-0}" == "1" ]]; then
  ADDITIONAL_UV_FLAGS="--upgrade"
fi
export ADDITIONAL_UV_FLAGS

if [[ ! -x "$UV" ]]; then
  error "Expected uv wrapper at '$UV' but it is missing or not executable."
  exit 1
fi

if ! command -v uv &>/dev/null; then
  error "uv command not found. Please install uv: https://github.com/astral-sh/uv"
  exit 1
fi

UV_MIN_VERSION="0.4.0"
UV_VERSION=$("$UV" --version 2>/dev/null | awk '{print $2}' || echo "0.0.0")

version_ge() {
  [ "$(printf '%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

if ! version_ge "$UV_VERSION" "$UV_MIN_VERSION"; then
  error "uv version $UV_VERSION found, but >= $UV_MIN_VERSION is required."
  error "Please upgrade uv: https://github.com/astral-sh/uv"
  exit 1
fi

if [[ ! -f "$CVE_CONSTRAINTS_FILE" ]]; then
  error "CVE constraints file not found: $CVE_CONSTRAINTS_FILE"
  exit 1
fi

# The following will create a pylock.toml file for every pyproject.toml we have.
${UV} --version
while IFS= read -r -d '' lockfile; do
  lock_dir=$(dirname "$lockfile")
  (
    cd "$lock_dir"
    # Relative path avoids absolute paths in pylock.toml headers (CI vs local).
    constraints_path=$(
      CVE_CONSTRAINTS_FILE="$CVE_CONSTRAINTS_FILE" python3 -c \
        'import os; print(os.path.relpath(os.environ["CVE_CONSTRAINTS_FILE"], os.getcwd()))'
    )
    # derives python-version from directory suffix (e.g., "ubi9-python-3.12")
    # shellcheck disable=SC2086
    ${UV} pip compile pyproject.toml \
      --output-file pylock.toml \
      --format pylock.toml \
      --generate-hashes \
      --emit-index-url \
      --python-version="${PWD##*-}" \
      --python-platform linux \
      --no-annotate \
      --constraints "${constraints_path}" \
      ${ADDITIONAL_UV_FLAGS:-} \
      --quiet
  )
done < <(find . -name pylock.toml -print0)
