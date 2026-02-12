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
#   ./rewrite-npm-urls.sh . --no-cleanup              # keep the test directory after run
# =============================================================================
set -euo pipefail

# =============================================================================
# Configuration  (edit these as needed)
# =============================================================================

# Source directory to copy from (set via first positional argument, defaults to ".")
SOURCE_DIR="."

# Test directory to work in (will be created and optionally removed)
TEST_DIR="test"

# Target filenames to process (add more filenames to this array as needed)
TARGET_FILENAMES=(
    "package-lock.json"
    "package.json"
)

# Cachi2 local cache base path
CACHI2_BASE="file:///cachi2/output/deps/npm"

# Whether to remove the test directory at the end (override with --no-cleanup)
DO_CLEANUP=true

# =============================================================================
# Globals
# =============================================================================

# Populated by find_target_files()
TARGET_FILES=()

# Counters for the summary
TOTAL_REGISTRY_REWRITES=0
TOTAL_GIT_SSH_REWRITES=0
TOTAL_GIT_HTTPS_REWRITES=0
TOTAL_SHORTNAME_REWRITES=0

# =============================================================================
# Helper functions
# =============================================================================

log_info()  { echo "==> $*"; }
log_step()  { echo "    $*"; }
log_warn()  { echo "    WARN: $*"; }
log_error() { echo "    ERROR: $*" >&2; }
log_ok()    { echo "    OK: $*"; }

# -----------------------------------------------------------------------------
# Portable sed-in-place wrapper.
# macOS (BSD) sed needs: sed -i '' -E ...
# GNU sed needs:         sed -i -E ...
#
# Usage:  sed_i 's|old|new|g' file
#         (always uses -E for extended regex)
# -----------------------------------------------------------------------------
if sed --version 2>/dev/null | grep -q "GNU"; then
    sed_i() { sed -i -E "$@"; }
else
    sed_i() { sed -i '' -E "$@"; }
fi


