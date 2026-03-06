#!/bin/bash
set -euo pipefail
############################################################################################
# setup-offline-binaries.sh - Populate local caches for hermetic code-server build
#
# [HERMETIC] This script is sourced before `npm ci --offline` in the rpm-base
# stage of Dockerfile.cpu. It populates local caches for all binaries that code-server's
# build process would normally download at build time:
#
#   1. npm config: offline, prefer-offline, fetch-retries=0 (and legacy-peer-deps).
#   2. node-gyp: NPM_CONFIG_NODEDIR=/usr (from codeserver-offline-env.sh) → system headers.
#   3. Ripgrep: copy prefetched tarballs to /tmp/vscode-ripgrep-cache-<version>/.
#   4. VSCode .vsix: copy from utils/ (git-tracked) to VSCODE_OFFLINE_CACHE for patched fetch.js.
#   5. Node: pre-populate .build/node/ with system /usr/bin/node so gulp skips download.
#   6. Pre-populate .build/builtInExtensions/<name>/ from extracted .vsix in utils/.
#   7. Rewrite package-lock.json "resolved" URLs to file:///cachi2/output/deps/npm/...
#
# Root postinstall (ci/dev/postinstall.sh) runs install-deps custom-packages first, then
# test, lib/vscode; custom-packages populates the npm cache for lockfile resolution.
#
# Ripgrep/oc/GPG key are prefetched by cachi2 (artifacts.in.yaml) at /cachi2/output/deps/generic/.
# Built-in .vsix (js-debug, js-debug-companion, vscode-js-profile-table) are in utils/.
############################################################################################

# codeserver-offline-env.sh is the single source of truth for all env vars
# (HERMETO_OUTPUT, CODESERVER_SOURCE_PREFETCH, npm_config_*, NPM_CONFIG_NODEDIR, etc.)
. ./patches/codeserver-offline-env.sh

# Set npm global config so settings persist for subprocesses and lifecycle scripts
# (e.g. release:standalone) that may not inherit env vars.
npm config set --global offline true
npm config set --global prefer-offline true
npm config set --global fetch-retries 0
npm config set --global audit false
npm config set --global fund false
# Skip auto-installing peer dependencies (e.g. tslib@* from @microsoft/applicationinsights-core-js).
# The remote/.npmrc has legacy-peer-deps=true but that file is NOT copied into
# release-standalone/lib/vscode/, so npm install there would try to fetch peer deps.
npm config set --global legacy-peer-deps true

# node-gyp: NPM_CONFIG_NODEDIR=/usr (codeserver-offline-env.sh) uses system headers
# from nodejs-devel RPM; no Node headers tarball needed (same as che-code).

# Playwright Chromium: supplied via custom-packages/package.json (prefetched into deps/npm by cachi2).
# PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 (set in codeserver-offline-env.sh) prevents
# the @playwright/browser-chromium postinstall from attempting any download.

# Setup VSCode ripgrep - use the cache directory that @vscode/ripgrep expects
# Prefetched in prefetch-input/artifacts.in.yaml; Cachi2 puts them in HERMETO_OUTPUT/deps/generic/.
# Cache dir: <os.tmpdir()>/vscode-ripgrep-cache-<packageVersion>/ (see @vscode/ripgrep lib/download.js).
# We use a single version (v13.0.0-13) for all 4 arches; apply-patch.sh patches @vscode/ripgrep
# so its postinstall uses VERSION for every target (no MULTI_ARCH_LINUX_VERSION).
VSCODE_RIPGREP_VERSION="1.15.14"
RIPGREP_CACHE_DIR="/tmp/vscode-ripgrep-cache-${VSCODE_RIPGREP_VERSION}"
mkdir -p "${RIPGREP_CACHE_DIR}"
cp "${HERMETO_OUTPUT}/deps/generic/ripgrep-v13."*.tar.gz "${RIPGREP_CACHE_DIR}/"

# Setup VSCode marketplace extensions and Node.js binaries from prefetched files.
# VSCODE_OFFLINE_CACHE is already exported by codeserver-offline-env.sh.
# Built-in .vsix (js-debug, etc.) are in repo at utils/ (COPY'd into image); not from cachi2.
mkdir -p "${VSCODE_OFFLINE_CACHE}"
VSIX_UTILS="${CODESERVER_SOURCE_CODE}/utils"

