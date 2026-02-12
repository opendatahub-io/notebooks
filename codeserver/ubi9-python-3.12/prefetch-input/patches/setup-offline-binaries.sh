#!/bin/bash
#set +euo pipefail

############################################################################################
# setup-offline-binaries.sh - Populate local caches for hermetic code-server build
#
# [HERMETIC] This script is sourced before `npm ci --offline` in the rpm-base
# stage of Dockerfile.cpu. It populates local caches for all binaries that code-server's
# build process would normally download at build time:
#
#   1. npm config: set offline=true, prefer-offline=true, fetch-retries=0
#   2. Electron: pre-populate ~/.cache/electron/ with the prefetched zip + checksums
#   3. node-gyp headers: set up ~/.cache/node-gyp/ for Electron v37.7.0, Node 22.22.0, 22.20.0
#   4. Playwright Chromium: unzip into ~/.cache/ms-playwright/chromium-1134/
#   5. VSCode ripgrep: copy to /tmp/vscode-ripgrep-cache-<version>/
#   6. VSCode extensions (.vsix): copy to .vscode-offline-cache/ for fetch.js
#   7. Node.js runtime binary: copy to .vscode-offline-cache/ for bundling
#   8. Pre-populate .build/ caches so gulp tasks skip network downloads:
#      - .build/node/v22.20.0/linux-x64/node (Node.js binary for bundling)
#      - .build/builtInExtensions/<name>/ (extracted .vsix contents)
#
# All artifacts are prefetched by cachi2 via artifacts.in.yaml and stored at
# /cachi2/output/deps/generic/.
############################################################################################

HERMETO_OUTPUT=/cachi2/output
CODESERVER_SOURCE_PREFETCH="${CODESERVER_SOURCE_PREFETCH:-$(pwd)/prefetch-input/code-server}"
. ./patches/codeserver-offline-env.sh

# Configure npm for offline mode
# Use both exports (for current script) and global config (for future npm commands)
export npm_config_offline=true
export npm_config_prefer_offline=true
export npm_config_fetch_retries=0
export npm_config_audit=false
export npm_config_fund=false
export npm_config_legacy_peer_deps=true

# Also set globally for npm commands run in different contexts (like release:standalone)
npm config set --global offline true
npm config set --global prefer-offline true
npm config set --global fetch-retries 0
npm config set --global audit false
npm config set --global fund false
# Skip auto-installing peer dependencies (e.g. tslib@* from @microsoft/applicationinsights-core-js).
# The remote/.npmrc has legacy-peer-deps=true but that file is NOT copied into
# release-standalone/lib/vscode/, so npm install there would try to fetch peer deps.
npm config set --global legacy-peer-deps true

# Setup Electron (ELECTRON_* and PLAYWRIGHT_* are already set by patches/codeserver-offline-env.sh)
mkdir -p ~/.cache/electron
cp "${HERMETO_OUTPUT}/deps/generic/electron-v37.7.0-linux-x64.zip" ~/.cache/electron/
cp "${HERMETO_OUTPUT}/deps/generic/SHASUMS256.txt" ~/.cache/electron/SHASUMS256.txt-37.7.0

# Setup node-gyp cache for Electron headers (37.7.0)
# node-gyp expects headers at: ~/.cache/node-gyp/<version>/
mkdir -p ~/.cache/node-gyp/37.7.0
tar -xzf "${HERMETO_OUTPUT}/deps/generic/node-v37.7.0-headers.tar.gz" \
    -C ~/.cache/node-gyp/37.7.0 --strip-components=1
echo "11" > ~/.cache/node-gyp/37.7.0/installVersion

# Setup node-gyp cache for Node.js headers (22.22.0)
# Some build tools may use system Node.js instead of Electron
mkdir -p ~/.cache/node-gyp/22.22.0
tar -xzf "${HERMETO_OUTPUT}/deps/generic/node-v22.22.0-headers.tar.gz" \
    -C ~/.cache/node-gyp/22.22.0 --strip-components=1
echo "11" > ~/.cache/node-gyp/22.22.0/installVersion

# Setup node-gyp cache for Node.js headers (22.20.0)
# VSCode remote modules target this specific Node.js version
mkdir -p ~/.cache/node-gyp/22.20.0
tar -xzf "${HERMETO_OUTPUT}/deps/generic/node-v22.20.0-headers.tar.gz" \
    -C ~/.cache/node-gyp/22.20.0 --strip-components=1
echo "11" > ~/.cache/node-gyp/22.20.0/installVersion

# Setup Playwright Chromium
mkdir -p ~/.cache/ms-playwright/chromium-1134
unzip -qo "${HERMETO_OUTPUT}/deps/generic/chromium-1134-linux.zip" -d ~/.cache/ms-playwright/chromium-1134
# Mark as installed
touch ~/.cache/ms-playwright/chromium-1134/INSTALLATION_COMPLETE

