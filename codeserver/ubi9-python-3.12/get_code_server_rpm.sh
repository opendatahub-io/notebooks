#!/bin/bash
set -euxo pipefail

##############################################################################
# This script is expected to be run as `root`                                #
# It builds code-server rpm for `ppc64le`                                    #
# For other architectures, the rpm is downloaded from the available releases #
##############################################################################


# Mapping of `uname -m` values to equivalent GOARCH values
declare -A UNAME_TO_GOARCH
UNAME_TO_GOARCH["x86_64"]="amd64"
UNAME_TO_GOARCH["aarch64"]="arm64"
UNAME_TO_GOARCH["ppc64le"]="ppc64le"
UNAME_TO_GOARCH["s390x"]="s390x"

ARCH="${UNAME_TO_GOARCH[$(uname -m)]}"

if [[ "$ARCH" == "amd64" || "$ARCH" == "arm64" || "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then   
    # starting with node-22, c++20 is required (gcc-toolset-14 installed from prefetched RPMs)
    . /opt/rh/gcc-toolset-14/enable
    # [HERMETIC] Install nfpm (RPM packager) from prefetched RPM (previously fetched from GitHub releases API at build time).
    dnf install -y /cachi2/output/deps/generic/nfpm-2.44.1-1.$(uname -m).rpm
    # [HERMETIC] CODESERVER_SOURCE_PREFETCH is set by Dockerfile ENV (points to prefetched code-server source).
    cd "${CODESERVER_SOURCE_PREFETCH}"

    # s390x: apply patch (from VSCodium: arch-4-s390x-package.json.patch)
    if [[ "$ARCH" == "s390x" ]]; then
        patch -p1 < patches/s390x.patch
    fi

    # # [HERMETIC] Apply offline-build patches (cachi2 rewrites, offline npm, etc.)
    # # Use `patch` instead of `git apply` because the prefetched source contains a
    # # nested git submodule (lib/vscode) whose .git reference is broken inside the
    # # container, causing `git apply` to fail on files within that submodule.
    # for p in patches/[0-9]*-*.patch; do
    #     echo "Applying $p"
    #     patch -p1 < "$p"
    # done

    # # [HERMETIC] Copy stored patched package.json/package-lock.json files.
    # # These directories have git-shorthand dependencies (@parcel/watcher,
    # # @emmetio/css-parser) that can't be fetched offline. The stored copies
    # # rewrite them to file:///cachi2/output/deps/generic/... URLs pointing to
    # # pre-fetched tarballs (listed in artifacts.in.yaml).
    # #
    # # We use COPY instead of diff patches because:
    # # - On Konflux, cachi2 npm prefetch rewrites resolved URLs in the source
    # #   before the Docker build, so diff context lines no longer match.
    # # - On local builds, cachi2 prefetch doesn't run, so we need the rewrites.
    # # The stored copies work in both environments since the generic tarballs
    # # are always available in the cachi2 cache.
    # echo "Copying patched lib/vscode/extensions/ files (@parcel/watcher rewrite)"
    # cp patches/lib/vscode/extensions/package.json lib/vscode/extensions/package.json
    # cp patches/lib/vscode/extensions/package-lock.json lib/vscode/extensions/package-lock.json

    # echo "Copying patched lib/vscode/extensions/emmet/ files (@emmetio/css-parser rewrite)"
    # cp patches/lib/vscode/extensions/emmet/package.json lib/vscode/extensions/emmet/package.json
    # cp patches/lib/vscode/extensions/emmet/package-lock.json lib/vscode/extensions/emmet/package-lock.json

    # echo "Copying patched lib/vscode/remote/ files (node-gyp, proc-log, @parcel/watcher)"
    # cp patches/lib/vscode/remote/package.json lib/vscode/remote/package.json
    # cp patches/lib/vscode/remote/package-lock.json lib/vscode/remote/package-lock.json

    

    # ppc64le/s390x: @vscode/vsce-sign's postinstall downloads a platform-specific
    # signing binary, but none exists for ppc64le/s390x so it exits(1) and breaks
    # npm ci.  The binary is unused in our build:
    #   - Build time: gulpfile.reh.js (VS Code Remote Extension Host) never references it.
    #   - Runtime: signature verification is disabled by patches/signature-verification.diff.
    #
    # Reference: b-data.ch builds code-server on ppc64le by downgrading @vscode/vsce
    # to 2.20.1 (which has no vsce-sign dependency at all), confirming it is safe to
    # remove.  See: https://gitlab.b-data.ch/coder/code-server-builder
    #              https://gitlab.b-data.ch/coder/code-server (patches/signature-verification.diff)
    #
    # Fix: remove the postinstall script from the cached tarball, then strip its
    # integrity hash from the lockfile so npm accepts the modified tarball.
    if [[ "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then
        VSCE_TGZ=$(find /cachi2/output/deps/npm -name "vscode-vsce-sign-*.tgz" -type f 2>/dev/null | head -1)
        if [[ -n "${VSCE_TGZ}" ]]; then
            echo "Patching vsce-sign: removing postinstall for ${ARCH} (${VSCE_TGZ})"
            tmpdir=$(mktemp -d)
            tar xzf "${VSCE_TGZ}" -C "$tmpdir"
            jq 'del(.scripts.postinstall)' "$tmpdir/package/package.json" \
                > /tmp/pkg-tmp.json && mv /tmp/pkg-tmp.json "$tmpdir/package/package.json"
            tar czf "${VSCE_TGZ}" -C "$tmpdir" package
            rm -rf "$tmpdir"
        fi
        # Strip integrity so npm accepts the modified tarball
        jq 'del(.packages["node_modules/@vscode/vsce-sign"].integrity)' \
            lib/vscode/build/package-lock.json > /tmp/lock-tmp.json \
            && mv /tmp/lock-tmp.json lib/vscode/build/package-lock.json
    fi

    # apply code-server's own patches to VS Code source
    while IFS= read -r src_patch; do echo "patches/$src_patch"; patch -p1 < "patches/$src_patch"; done < patches/series    
    npm cache clean --force
else
  # we shall not download rpm for other architectures
  echo "Unsupported architecture: $ARCH" >&2
  exit 1
fi
