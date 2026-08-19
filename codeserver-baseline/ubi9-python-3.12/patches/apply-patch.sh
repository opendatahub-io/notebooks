#!/usr/bin/env bash
set -Eeuxo pipefail

# Dockerfile invokes this from the code-server source root.
. /opt/rh/gcc-toolset-14/enable

while IFS= read -r src_patch || [[ -n "$src_patch" ]]; do
    [[ -z "$src_patch" ]] && continue
    patch -p1 < "patches/$src_patch"
done < patches/series

# ppc64le/s390x: @vscode/vsce-sign (dep of @vscode/vsce) has a postinstall script
# that hard-fails on unsupported arches, even though code-server doesn't need it.
# The hermetic codeserver flow patches this via cachi2 tarballs; for phase-1 online
# builds, neutralize it via the lockfile metadata so npm doesn't run the script.
ARCH="$(uname -m)"
if [[ "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then
    while IFS= read -r -d '' lockfile; do
        if jq -e '.packages["node_modules/@vscode/vsce-sign"]' "$lockfile" >/dev/null 2>&1; then
            echo "Patching vsce-sign hasInstallScript=false in ${lockfile}"
            jq '
                (.packages["node_modules/@vscode/vsce-sign"].hasInstallScript = false) |
                del(.packages["node_modules/@vscode/vsce-sign"].integrity)
            ' "$lockfile" > /tmp/lock-tmp.json && mv /tmp/lock-tmp.json "$lockfile"
        fi
    done < <(find lib/vscode -name package-lock.json -type f -print0)
fi

npm cache clean --force

if [[ "${GHA_BUILD:-false}" == "true" ]]; then
    "${CODESERVER_PATCHES}/tweak-gha.sh"
fi
