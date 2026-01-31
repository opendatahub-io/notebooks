#!/bin/bash
# Code-server offline build environment. Source this script; do not execute.
# Expects HERMETO_OUTPUT and CODESERVER_SOURCE_PREFETCH to be set, or uses defaults.
# Usage: . utils/codeserver-offline-env.sh
#    or: source utils/codeserver-offline-env.sh
HERMETO_OUTPUT="${HERMETO_OUTPUT:-/cachi2/output}"
CODESERVER_SOURCE_PREFETCH="${CODESERVER_SOURCE_PREFETCH:-$(pwd)/prefetch-input/code-server}"

export TMPDIR=/tmp
export npm_config_argon2_binary_host_mirror="file://${HERMETO_OUTPUT}/deps/generic/"
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
export ELECTRON_CACHE=~/.cache/electron
export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export PLAYWRIGHT_SKIP_FFMPEG_INSTALL=1
# CODESERVER_SOURCE_PREFETCH may be absolute (from ENV) or relative; avoid double /root/ when already absolute
if [[ "$CODESERVER_SOURCE_PREFETCH" = /* ]]; then
  export VSCODE_OFFLINE_CACHE="${CODESERVER_SOURCE_PREFETCH}/.vscode-offline-cache"
else
  export VSCODE_OFFLINE_CACHE="${HOME:-/root}/${CODESERVER_SOURCE_PREFETCH}/.vscode-offline-cache"
fi