# Setup VSCode ripgrep - use the cache directory that @vscode/ripgrep expects
# Prefetched in prefetch-input/artifacts.in.yaml; Cachi2 puts them in HERMETO_OUTPUT/deps/generic/.
# Cache dir: <os.tmpdir()>/vscode-ripgrep-cache-<packageVersion>/ (see @vscode/ripgrep lib/download.js).
# x64/arm64 use VERSION v13.0.0-13; ppc64le/s390x/arm-gnueabihf use MULTI_ARCH_LINUX_VERSION v13.0.0-4 (package hardcodes this).
VSCODE_RIPGREP_VERSION="1.15.14"
RIPGREP_CACHE_DIR="/tmp/vscode-ripgrep-cache-${VSCODE_RIPGREP_VERSION}"
mkdir -p "${RIPGREP_CACHE_DIR}"
cp "${HERMETO_OUTPUT}/deps/generic/ripgrep-v13."*.tar.gz "${RIPGREP_CACHE_DIR}/"

echo "VSCode ripgrep cache populated at ${RIPGREP_CACHE_DIR}"

# Setup VSCode marketplace extensions and Node.js binaries from prefetched files
# Copy files to a location accessible during build (CODESERVER_SOURCE_PREFETCH may be absolute from ENV)
if [[ "$CODESERVER_SOURCE_PREFETCH" = /* ]]; then
  VSCODE_OFFLINE_DIR="${CODESERVER_SOURCE_PREFETCH}/.vscode-offline-cache"
else
  VSCODE_OFFLINE_DIR="${HOME:-/root}/${CODESERVER_SOURCE_PREFETCH}/.vscode-offline-cache"
fi
mkdir -p "${VSCODE_OFFLINE_DIR}"

# Copy .vsix extension files
cp "${HERMETO_OUTPUT}/deps/generic/ms-vscode.js-debug-companion.1.1.3.vsix" "${VSCODE_OFFLINE_DIR}/"
cp "${HERMETO_OUTPUT}/deps/generic/ms-vscode.js-debug.1.105.0.vsix" "${VSCODE_OFFLINE_DIR}/"
cp "${HERMETO_OUTPUT}/deps/generic/ms-vscode.vscode-js-profile-table.1.0.10.vsix" "${VSCODE_OFFLINE_DIR}/"

# Copy Node.js runtime binary (for bundling with VSCode server)
cp "${HERMETO_OUTPUT}/deps/generic/node-v22.20.0-linux-x64.tar.gz" "${VSCODE_OFFLINE_DIR}/"

echo "Copied VSCode offline files to ${VSCODE_OFFLINE_DIR}"

# [HERMETIC] Pre-populate VSCode .build/ caches so that gulp tasks skip network downloads.
# The VSCode build system checks these directories BEFORE attempting to fetch from the network:
#   - .build/node/v<version>/<platform>-<arch>/  → skips Node.js binary download
#   - .build/builtInExtensions/<name>/           → skips extension download from GitHub
#
# By populating them here, the build:vscode step (gulp vscode-reh-web-linux-x64-min) runs
# fully offline without needing to patch fetch.js.
VSCODE_BUILD_DIR="${CODESERVER_SOURCE_PREFETCH}/lib/vscode/.build"

# --- Pre-populate Node.js binary for bundling with VSCode server ---
# gulpfile.reh.js: if .build/node/v<ver>/<platform>-<arch>/ exists → skip download
# The gulp task extracts the tarball, filters for the 'node' binary, and writes it there.
NODE_BUILD_VERSION="22.20.0"
NODE_CACHE_DIR="${VSCODE_BUILD_DIR}/node/v${NODE_BUILD_VERSION}/linux-x64"
if [[ ! -d "${NODE_CACHE_DIR}" ]]; then
    mkdir -p "${NODE_CACHE_DIR}"
    tar -xzf "${HERMETO_OUTPUT}/deps/generic/node-v${NODE_BUILD_VERSION}-linux-x64.tar.gz" \
        -C "${NODE_CACHE_DIR}" --strip-components=1 --wildcards '*/bin/node'
    # Flatten: gulp expects .build/node/v22.20.0/linux-x64/node (not bin/node)
    mv "${NODE_CACHE_DIR}/bin/node" "${NODE_CACHE_DIR}/node"
    rmdir "${NODE_CACHE_DIR}/bin" 2>/dev/null || true
    chmod +x "${NODE_CACHE_DIR}/node"
    echo "Pre-populated Node.js ${NODE_BUILD_VERSION} binary at ${NODE_CACHE_DIR}/node"
fi

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

populate_vsix "${HERMETO_OUTPUT}/deps/generic/ms-vscode.js-debug-companion.1.1.3.vsix" "ms-vscode.js-debug-companion"
populate_vsix "${HERMETO_OUTPUT}/deps/generic/ms-vscode.js-debug.1.105.0.vsix" "ms-vscode.js-debug"
populate_vsix "${HERMETO_OUTPUT}/deps/generic/ms-vscode.vscode-js-profile-table.1.0.10.vsix" "ms-vscode.vscode-js-profile-table"

echo "Pre-populated built-in extensions at ${EXTENSIONS_CACHE_DIR}"

# Rewrite all package-lock.json "resolved" URLs to point to the cachi2 file cache.
# This is the critical step that makes `npm ci --offline` work: URLs like
# https://registry.npmjs.org/foo/-/foo-1.0.0.tgz become file:///cachi2/output/deps/npm/...
echo "Rewriting package-lock.json resolved URLs to cachi2 file cache..."
. /root/scripts/lockfile-generators/rewrite-npm-urls.sh prefetch-input/code-server
echo "Offline binary setup complete!"
