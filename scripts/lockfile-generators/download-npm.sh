#!/usr/bin/env bash
set -euo pipefail

# download-npm.sh — Download npm packages for offline/cachi2 builds.
#
# Extracts resolved URLs from package-lock.json and package.json files,
# then downloads each tarball into cachi2/output/deps/npm/.  Files that
# already exist are skipped.  This is the local-development equivalent of
# what cachi2 does for npm dependencies in Konflux CI.
#
# Handles the same URL types that rewrite-npm-urls.sh rewrites:
#   1. HTTPS registry URLs   (https://registry.npmjs.org/.../-/name-ver.tgz)
#   2. git+ssh/https:// URLs (git+ssh://...#hash or git+https://...#hash)
#   3. GitHub shortname refs (owner/repo#hash-or-branch  in dependency values)
#
# Two modes:
#   1) --lock-file <path>    Process a single package-lock.json (and its companion package.json).
#   2) --tekton-file <path>  Parse a Tekton PipelineRun YAML (.tekton/) to
#                            discover all npm-type prefetch-input paths, then
#                            process every package-lock.json and package.json found under them.
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

# ---------------------------------------------------------------------------
# Extract downloadable package references from a JSON file.
#
# Handles the same URL types that rewrite-npm-urls.sh rewrites, and derives
# filenames using the same conventions so that the downloaded tarballs land
# where the rewrite script (and npm ci --offline) expect them.
#
#   Type                 | Filename derivation
#   ---------------------+----------------------------------------------
#   Registry URL         | basename after /-/  (e.g. runtime-7.27.6.tgz)
#     (scoped)           | scope-basename      (e.g. types-cookie-parser-1.4.7.tgz)
#   git+ssh/https URL    | owner-repo-hash.tgz
#   Shortname ref        | owner-repo-ref.tgz
#
# Output: one "filename<TAB>download_url" pair per line, unsorted.
# ---------------------------------------------------------------------------
extract_refs_from_file() {
    local file="$1"

    # --- Collect all "resolved" field values once (used by types 1-2) --------
    local resolved_urls
    resolved_urls=$(jq -r '.. | objects | select(has("resolved")) | .resolved' "$file" 2>/dev/null) || true

    # --- 1. HTTPS registry URLs ---------------------------------------------
    # Before: "resolved": "https://registry.npmjs.org/@babel/runtime/-/runtime-7.27.6.tgz"
    # Filename: runtime-7.27.6.tgz  (basename — the part after /-/)
    # Download URL: the original URL itself
    #
    # SCOPED PACKAGES: npm registry URLs for scoped packages do NOT include
    # the scope in the tarball filename, so different packages can collide:
    #   @types/cookie-parser -> cookie-parser-1.4.7.tgz
    #   cookie-parser        -> cookie-parser-1.4.7.tgz
    # To avoid this, scoped packages get the scope prepended to the filename:
    #   @types/cookie-parser -> types-cookie-parser-1.4.7.tgz
    echo "$resolved_urls" \
        | grep -E '^https?://.*/-/' \
        | while IFS= read -r url; do
            local fname
            fname=$(basename "$url")
            # For scoped packages (/@scope/name/-/name-ver.tgz), prefix with scope
            if [[ "$url" =~ /@([^/]+)/[^/]+/-/ ]]; then
                fname="${BASH_REMATCH[1]}-${fname}"
            fi
            printf '%s\t%s\n' "$fname" "$url"
        done || true

    # --- 2+3. git+ssh:// and git+https:// URLs --------------------------------
    # Before: "resolved": "git+ssh://git@github.com/owner/repo.git#commithash"
    #     or: "resolved": "git+https://github.com/owner/repo.git#commithash"
    # Filename: owner-repo-commithash.tgz
    # Download URL: https://github.com/owner/repo/archive/commithash.tar.gz
    echo "$resolved_urls" \
        | grep -E '^git\+(ssh://git@|https://)github\.com/' \
        | while IFS= read -r url; do
            if [[ "$url" =~ git\+(ssh://git@|https://)github\.com/([^/]+)/([^.#\"]+)(\.git)?#(.+)$ ]]; then
                local owner="${BASH_REMATCH[2]}" repo="${BASH_REMATCH[3]}" ref="${BASH_REMATCH[5]}"
                printf '%s\t%s\n' \
                    "${owner}-${repo}-${ref}.tgz" \
                    "https://github.com/${owner}/${repo}/archive/${ref}.tar.gz"
            fi
        done || true

    # --- 3. GitHub shortname refs (from dependency values) -------------------
    # Before: "@parcel/watcher": "parcel-bundler/watcher#1ca032aa..."
    # Filename: parcel-bundler-watcher-1ca032aa....tgz
    # Download URL: https://github.com/parcel-bundler/watcher/archive/1ca032aa....tar.gz
    #
    # These appear in package.json dependency fields.  The jq query safely
    # returns nothing on files that lack these top-level keys.
    jq -r '
        [.dependencies, .devDependencies, .optionalDependencies, .peerDependencies]
        | map(select(. != null))
        | map(to_entries[])
        | .[].value
    ' "$file" 2>/dev/null \
        | grep -E '^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+#' \
        | while IFS= read -r ref; do
            if [[ "$ref" =~ ^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)#(.+)$ ]]; then
                local owner="${BASH_REMATCH[1]}" repo="${BASH_REMATCH[2]}" gitref="${BASH_REMATCH[3]}"
                printf '%s\t%s\n' \
                    "${owner}-${repo}-${gitref}.tgz" \
                    "https://github.com/${owner}/${repo}/archive/${gitref}.tar.gz"
            fi
        done || true
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

# --- Collect JSON files to process ---
# We process both package-lock.json (for registry/git resolved URLs) and
# package.json (for GitHub shortname refs), matching rewrite-npm-urls.sh scope.
declare -a json_files=()

if [[ -n "$LOCKFILE" ]]; then
    json_files+=("$LOCKFILE")
    # Also pick up the companion package.json for shortname refs
    companion_pjson="$(dirname "$LOCKFILE")/package.json"
    if [[ -f "$companion_pjson" ]]; then
        json_files+=("$companion_pjson")
    fi
fi

if [[ -n "$TEKTON_FILE" ]]; then
    echo "Parsing Tekton file: $TEKTON_FILE"
    npm_paths=$(extract_npm_paths_from_tekton "$TEKTON_FILE")

    if [[ -z "$npm_paths" ]]; then
        error_exit "No npm-type prefetch-input entries found in $TEKTON_FILE"
    fi

    while IFS= read -r npm_path; do
        [[ -z "$npm_path" ]] && continue
        # Find all package-lock.json and package.json files (skip node_modules)
        while IFS= read -r -d '' f; do
            json_files+=("$f")
            echo "  Found: $f"
        done < <(find "$npm_path" -not -path "*/node_modules/*" \
                    \( -name "package-lock.json" -o -name "package.json" \) \
                    -type f -print0 2>/dev/null)
    done <<< "$npm_paths"
fi

if [[ ${#json_files[@]} -eq 0 ]]; then
    error_exit "No valid package-lock.json or package.json files to process."
fi

echo ""
echo "Processing ${#json_files[@]} file(s)..."

# --- Collect all unique references across all files ---
all_refs=""
for f in "${json_files[@]}"; do
    echo "  Extracting references from $f..."
    refs=$(extract_refs_from_file "$f") || true
    if [[ -n "$refs" ]]; then
        all_refs+=$'\n'"$refs"
    fi
done

# Deduplicate by filename (first column)
refs=$(echo "$all_refs" | grep -v '^$' | sort -t$'\t' -k1,1 -u) || true

if [[ -z "$refs" ]]; then
    echo "No downloadable references found (all may already be local file:// references)."
    exit 0
fi

# --- Download ---
mkdir -p "$DEST_DIR"

total=$(echo "$refs" | wc -l | tr -d ' ')
count=0
downloaded=0
skipped=0
failed=0

echo ""
echo "Found $total unique packages to download."
echo ""

while IFS=$'\t' read -r filename download_url; do
    count=$((count + 1))

    if [[ -f "$DEST_DIR/$filename" ]]; then
        echo "[$count/$total] SKIP  Already exists: $filename"
        skipped=$((skipped + 1))
    else
        if wget -q -O "$DEST_DIR/$filename" "$download_url"; then
            echo "[$count/$total] OK    Downloaded: $filename"
            downloaded=$((downloaded + 1))
        else
            echo "[$count/$total] FAIL  Failed: $download_url" >&2
            failed=$((failed + 1))
            # Clean up partial download
            rm -f "$DEST_DIR/$filename"
        fi
    fi
done <<< "$refs"

echo ""
echo "Finished! Total: $total  Downloaded: $downloaded  Skipped: $skipped  Failed: $failed"
echo "Location: $DEST_DIR"
