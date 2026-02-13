#!/usr/bin/env bash
# =============================================================================
# rewrite-npm-urls.sh
#
# Rewrites all resolved URLs in package-lock.json and package.json files
# to point to the local cachi2 offline cache:
#   file:///cachi2/output/deps/npm/<filename>
#
# Handles:
#   1. HTTPS registry URLs  (https://registry.npmjs.org/.../-/name-ver.tgz)
#   2. git+ssh:// URLs       (git+ssh://git@github.com/owner/repo.git#hash)
#   3. git+https:// URLs     (git+https://github.com/owner/repo.git#hash)
#   4. GitHub shortname refs  (owner/repo#hash-or-branch  in dependency values)
#
# Usage:
#   ./rewrite-npm-urls.sh .                          # run on the current directory
#   ./rewrite-npm-urls.sh prefetch-input/code-server  # run on a specific directory
# =============================================================================
set -euo pipefail

# =============================================================================
# Configuration  (edit these as needed)
# =============================================================================

# Source directory to process (set via first positional argument, defaults to ".")
SOURCE_DIR="."

# Target filenames to process (add more filenames to this array as needed)
TARGET_FILENAMES=(
    "package-lock.json"
    "package.json"
)

# Cachi2 local cache base path
CACHI2_BASE="file:///cachi2/output/deps/npm"

# =============================================================================
# Globals
# =============================================================================

# Populated by find_target_files()
TARGET_FILES=()

# Counter for the summary
TOTAL_FILES_PROCESSED=0

# =============================================================================
# Helper functions
# =============================================================================

log_info()  { echo "==> $*"; }
log_step()  { echo "    $*"; }
log_warn()  { echo "    WARN: $*"; }
log_error() { echo "    ERROR: $*" >&2; }


# =============================================================================
# Find all target JSON files inside the source directory
# =============================================================================
find_target_files() {
    log_info "Finding target JSON files..."

    TARGET_FILES=()
    for filename in "${TARGET_FILENAMES[@]}"; do
        while IFS= read -r -d '' file; do
            TARGET_FILES+=("${file}")
        done < <(find "${SOURCE_DIR}" -name "${filename}" -type f -print0)
    done

    log_step "Found ${#TARGET_FILES[@]} file(s) matching: ${TARGET_FILENAMES[*]}"

    if [[ ${#TARGET_FILES[@]} -eq 0 ]]; then
        log_warn "No target files found — nothing to do."
        return 1
    fi
}

# =============================================================================
# Process a single file through all rewrite passes (uses perl).
# Each perl one-liner is one rewrite type.
#
# Order matters: integrity removal must run BEFORE URL rewrites so we can
# still identify git+ssh / git+https resolved URLs.
#
# Rewrite types:
#   1. Remove integrity hashes for git-resolved deps
#   2. Registry URLs   https://registry.npmjs.org/...  → file:///cachi2/...
#   3. git+ssh/https   git+ssh://...#hash              → file:///cachi2/...-hash.tgz
#   4. Shortname refs  "owner/repo#ref"                → file:///cachi2/...-ref.tgz
# =============================================================================
process_file() {
    local file="$1"
    log_step "Processing: ${file}"

    # 1) Strip integrity hashes for git deps (npm pack is not reproducible,
    #    so offline tarballs will have different hashes — safe to remove
    #    because content is pinned by git commit hash).
    perl -i -ne '
        if ($s) { $s=0; next if /^\s*"integrity":\s*"/ }
        $s=1 if /"resolved":\s*"git\+/; print
    ' "${file}"

    # 2) Registry URLs (scoped @scope/pkg and unscoped pkg in one pass).
    #    Scoped: @types/cookie-parser/-/cookie-parser-1.4.7.tgz → types-cookie-parser-1.4.7.tgz
    #    Unscoped: express/-/express-4.19.2.tgz                  → express-4.19.2.tgz
    perl -i -pe 's!"resolved": "https?://[^"]*?/(?:\@([^/]+)/)?[^/]+/-/([^"]+)"! "\"resolved\": \"'"${CACHI2_BASE}"'/" . ($1 ? "$1-$2" : "$2") . "\"" !ge' "${file}"

    # 3) git+ssh and git+https URLs → owner-repo-hash.tgz
    perl -i -pe 's!"resolved": "git\+(ssh://git\@|https://)github\.com/([^/]+)/([^.#"]+)(?:\.git)?#([^"]+)"!"resolved": "'"${CACHI2_BASE}"'/$2-$3-$4.tgz"!g' "${file}"

    # 4) GitHub shortname refs: "owner/repo#ref" → cachi2 path
    perl -i -pe 's!": "([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)#([^"]+)"!": "'"${CACHI2_BASE}"'/$1-$2-$3.tgz"!g' "${file}"

    TOTAL_FILES_PROCESSED=$((TOTAL_FILES_PROCESSED + 1))
}


# =============================================================================
# Print a banner with the current configuration
# =============================================================================
print_banner() {
    echo "=============================================="
    echo "  npm URL Rewriter for cachi2 offline builds"
    echo "=============================================="
    echo ""
    echo "  Source dir  : ${SOURCE_DIR}"
    echo "  Filenames   : ${TARGET_FILENAMES[*]}"
    echo "  Cache base  : ${CACHI2_BASE}"
    echo ""
}

# =============================================================================
# Print a final summary
# =============================================================================
print_summary() {
    echo ""
    echo "----------------------------------------------"
    echo "  Done — ${TOTAL_FILES_PROCESSED} file(s) processed"
    echo "----------------------------------------------"
    echo ""
}

# =============================================================================
# Parse command-line arguments
# =============================================================================
parse_args() {
    local positional_set=false

    for arg in "$@"; do
        case "${arg}" in
            --help|-h)
                echo "Usage: $0 [SOURCE_DIR] [--help]"
                echo ""
                echo "  SOURCE_DIR     Directory to process (default: current directory '.')"
                echo "  --help         Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0 .                          # process current directory"
                echo "  $0 prefetch-input/code-server  # process a specific directory"
                exit 0
                ;;
            -*)
                log_error "Unknown option: ${arg}"
                echo "Try '$0 --help' for usage information."
                exit 1
                ;;
            *)
                if [[ "${positional_set}" == true ]]; then
                    log_error "Unexpected argument: ${arg} (source directory already set to '${SOURCE_DIR}')"
                    echo "Try '$0 --help' for usage information."
                    exit 1
                fi
                SOURCE_DIR="${arg}"
                positional_set=true
                ;;
        esac
    done
}

# =============================================================================
# Main
# =============================================================================
main() {
    parse_args "$@"
    print_banner

    # Find all target JSON files
    find_target_files

    # Rewrite URLs in every file
    log_info "Rewriting URLs in ${#TARGET_FILES[@]} file(s)..."
    for file in "${TARGET_FILES[@]}"; do
        process_file "${file}"
    done

    print_summary
}

main "$@"
