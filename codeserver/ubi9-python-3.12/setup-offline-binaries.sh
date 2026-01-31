#!/bin/bash
set -euo pipefail

HERMETO_OUTPUT=/cachi2/output
CODESERVER_SOURCE_PREFETCH="${CODESERVER_SOURCE_PREFETCH:-$(pwd)/prefetch-input/code-server}"
. ./utils/codeserver-offline-env.sh

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

# Setup Electron (ELECTRON_* and PLAYWRIGHT_* are already set by codeserver-offline-env.sh)
mkdir -p ~/.cache/electron
cp "${HERMETO_OUTPUT}/deps/generic/electron-v37.3.1-linux-x64.zip" ~/.cache/electron/
cp "${HERMETO_OUTPUT}/deps/generic/SHASUMS256.txt" ~/.cache/electron/SHASUMS256.txt-37.3.1

# Setup node-gyp cache for Electron headers (37.3.1)
# node-gyp expects headers at: ~/.cache/node-gyp/<version>/
mkdir -p ~/.cache/node-gyp/37.3.1
tar -xzf "${HERMETO_OUTPUT}/deps/generic/node-v37.3.1-headers.tar.gz" \
    -C ~/.cache/node-gyp/37.3.1 --strip-components=1
echo "11" > ~/.cache/node-gyp/37.3.1/installVersion

# Setup node-gyp cache for Node.js headers (22.19.0)
# Some build tools may use system Node.js instead of Electron
mkdir -p ~/.cache/node-gyp/22.19.0
tar -xzf "${HERMETO_OUTPUT}/deps/generic/node-v22.19.0-headers.tar.gz" \
    -C ~/.cache/node-gyp/22.19.0 --strip-components=1
echo "11" > ~/.cache/node-gyp/22.19.0/installVersion

# Setup node-gyp cache for Node.js headers (22.18.0)
# VSCode remote modules target this specific Node.js version
mkdir -p ~/.cache/node-gyp/22.18.0
tar -xzf "${HERMETO_OUTPUT}/deps/generic/node-v22.18.0-headers.tar.gz" \
    -C ~/.cache/node-gyp/22.18.0 --strip-components=1
echo "11" > ~/.cache/node-gyp/22.18.0/installVersion

# Setup Playwright Chromium
mkdir -p ~/.cache/ms-playwright/chromium-1134
unzip -q "${HERMETO_OUTPUT}/deps/generic/chromium-1134-linux.zip" -d ~/.cache/ms-playwright/chromium-1134
# Mark as installed
touch ~/.cache/ms-playwright/chromium-1134/INSTALLATION_COMPLETE

# Setup VSCode ripgrep - use the cache directory that @vscode/ripgrep expects
# The cache directory is: <os.tmpdir()>/vscode-ripgrep-cache-<packageVersion>/
# where packageVersion is the version from @vscode/ripgrep package.json
VSCODE_RIPGREP_VERSION="1.15.14"
RIPGREP_CACHE_DIR="/tmp/vscode-ripgrep-cache-${VSCODE_RIPGREP_VERSION}"
mkdir -p "${RIPGREP_CACHE_DIR}"

# Copy both architecture tarballs to the cache with the exact name the package expects
# Format: ripgrep-<version>-<target>.tar.gz (@vscode/ripgrep picks by arch at runtime)
cp "${HERMETO_OUTPUT}/deps/generic/ripgrep-v13.0.0-13-x86_64-unknown-linux-musl.tar.gz" \
   "${RIPGREP_CACHE_DIR}/ripgrep-v13.0.0-13-x86_64-unknown-linux-musl.tar.gz"
cp "${HERMETO_OUTPUT}/deps/generic/ripgrep-v13.0.0-13-aarch64-unknown-linux-gnu.tar.gz" \
   "${RIPGREP_CACHE_DIR}/ripgrep-v13.0.0-13-aarch64-unknown-linux-gnu.tar.gz"

echo "VSCode ripgrep cache populated at ${RIPGREP_CACHE_DIR}"

# Setup VSCode marketplace extensions and Node.js binaries from prefetched files
# Copy files to a location accessible during build
VSCODE_OFFLINE_DIR="/root/${CODESERVER_SOURCE_PREFETCH}/.vscode-offline-cache"
mkdir -p "${VSCODE_OFFLINE_DIR}"

# Copy .vsix extension files
cp "${HERMETO_OUTPUT}/deps/generic/ms-vscode.js-debug-companion.1.1.3.vsix" "${VSCODE_OFFLINE_DIR}/"
cp "${HERMETO_OUTPUT}/deps/generic/ms-vscode.js-debug.1.104.0.vsix" "${VSCODE_OFFLINE_DIR}/"
cp "${HERMETO_OUTPUT}/deps/generic/ms-vscode.vscode-js-profile-table.1.0.10.vsix" "${VSCODE_OFFLINE_DIR}/"

# Copy Node.js runtime binary (for bundling with VSCode server)
cp "${HERMETO_OUTPUT}/deps/generic/node-v22.18.0-linux-x64.tar.gz" "${VSCODE_OFFLINE_DIR}/"

echo "Copied VSCode offline files to ${VSCODE_OFFLINE_DIR}"

# fetch.js is patched via patches/code-server/lib/vscode/build/lib/fetch.js (COPY in Dockerfile)
# VSCODE_OFFLINE_CACHE is already set by codeserver-offline-env.sh (sourced at top of this script)

echo "Offline binary setup complete!"
