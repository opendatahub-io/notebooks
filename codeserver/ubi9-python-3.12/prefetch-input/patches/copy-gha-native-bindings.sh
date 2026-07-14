#!/bin/bash
# GHA-only: copy native .node files built in lib/vscode during postinstall into
# release-standalone. vscode-reh-web output (rsync'd by release:standalone) does not
# include those bindings; npm rebuild there is a no-op on trimmed packages.
set -Eeuxo pipefail

. "${CODESERVER_SOURCE_CODE}/patches/codeserver-offline-env.sh"

src_root="${CODESERVER_SOURCE_PREFETCH}"
dst_root="${src_root}/release-standalone"

copy_native_artifacts() {
    local src_pkg="$1"
    local dst_pkg="$2"
    local label="$3"
    local required="${4:-true}"

    if [[ ! -d "${src_pkg}" ]]; then
        if [[ "${required}" == "true" ]]; then
            echo "ERROR: ${label} source not found at ${src_pkg}" >&2
            return 1
        fi
        echo "WARNING: ${label} source not found at ${src_pkg}, skipping"
        return 0
    fi
    if [[ ! -d "${dst_pkg}" ]]; then
        if [[ "${required}" == "true" ]]; then
            echo "ERROR: ${label} destination not found at ${dst_pkg}" >&2
            return 1
        fi
        echo "WARNING: ${label} destination not found at ${dst_pkg}, skipping"
        return 0
    fi

    local copied=false
    for subdir in build prebuilds compiled; do
        if [[ -d "${src_pkg}/${subdir}" ]]; then
            mkdir -p "${dst_pkg}/${subdir}"
            rsync -a "${src_pkg}/${subdir}/" "${dst_pkg}/${subdir}/"
            copied=true
        fi
    done

    if [[ "${copied}" != "true" ]]; then
        if [[ "${required}" == "true" ]]; then
            echo "ERROR: no native artifacts found under ${src_pkg} for ${label}" >&2
            return 1
        fi
        echo "WARNING: no native artifacts found under ${src_pkg} for ${label}, skipping"
        return 0
    fi
    echo "Copied native artifacts for ${label} into ${dst_pkg}"
}

echo "Copying GHA native bindings from lib/vscode build tree into release-standalone"

copy_native_artifacts \
    "${src_root}/lib/vscode/node_modules/@vscode/spdlog" \
    "${dst_root}/lib/vscode/node_modules/@vscode/spdlog" \
    "@vscode/spdlog"

# node-pty is built under lib/vscode/remote during postinstall; runtime loads it from
# release-standalone/lib/vscode/node_modules/node-pty after npm install merges remote deps.
copy_native_artifacts \
    "${src_root}/lib/vscode/remote/node_modules/node-pty" \
    "${dst_root}/lib/vscode/node_modules/node-pty" \
    "node-pty" \
    "false"

spdlog_dst="${dst_root}/lib/vscode/node_modules/@vscode/spdlog"
if [[ -f "${spdlog_dst}/build/Release/spdlog.node" && ! -e "${spdlog_dst}/build/spdlog.node" ]]; then
    ln -sf Release/spdlog.node "${spdlog_dst}/build/spdlog.node"
fi

if ! find "${spdlog_dst}" -name 'spdlog.node' -print -quit | grep -q .; then
    echo "ERROR: spdlog.node not found under ${spdlog_dst} after copy" >&2
    exit 1
fi

echo "Verified spdlog.node present under ${spdlog_dst}"
