#!/usr/bin/env bash
set -euo pipefail

# download-rpms: Download RPMs from an RPM lockfile and create DNF repository metadata.
#
# This script reads a generated rpms.lock.yaml, which is created by create-rpm-lockfile.sh,
# downloads each referenced RPM into cachi2/output/deps/rpm, verifies checksums when yq is available,
# and runs createrepo_c (or createrepo, or a container fallback) so the directory can be used as
# a DNF repo. We need it for offline and Cachi2-based image builds: the build uses the lockfile to
# install the exact same RPMs without hitting upstream mirrors, and DNF requires repodata to
# resolve and install from the local directory.

# --- Configuration & Defaults ---
SCRIPTS_PATH="scripts/lockfile-generators"
DEST_DIR="./cachi2/output/deps/rpm"
LOCKFILE=""

# --- Functions ---
usage() {
    echo "Usage: $0 --lock-file <path>"
    echo ""
    echo "Options:"
    echo "  -l, --lock-file    Path to rpms.lock.yaml (e.g. codeserver/ubi9-python-3.12/prefetch-input/rpms.lock.yaml)"
    echo "  -h, --help         Display this help message"
    echo ""
    echo "Note: This script must be run from the project root directory."
    exit 1
}

error_exit() {
    echo "Error: $1" >&2
    exit 1
}

run_createrepo_in_container() {
    local repo_dir_abs="$1"
    local img="localhost/notebook-rpm-lockfile:latest"
    echo "Creating repository metadata via podman (notebook-rpm-lockfile image)..."
    podman run --rm -v "${repo_dir_abs}:/repo:z" --platform=linux/x86_64 "$img" sh -c \
        "rm -rf /repo/repodata && createrepo_c /repo && repo2module /repo > modules.yaml && modifyrepo_c --mdtype=modules modules.yaml /repo/repodata"
}

# --- Root Directory Validation ---
if [[ ! -f "$SCRIPTS_PATH/download-rpms.sh" ]]; then
    echo "Current directory: $(pwd)" >&2
    error_exit "This script must be run from the repository root."
fi

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        -l|--lock-file)
            [[ $# -lt 2 ]] && error_exit "--lock-file requires a value."
            LOCKFILE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

[[ -z "$LOCKFILE" ]] && error_exit "--lock-file is required."
[[ ! -f "$LOCKFILE" ]] && error_exit "Lock file not found: $LOCKFILE"

# --- Execution ---
mkdir -p "$DEST_DIR"

echo "Starting download of RPMs from $LOCKFILE..."

if command -v yq &>/dev/null; then
    urls=$(yq '.arches[].packages[].url' "$LOCKFILE")
else
    echo "Warning: yq not found. Falling back to grep/sed (requires url: key in lockfile)." >&2
    # Match list-item lines containing "url: " (e.g. "  - url: https://...")
    urls=$(grep -E '^[[:space:]]+- url:' "$LOCKFILE" | sed 's/.*url:[[:space:]]*//')
fi

total=$(echo "$urls" | grep -c . || true)
count=0

for url in $urls; do
    [[ -z "$url" ]] && continue
    count=$((count + 1))
    filename=$(basename "$url")

    echo "[$count/$total] Downloading: $filename"

    if ! wget -q -nc -P "$DEST_DIR" "$url"; then
        echo "Error: Failed to download $url" >&2
        continue
    fi

    if command -v yq &>/dev/null; then
        # Use yq with --arg to safely pass URL; allow yq to fail (e.g. --arg unsupported) without exiting (set -e)
        checksum=$(yq --arg u "$url" '.arches[].packages[] | select(.url == $u) | .checksum' "$LOCKFILE" 2>/dev/null | head -n 1) || checksum=""
        if [[ -n "$checksum" ]]; then
            hash="${checksum#sha256:}"
            if ! echo "$hash  $DEST_DIR/$filename" | sha256sum -c - &>/dev/null; then
                error_exit "Checksum mismatch for $filename"
            fi
            echo "  ✓ Checksum verified for $filename"
        fi
    fi
done

# Create DNF repo metadata so dnf can use this directory (e.g. with local.repo)
if command -v createrepo_c &>/dev/null; then
    echo "Creating repository metadata (createrepo_c)..."
    createrepo_c "$DEST_DIR"
elif command -v createrepo &>/dev/null; then
    echo "Creating repository metadata (createrepo)..."
    createrepo "$DEST_DIR"
else
    DEST_ABS="$(cd "$DEST_DIR" && pwd)"
    run_createrepo_in_container "$DEST_ABS"
fi

echo "Finished! RPMs are located in $DEST_DIR"