#!/usr/bin/env bash
set -euo pipefail

# download-npm.sh — Download npm packages for offline/cachi2 builds.
#
# Extracts resolved http(s) URLs from package-lock.json files using jq,
# then downloads each tarball into cachi2/output/deps/npm/.  Files that
# already exist are skipped.  This is the local-development equivalent of
# what cachi2 does for npm dependencies in Konflux CI.
#
# Two modes:
#   1) --lock-file <path>    Process a single package-lock.json.
#   2) --tekton-file <path>  Parse a Tekton PipelineRun YAML (.tekton/) to
#                            discover all npm-type prefetch-input paths, then
#                            process every package-lock.json found under them.
#
# Both flags can be combined.  URLs that are already local
# (file:///cachi2/...) are automatically skipped.

# --- Configuration & Defaults ---
SCRIPTS_PATH="scripts/lockfile-generators"
DEST_DIR="./cachi2/output/deps/npm"
LOCKFILE=""
TEKTON_FILE=""

# --- Functions ---
usage() {
    echo "Usage: $0 [--lock-file <path>] [--tekton-file <path>]"
    echo ""
    echo "Options:"
    echo "  -l, --lock-file     Path to a single package-lock.json file"
    echo "  -t, --tekton-file   Path to a Tekton PipelineRun YAML under .tekton/"
    echo "                      Extracts all npm-type prefetch-input paths and downloads"
    echo "                      resolved packages from each package-lock.json found."
    echo "  -h, --help          Display this help message"
    echo ""
    echo "At least one of --lock-file or --tekton-file must be provided."
    echo "Must be run from the repository root."
    exit 1
}

error_exit() {
    echo "Error: $1" >&2
    exit 1
}

# Extract resolved http(s) URLs from a package-lock.json, one per line, sorted and unique.
extract_urls_from_lockfile() {
    local lockfile="$1"
    jq -r '(.. | objects | select(has("resolved")) | .resolved)' "$lockfile" \
        | grep '^https\?://' \
        | sort -u
}

# Derive the local filename for an npm registry URL.
# Scoped packages (e.g. /@types/node/-/node-1.0.0.tgz) get a "scope-name" prefix
# so they don't collide with unscoped packages of the same tarball name.
url_to_filename() {
    local url="$1"
    local filename
    filename=$(basename "$url")
    if [[ "$url" =~ /@([^/]+)/ ]]; then
        local scope="${BASH_REMATCH[1]}"
        filename="${scope}-${filename}"
    fi
    echo "$filename"
}

# Parse a Tekton PipelineRun YAML and print all paths where type == "npm".
extract_npm_paths_from_tekton() {
    local tekton_file="$1"
    yq eval '
        .spec.params[]
        | select(.name == "prefetch-input")
        | .value[]
        | select(.type == "npm")
        | .path
    ' "$tekton_file"
}

# --- Root Directory Validation ---
if [[ ! -f "$SCRIPTS_PATH/download-npm.sh" ]]; then
    error_exit "This script must be run from the repository root."
fi

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
    case $1 in
        -l|--lock-file)   LOCKFILE="$2";    shift 2 ;;
        -t|--tekton-file) TEKTON_FILE="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

[[ -z "$LOCKFILE" && -z "$TEKTON_FILE" ]] && error_exit "At least one of --lock-file or --tekton-file is required."

# --- Validate inputs ---
if [[ -n "$LOCKFILE" && ! -f "$LOCKFILE" ]]; then
    error_exit "--lock-file path does not exist: $LOCKFILE"
fi
if [[ -n "$TEKTON_FILE" && ! -f "$TEKTON_FILE" ]]; then
    error_exit "--tekton-file path does not exist: $TEKTON_FILE"
fi

# --- Pre-flight checks ---
command -v jq  &>/dev/null || error_exit "jq is required."
if [[ -n "$TEKTON_FILE" ]]; then
    command -v yq &>/dev/null || error_exit "yq is required (https://github.com/mikefarah/yq)."
fi

# --- Collect lockfiles to process ---
declare -a lockfiles=()

if [[ -n "$LOCKFILE" ]]; then
    lockfiles+=("$LOCKFILE")
fi

if [[ -n "$TEKTON_FILE" ]]; then
    echo "Parsing Tekton file: $TEKTON_FILE"
    npm_paths=$(extract_npm_paths_from_tekton "$TEKTON_FILE")

    if [[ -z "$npm_paths" ]]; then
        error_exit "No npm-type prefetch-input entries found in $TEKTON_FILE"
    fi

    while IFS= read -r npm_path; do
        [[ -z "$npm_path" ]] && continue
        lockfile_path="${npm_path}/package-lock.json"
        if [[ -f "$lockfile_path" ]]; then
            lockfiles+=("$lockfile_path")
            echo "  Found: $lockfile_path"
        else
            echo "  Warning: $lockfile_path not found, skipping."
        fi
    done <<< "$npm_paths"
fi

if [[ ${#lockfiles[@]} -eq 0 ]]; then
    error_exit "No valid package-lock.json files to process."
fi

echo ""
echo "Processing ${#lockfiles[@]} lockfile(s)..."

# --- Collect all unique URLs across all lockfiles ---
all_urls=""
for lf in "${lockfiles[@]}"; do
    echo "  Extracting URLs from $lf..."
    urls=$(extract_urls_from_lockfile "$lf") || true
    if [[ -n "$urls" ]]; then
        all_urls+=$'\n'"$urls"
    fi
done

# Deduplicate across all lockfiles
urls=$(echo "$all_urls" | grep -v '^$' | sort -u) || true

if [[ -z "$urls" ]]; then
    echo "No http(s) resolved URLs found across all lockfiles (all may already be local file:// references)."
    exit 0
fi

# --- Download ---
mkdir -p "$DEST_DIR"

total=$(echo "$urls" | wc -l | tr -d ' ')
count=0
downloaded=0
skipped=0
failed=0

echo ""
echo "Found $total unique packages to download."
echo ""

while IFS= read -r url; do
    count=$((count + 1))
    filename=$(url_to_filename "$url")

    if [[ -f "$DEST_DIR/$filename" ]]; then
        echo "[$count/$total] ⊘ Already exists: $filename"
        skipped=$((skipped + 1))
    else
        if wget -q -O "$DEST_DIR/$filename" "$url"; then
            echo "[$count/$total] ✓ Downloaded: $filename"
            downloaded=$((downloaded + 1))
        else
            echo "[$count/$total] ✗ Failed: $url" >&2
            failed=$((failed + 1))
            # Clean up partial download
            rm -f "$DEST_DIR/$filename"
        fi
    fi
done <<< "$urls"

echo ""
echo "Finished! Total: $total  Downloaded: $downloaded  Skipped: $skipped  Failed: $failed"
echo "Location: $DEST_DIR"