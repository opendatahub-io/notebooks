#!/usr/bin/env bash
set -euo pipefail

# --- Configuration & Defaults ---
SCRIPTS_PATH="scripts/lockfile-generators"
DEST_DIR="./cachi2/output/deps/npm"
LOCKFILE=""

# --- Functions ---
usage() {
    echo "Usage: $0 --lock-file <path>"
    echo ""
    echo "Options:"
    echo "  -l, --lock-file    Path to the package-lock.json file"
    echo "  -h, --help         Display this help message"
    echo ""
    echo "Must be run from the repository root."
    exit 1
}

error_exit() {
    echo "Error: $1" >&2
    exit 1
}

# --- Root Directory Validation ---
if [[ ! -f "$SCRIPTS_PATH/download-npm.sh" ]]; then
    error_exit "This script must be run from the repository root."
fi

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
    case $1 in
        -l|--lock-file) LOCKFILE="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

[[ -z "$LOCKFILE" || ! -f "$LOCKFILE" ]] && error_exit "Valid --lock-file is required (path to package-lock.json)."

# --- Execution ---
mkdir -p "$DEST_DIR"

command -v jq &>/dev/null || error_exit "jq is required."

echo "Extracting URLs from $LOCKFILE..."

urls=$(jq -r '(.. | objects | select(has("resolved")) | .resolved)' "$LOCKFILE" | grep '^http' | sort -u)

[[ -z "$urls" ]] && error_exit "No resolved URLs found in lockfile."

total=$(echo "$urls" | wc -l | tr -d ' ')
count=0

echo "Found $total unique packages to download."

while read -r url; do
    count=$((count + 1))
    filename=$(basename "$url")
    # Check if the URL contains a scoped package (e.g., /@eslint/ or /@types/)
    if [[ "$url" =~ /@([^/]+)/ ]]; then
        scope="${BASH_REMATCH[1]}"
        # Combine the scope and the filename, omitting the '@'
        filename="${scope}-${filename}"
    fi

    filename=$(basename "$url")
    if [[ "$url" =~ /@([^/]+)/ ]]; then
        scope="${BASH_REMATCH[1]}"
        filename="${scope}-${filename}"
    fi

    echo "[$count/$total] Processing: $filename"

    if [[ -f "$DEST_DIR/$filename" ]]; then
        echo "  ⊘ Already exists, skipping."
    else
        if wget -q -O "$DEST_DIR/$filename" "$url"; then
            echo "  ✓ Downloaded $filename"
        else
            echo "  ✗ Failed: $url" >&2
        fi
    fi
done <<< "$urls"

echo ""
echo "Finished! Total packages: $total"
echo "Location: $DEST_DIR"