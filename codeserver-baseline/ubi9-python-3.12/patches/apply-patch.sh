#!/usr/bin/env bash
set -Eeuxo pipefail

# Dockerfile invokes this from the code-server source root.
. /opt/rh/gcc-toolset-14/enable

while IFS= read -r src_patch || [[ -n "$src_patch" ]]; do
    [[ -z "$src_patch" ]] && continue
    patch -p1 < "patches/$src_patch"
done < patches/series

npm cache clean --force

if [[ "${GHA_BUILD:-false}" == "true" ]]; then
    "${CODESERVER_PATCHES}/tweak-gha.sh"
fi
