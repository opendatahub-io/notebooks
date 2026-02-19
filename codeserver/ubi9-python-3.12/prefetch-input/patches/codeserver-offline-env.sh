#!/bin/bash
############################################################################################
# codeserver-offline-env.sh - Environment variables for hermetic code-server build
#
# [HERMETIC] Sourced by setup-offline-binaries.sh and every RUN step in the
# rpm-base stage that runs npm commands. Sets environment variables that tell Electron,
# Playwright, argon2, and the patched fetch.js to use local caches instead of downloading.
#
# Usage: . prefetch-input/patches/codeserver-offline-env.sh
#    or: source prefetch-input/patches/codeserver-offline-env.sh
############################################################################################
HERMETO_OUTPUT="${HERMETO_OUTPUT:-/cachi2/output}"
CODESERVER_SOURCE_PREFETCH="${CODESERVER_SOURCE_PREFETCH:-$(pwd)/prefetch-input/code-server}"

export TMPDIR=/tmp
# argon2 prebuild: redirect binary download to local file mirror
export npm_config_argon2_binary_host_mirror="file://${HERMETO_OUTPUT}/deps/generic/"
# Electron: skip download (we pre-populate the cache in setup-offline-binaries.sh)
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
export ELECTRON_CACHE=~/.cache/electron
# Playwright: skip browser download (pre-populated by setup-offline-binaries.sh)
export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright
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