# Copy .vsix extension files from utils/ (git-tracked large files)
cp "${VSIX_UTILS}/ms-vscode.js-debug-companion.1.1.3.vsix" "${VSCODE_OFFLINE_CACHE}/"
cp "${VSIX_UTILS}/ms-vscode.js-debug.1.105.0.vsix" "${VSCODE_OFFLINE_CACHE}/"
cp "${VSIX_UTILS}/ms-vscode.vscode-js-profile-table.1.0.10.vsix" "${VSCODE_OFFLINE_CACHE}/"

# [HERMETIC] Pre-populate .build/node/ with system Node (like che-code) so gulp skips download.
# build-vscode.sh is patched to build for current arch (vscode-reh-web-linux-${NODE_ARCH}).
# On ppc64le/s390x we add those arches to BUILD_TARGETS (below) and run the native task,
# so we only need system node in linux-${NODE_ARCH} (no extra node tarball).
NODE_BUILD_VERSION=$(grep -E '^target=' "${CODESERVER_SOURCE_PREFETCH}/lib/vscode/remote/.npmrc" | cut -d'"' -f2)
NODE_ARCH=$(node -p "process.arch")
VSCODE_BUILD_DIR="${CODESERVER_SOURCE_PREFETCH}/lib/vscode/.build"
NODE_CACHE_DIR="${VSCODE_BUILD_DIR}/node/v${NODE_BUILD_VERSION}/linux-${NODE_ARCH}"
mkdir -p "${NODE_CACHE_DIR}"
cp /usr/bin/node "${NODE_CACHE_DIR}/node"
chmod +x "${NODE_CACHE_DIR}/node"
echo "Cached system node for .build/node/v${NODE_BUILD_VERSION}/linux-${NODE_ARCH}/node"

# --- Pre-populate built-in extensions from prefetched .vsix files ---
# builtInExtensions.js: isUpToDate() checks .build/builtInExtensions/<name>/package.json
# If the version matches product.json, the download is skipped entirely.
EXTENSIONS_CACHE_DIR="${VSCODE_BUILD_DIR}/builtInExtensions"
mkdir -p "${EXTENSIONS_CACHE_DIR}"

populate_vsix() {
    local vsix_file="$1"
    local ext_name="$2"
    local ext_dir="${EXTENSIONS_CACHE_DIR}/${ext_name}"

    if [[ -d "${ext_dir}" && -f "${ext_dir}/package.json" ]]; then
        echo "Extension ${ext_name} already populated, skipping"
        return
    fi

    echo "Extracting ${ext_name} from $(basename "${vsix_file}")..."
    local tmp_dir="/tmp/vsix-extract-$$"
    rm -rf "${tmp_dir}"
    mkdir -p "${tmp_dir}"
    # .vsix is a ZIP; the extension contents are in the extension/ subdirectory
    unzip -qo "${vsix_file}" "extension/*" -d "${tmp_dir}"
    rm -rf "${ext_dir}"
    mv "${tmp_dir}/extension" "${ext_dir}"
    rm -rf "${tmp_dir}"
    echo "  -> ${ext_dir}"
}

populate_vsix "${VSIX_UTILS}/ms-vscode.js-debug-companion.1.1.3.vsix" "ms-vscode.js-debug-companion"
populate_vsix "${VSIX_UTILS}/ms-vscode.js-debug.1.105.0.vsix" "ms-vscode.js-debug"
populate_vsix "${VSIX_UTILS}/ms-vscode.vscode-js-profile-table.1.0.10.vsix" "ms-vscode.vscode-js-profile-table"

# Rewrite all package-lock.json "resolved" URLs to point to the cachi2 file cache.
# https://registry.npmjs.org/foo/-/foo-1.0.0.tgz → file:///cachi2/output/deps/npm/...
. /root/scripts/lockfile-generators/rewrite-npm-urls.sh prefetch-input/code-server

echo "Offline binary setup complete."