# =============================================================================
# Step 2: Find all target JSON files inside the test directory
# =============================================================================
find_target_files() {
    log_info "Finding target JSON files..."

    TARGET_FILES=()
    for filename in "${TARGET_FILENAMES[@]}"; do
        while IFS= read -r -d '' file; do
            TARGET_FILES+=("${file}")
        done < <(find "${TEST_DIR}" -name "${filename}" -type f -print0)
    done

    log_step "Found ${#TARGET_FILES[@]} file(s) matching: ${TARGET_FILENAMES[*]}"

    if [[ ${#TARGET_FILES[@]} -eq 0 ]]; then
        log_warn "No target files found — nothing to do."
        return 1
    fi
}

# =============================================================================
# Step 3: URL rewrite functions (each operates on a single file)
# =============================================================================

# ---- 3a. HTTPS registry resolved URLs ---------------------------------------
# Before: "resolved": "https://registry.npmjs.org/@babel/runtime/-/runtime-7.27.6.tgz"
# After:  "resolved": "file:///cachi2/output/deps/npm/runtime-7.27.6.tgz"
#
# SCOPED PACKAGES: npm registry URLs for scoped packages do NOT include the
# scope in the tarball filename.  For example, both of these resolve to the
# same basename "cookie-parser-1.4.7.tgz":
#   @types/cookie-parser -> /@types/cookie-parser/-/cookie-parser-1.4.7.tgz
#   cookie-parser        -> /cookie-parser/-/cookie-parser-1.4.7.tgz
#
# To avoid filename collisions, scoped packages get the scope prepended:
#   @types/cookie-parser -> types-cookie-parser-1.4.7.tgz
#   cookie-parser        -> cookie-parser-1.4.7.tgz
# --------------------------------------------------------------------------
rewrite_registry_urls() {
    local file="$1"
    local before after

    before=$(grep -cE '"resolved": "https?://' "${file}" 2>/dev/null || true)

    # Pass 1: Scoped packages — @scope/name/-/name-ver.tgz → scope-name-ver.tgz
    # The /@([^/]+)/ captures the scope (without @), producing e.g. "types-cookie-parser-1.4.7.tgz"
    sed_i "s|\"resolved\": \"https?://[^\"]*/@([^/]+)/[^/]+/-/([^\"]+)\"|\"resolved\": \"${CACHI2_BASE}/\1-\2\"|g" \
        "${file}"

    # Pass 2: Unscoped packages — name/-/name-ver.tgz → name-ver.tgz (unchanged)
    # Only matches remaining https:// URLs (scoped ones were already rewritten in Pass 1)
    sed_i "s|\"resolved\": \"https?://[^\"]*/-/([^\"]+)\"|\"resolved\": \"${CACHI2_BASE}/\1\"|g" \
        "${file}"

    after=$(grep -cE '"resolved": "https?://' "${file}" 2>/dev/null || true)
    local count=$((before - after))
    TOTAL_REGISTRY_REWRITES=$((TOTAL_REGISTRY_REWRITES + count))

    if [[ ${count} -gt 0 ]]; then
        log_step "  Registry URLs rewritten: ${count}"
    fi
}

# ---- 3b. git+ssh:// resolved URLs -------------------------------------------
# Before: "resolved": "git+ssh://git@github.com/owner/repo.git#commithash"
# After:  "resolved": "file:///cachi2/output/deps/npm/owner-repo-commithash.tgz"
# --------------------------------------------------------------------------
rewrite_git_ssh_urls() {
    local file="$1"
    local before after

    before=$(grep -c '"resolved": "git+ssh://' "${file}" 2>/dev/null || true)

    sed_i "s|\"resolved\": \"git\+ssh://git@github\.com/([^/]+)/([^.#\"]+)(\.git)?#([^\"]+)\"|\"resolved\": \"${CACHI2_BASE}/\1-\2-\4.tgz\"|g" \
        "${file}"

    after=$(grep -c '"resolved": "git+ssh://' "${file}" 2>/dev/null || true)
    local count=$((before - after))
    TOTAL_GIT_SSH_REWRITES=$((TOTAL_GIT_SSH_REWRITES + count))

    if [[ ${count} -gt 0 ]]; then
        log_step "  git+ssh URLs rewritten:  ${count}"
    fi
}

# ---- 3c. git+https:// resolved URLs -----------------------------------------
# Before: "resolved": "git+https://github.com/owner/repo.git#commithash"
# After:  "resolved": "file:///cachi2/output/deps/npm/owner-repo-commithash.tgz"
# --------------------------------------------------------------------------
rewrite_git_https_urls() {
    local file="$1"
    local before after

    before=$(grep -c '"resolved": "git+https://' "${file}" 2>/dev/null || true)

    sed_i "s|\"resolved\": \"git\+https://github\.com/([^/]+)/([^.#\"]+)(\.git)?#([^\"]+)\"|\"resolved\": \"${CACHI2_BASE}/\1-\2-\4.tgz\"|g" \
        "${file}"

    after=$(grep -c '"resolved": "git+https://' "${file}" 2>/dev/null || true)
    local count=$((before - after))
    TOTAL_GIT_HTTPS_REWRITES=$((TOTAL_GIT_HTTPS_REWRITES + count))

    if [[ ${count} -gt 0 ]]; then
        log_step "  git+https URLs rewritten: ${count}"
    fi
}

# ---- 3d. GitHub shortname dependency references ------------------------------
# Matches values like: "owner/repo#hash-or-branch"
# Before: "@parcel/watcher": "parcel-bundler/watcher#1ca032aa..."
# After:  "@parcel/watcher": "file:///cachi2/output/deps/npm/parcel-bundler-watcher-1ca032aa....tgz"
#
# Before: "@emmetio/css-parser": "ramya-rao-a/css-parser#vscode"
# After:  "@emmetio/css-parser": "file:///cachi2/output/deps/npm/ramya-rao-a-css-parser-vscode.tgz"
# --------------------------------------------------------------------------
rewrite_shortname_refs() {
    local file="$1"
    local before after

    before=$(grep -cE '": "[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+#[^"]*"' "${file}" 2>/dev/null || true)

    # Pattern: ": "owner/repo#ref"  → ": "file:///cachi2/.../owner-repo-ref.tgz"
    # Owner/repo contain [a-zA-Z0-9_.-], ref is anything up to the closing quote.
    sed_i "s|: \"([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)#([^\"]+)\"|: \"${CACHI2_BASE}/\1-\2-\3.tgz\"|g" \
        "${file}"

    after=$(grep -cE '": "[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+#[^"]*"' "${file}" 2>/dev/null || true)
    local count=$((before - after))
    TOTAL_SHORTNAME_REWRITES=$((TOTAL_SHORTNAME_REWRITES + count))

    if [[ ${count} -gt 0 ]]; then
        log_step "  Shortname refs rewritten: ${count}"
    fi
}

# ---- 3e. Remove integrity for git-resolved dependencies ---------------------
# npm integrity hashes for git dependencies are computed from npm's own
# `npm pack` of the git checkout at install time.  The tarball available
# offline (raw GitHub archive, or differently-packed by cachi2) will almost
# certainly have a different hash because npm packing is not reproducible
# across environments / npm versions.
#
# Removing the "integrity" field tells npm to skip hash verification for
# these entries, which is safe because the content is pinned by the git
# commit hash in the resolved URL.
#
# Must run BEFORE URL rewrites so we can still identify git+ssh / git+https
# resolved URLs.
# --------------------------------------------------------------------------
remove_git_integrity() {
    local file="$1"
    local git_count

    git_count=$(grep -cE '"resolved": "git\+(ssh|https)://' "${file}" 2>/dev/null || true)

    if [[ ${git_count} -gt 0 ]]; then
        # For each "resolved": "git+..." line, remove the immediately following
        # "integrity" line (if present).  Uses perl for reliable cross-line logic.
        perl -i -ne '
            if ($skip_next) {
                $skip_next = 0;
                next if /^\s*"integrity":\s*"/;
            }
            $skip_next = 1 if /"resolved":\s*"git\+/;
            print;
        ' "${file}"

        log_step "  Git integrity fields removed for ${git_count} git dep(s)"
    fi
}

# =============================================================================
# Step 4: Process a single file through all rewrite passes
# =============================================================================
process_file() {
    local file="$1"

    log_step "Processing: ${file}"

    # Must run first: strip integrity hashes for git deps (before URLs are rewritten)
    remove_git_integrity   "${file}"
    rewrite_registry_urls  "${file}"
    rewrite_git_ssh_urls   "${file}"
    rewrite_git_https_urls "${file}"
    rewrite_shortname_refs "${file}"
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
    echo "  Test dir    : ${TEST_DIR}"
    echo "  Filenames   : ${TARGET_FILENAMES[*]}"
    echo "  Cache base  : ${CACHI2_BASE}"
    echo "  Cleanup     : ${DO_CLEANUP}"
    echo ""
}

# =============================================================================
# Print a final summary
# =============================================================================
print_summary() {
    echo ""
    echo "----------------------------------------------"
    echo "  Summary"
    echo "----------------------------------------------"
    echo "  Registry URLs rewritten : ${TOTAL_REGISTRY_REWRITES}"
    echo "  git+ssh URLs rewritten  : ${TOTAL_GIT_SSH_REWRITES}"
    echo "  git+https URLs rewritten: ${TOTAL_GIT_HTTPS_REWRITES}"
    echo "  Shortname refs rewritten: ${TOTAL_SHORTNAME_REWRITES}"
    echo "  Total files processed   : ${#TARGET_FILES[@]}"
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
            --no-cleanup)
                DO_CLEANUP=false
                ;;
            --help|-h)
                echo "Usage: $0 [SOURCE_DIR] [--no-cleanup] [--help]"
                echo ""
                echo "  SOURCE_DIR     Directory to process (default: current directory '.')"
                echo "  --no-cleanup   Keep the test directory after the run"
                echo "  --help         Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0 .                          # process current directory"
                echo "  $0 prefetch-input/code-server  # process a specific directory"
                echo "  $0 . --no-cleanup              # process and keep test dir"
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

    # Use SOURCE_DIR directly — no intermediate test directory needed.
    # (TEST_DIR="test" was a leftover from a dev/testing workflow; the copy
    # step that would have populated it was never implemented.)
    TEST_DIR="${SOURCE_DIR}"

    print_banner

    # Step 2: Find all target JSON files
    find_target_files

    # Step 3 & 4: Rewrite URLs in every file
    log_info "Rewriting URLs in ${#TARGET_FILES[@]} file(s)..."
    for file in "${TARGET_FILES[@]}"; do
        process_file "${file}"
    done

    # Print summary
    print_summary

}

main "$@"
