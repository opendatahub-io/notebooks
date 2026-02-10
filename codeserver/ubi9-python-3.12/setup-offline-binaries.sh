#!/bin/bash
set -euo pipefail

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

# Also set globally for npm commands run in different contexts (like release:standalone)
npm config set --global offline true
npm config set --global prefer-offline true
npm config set --global fetch-retries 0
npm config set --global audit false
npm config set --global fund false

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
unzip -q "${HERMETO_OUTPUT}/deps/generic/chromium-1134-linux.zip" -d ~/.cache/ms-playwright/chromium-1134
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
cp "${HERMETO_OUTPUT}/deps/generic/ms-vscode.js-debug.1.104.0.vsix" "${VSCODE_OFFLINE_DIR}/"
cp "${HERMETO_OUTPUT}/deps/generic/ms-vscode.vscode-js-profile-table.1.0.10.vsix" "${VSCODE_OFFLINE_DIR}/"

# Copy Node.js runtime binary (for bundling with VSCode server)
cp "${HERMETO_OUTPUT}/deps/generic/node-v22.20.0-linux-x64.tar.gz" "${VSCODE_OFFLINE_DIR}/"

echo "Copied VSCode offline files to ${VSCODE_OFFLINE_DIR}"

# fetch.js is patched via patches/code-server/lib/vscode/build/lib/fetch.js (COPY in Dockerfile)
# VSCODE_OFFLINE_CACHE is already set by patches/codeserver-offline-env.sh (sourced at top of this script)

# Rewrite all package-lock.json "resolved" URLs to point to the cachi2 file cache.
# This is the critical step that makes `npm ci --offline` work: URLs like
# https://registry.npmjs.org/foo/-/foo-1.0.0.tgz become file:///cachi2/output/deps/npm/...
echo "Rewriting package-lock.json resolved URLs to cachi2 file cache..."
REWRITE_SCRIPT="/root/scripts/lockfile-generators/rewrite-cachi2-path.sh"
if [[ -f "$REWRITE_SCRIPT" ]]; then
    . "$REWRITE_SCRIPT"
    pushd "${CODESERVER_SOURCE_PREFETCH}" > /dev/null
    find . -name "package-lock.json" -type f | while read f; do
        echo "Patching $f"
        rewrite_cachi2_path "$f"
    done
    popd > /dev/null
else
    echo "WARNING: $REWRITE_SCRIPT not found, skipping URL rewrite"
fi

echo "Offline binary setup complete!"
