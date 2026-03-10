#!/bin/bash
############################################################################################
# codeserver-offline-env.sh - Environment variables for hermetic code-server build
#
# [HERMETIC] Sourced by setup-offline-binaries.sh and every RUN step in the
# rpm-base stage that runs npm commands. Sets environment variables that tell
# argon2 (and the patched fetch.js) to use local caches instead of downloading.
#
# Usage: . prefetch-input/patches/codeserver-offline-env.sh
#    or: source prefetch-input/patches/codeserver-offline-env.sh
############################################################################################
HERMETO_OUTPUT="${HERMETO_OUTPUT:-/cachi2/output}"
CODESERVER_SOURCE_PREFETCH="${CODESERVER_SOURCE_PREFETCH:-$(pwd)/prefetch-input/code-server}"

# gcc-toolset-14 provides g++ (C++20 required by node-22 native modules).
# Must be enabled in every RUN step since each starts a fresh shell.
if [[ -f /opt/rh/gcc-toolset-14/enable ]]; then
    . /opt/rh/gcc-toolset-14/enable
fi

export TMPDIR=/tmp
# argon2: point at local mirror so it never hits the network. We do not prefetch
# argon2 prebuilds; when the tarball is missing here, node-pre-gyp falls back to
# building from source (node-gyp; gcc-toolset-14 is available in rpm-base).
export npm_config_argon2_binary_host_mirror="file://${HERMETO_OUTPUT}/deps/generic/"
# Electron: skip binary download entirely — code-server builds for the web
# (vscode-reh-web), not the Electron desktop app. The electron npm package is
# still in the dependency tree but its binary is never used at runtime.
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
# node-gyp: use system Node.js headers (from nodejs-devel RPM) instead of
# downloading Electron or Node.js headers. This is the same technique Dev Spaces
# uses to eliminate Electron header downloads from their che-code build.
export NPM_CONFIG_NODEDIR=/usr
export npm_config_nodedir=/usr
# Playwright: skip browser download during npm ci (Playwright is a devDep but
# only used for tests, not the build; chromium binary is not prefetched)
export PLAYWRIGHT_BROWSERS_PATH="${HOME}/.cache/ms-playwright"
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export PLAYWRIGHT_SKIP_FFMPEG_INSTALL=1
# VSCODE_OFFLINE_CACHE: used by the patched fetch.js (patches/code-server-v4.106.3/lib/vscode/build/lib/fetch.js)
# to read .vsix extensions and Node.js binaries from local files instead of downloading.
if [[ "$CODESERVER_SOURCE_PREFETCH" = /* ]]; then
  export VSCODE_OFFLINE_CACHE="${CODESERVER_SOURCE_PREFETCH}/.vscode-offline-cache"
else
  export VSCODE_OFFLINE_CACHE="${HOME:-/root}/${CODESERVER_SOURCE_PREFETCH}/.vscode-offline-cache"
fi

# npm offline settings: skip peer dep auto-install and ensure offline mode.
# These are also set globally (npm config set --global) by setup-offline-binaries.sh,
# but we export them here so they apply in every RUN step that sources this file
# (e.g. build, build:vscode, release, release:standalone, package).
export npm_config_offline=true
export npm_config_prefer_offline=true
export npm_config_fetch_retries=0
export npm_config_audit=false
export npm_config_fund=false
export npm_config_legacy_peer_deps=true
